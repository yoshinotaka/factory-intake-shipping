"""
入荷機能 - ビュー

CSV ファイルからのデータ取り込み機能
入荷一覧表示＋バーコード出荷処理
"""

import logging
import os
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import and_
from werkzeug.utils import secure_filename

from factory_shipping.extensions import db
from factory_shipping.models import IntakeItem, Store, ShipmentLog
from factory_shipping.shipping.utils import parse_tag_barcode
from factory_shipping.intake.services import import_hanjow_csv

intake_bp = Blueprint('intake', __name__)
logger = logging.getLogger(__name__)


@intake_bp.route('/')
@login_required
def index():
    """入荷データ一覧（旧）"""
    items = IntakeItem.query.filter(
        IntakeItem.tag_number != ''
    ).filter(
        IntakeItem.tag_number.isnot(None)
    ).order_by(IntakeItem.created_at.desc()).limit(50).all()
    return render_template('intake/index.html', items=items)


@intake_bp.route('/list', methods=['GET', 'POST'])
@login_required
def list_items():
    """
    入荷一覧画面（ページング＋検索＋バーコード出荷対応）

    GET: 一覧表示
    POST: バーコード入力による出荷処理
    """
    # POST: バーコード出荷処理
    if request.method == 'POST':
        scanned_code = request.form.get('scanned_code', '').strip()

        if scanned_code:
            try:
                # バーコード処理を実行
                result = process_barcode_shipment(scanned_code)

                if result['success']:
                    flash(result['message'], 'success')
                else:
                    flash(result['message'], 'warning')

            except Exception as e:
                logger.error(f"バーコード処理エラー: {e}")
                flash(f'エラーが発生しました: {str(e)}', 'error')

        # POST後はGETにリダイレクト（PRGパターン）
        return redirect(url_for('intake.list_items', **request.args))

    # GET: 検索条件を取得
    store_code = request.args.get('store_code', '').strip()
    tag_number = request.args.get('tag_number', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    status = request.args.get('status', 'all')  # unshipped, all
    sort_by = request.args.get('sort_by', 'intake_date')  # intake_date, tag_number
    sort_order = request.args.get('sort_order', 'asc')  # asc, desc
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # クエリ構築
    query = IntakeItem.query

    # タグ番号が空でないレコードのみ表示
    query = query.filter(IntakeItem.tag_number != '').filter(IntakeItem.tag_number.isnot(None))

    # 出荷ステータスフィルタ
    if status == 'unshipped':
        query = query.filter(IntakeItem.is_shipped == False)

    # 店舗コードフィルタ
    if store_code:
        query = query.filter(IntakeItem.store_code == store_code)

    # タグ番号フィルタ（指定されたタグ番号以降を表示）
    if tag_number:
        # 0-000形式から元の形式に戻す（先頭の店舗番号の1桁目を追加）
        # 例: 0-123 -> 店舗コードの1桁目 + 0123
        tag_search = tag_number.replace('-', '')  # ハイフンを除去
        if store_code:
            # 店舗コードが指定されている場合、その店舗の形式で検索
            full_tag = store_code[0] + tag_search  # 店舗コードの1桁目 + タグ番号
            query = query.filter(IntakeItem.tag_number >= full_tag)
        else:
            # 店舗コードが指定されていない場合、タグ番号の部分一致で検索
            query = query.filter(IntakeItem.tag_number.like(f'%{tag_search}%'))

    # 預かり日フィルタ（from）
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(IntakeItem.intake_date >= date_from_obj)
        except ValueError:
            flash('日付（from）の形式が正しくありません', 'warning')

    # 預かり日フィルタ（to）
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(IntakeItem.intake_date <= date_to_obj)
        except ValueError:
            flash('日付（to）の形式が正しくありません', 'warning')

    # 並び順: sort_by と sort_order パラメータに基づいて並び替え
    if sort_by == 'tag_number':
        if sort_order == 'desc':
            query = query.order_by(IntakeItem.tag_number.desc(), IntakeItem.id.desc())
        else:
            query = query.order_by(IntakeItem.tag_number.asc(), IntakeItem.id.asc())
    else:  # デフォルトは intake_date
        if sort_order == 'desc':
            query = query.order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc())
        else:
            query = query.order_by(IntakeItem.intake_date.asc(), IntakeItem.id.asc())

    # ページネーション
    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    # 店舗一覧（検索フォーム用）
    stores = Store.query.filter_by(is_active=True).order_by(Store.store_code).all()

    return render_template(
        'intake/list.html',
        items=pagination.items,
        pagination=pagination,
        stores=stores,
        # 検索条件を保持
        search_params={
            'store_code': store_code,
            'tag_number': tag_number,
            'date_from': date_from,
            'date_to': date_to,
            'status': status,
            'sort_by': sort_by,
            'sort_order': sort_order,
            'per_page': per_page
        }
    )


def process_barcode_shipment(scanned_code: str) -> dict:
    """
    バーコードから出荷処理を実行する

    Args:
        scanned_code (str): 9桁のバーコード

    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        # バーコードから店舗コードとタグ番号を抽出
        store_code, tag_number = parse_tag_barcode(scanned_code)

    except ValueError as e:
        logger.warning(f"バーコードパースエラー: {scanned_code} - {e}")
        return {
            'success': False,
            'message': f'バーコードの形式が正しくありません: {str(e)}'
        }

    # 店舗を検索
    store = Store.query.filter_by(store_code=store_code).first()
    if not store:
        logger.warning(f"店舗が見つかりません: {store_code}")
        return {
            'success': False,
            'message': f'該当する店舗が見つかりません（店舗コード: {store_code}）'
        }

    # 未出荷の入荷データを検索
    intake_item = IntakeItem.query.filter(
        and_(
            IntakeItem.store_id == store.id,
            IntakeItem.tag_number == tag_number,
            IntakeItem.is_shipped == False
        )
    ).first()

    if not intake_item:
        # 該当データなし
        logger.warning(f"該当する入荷データが見つかりません: {store_code}/{tag_number}")

        # 既に出荷済みかチェック
        shipped_item = IntakeItem.query.filter(
            and_(
                IntakeItem.store_id == store.id,
                IntakeItem.tag_number == tag_number,
                IntakeItem.is_shipped == True
            )
        ).first()

        if shipped_item:
            return {
                'success': False,
                'message': f'このタグは既に出荷済みです（店舗: {store_code} / タグ: {tag_number}）'
            }
        else:
            return {
                'success': False,
                'message': f'該当する入荷データが見つかりません（店舗: {store_code} / タグ: {tag_number}）'
            }

    # トランザクション開始
    try:
        # 出荷処理
        now = datetime.utcnow()
        intake_item.is_shipped = True
        intake_item.shipped_at = now

        # 出荷ログを作成
        shipment_log = ShipmentLog(
            intake_item_id=intake_item.id,
            store_id=store.id,
            scanned_code=scanned_code,
            scanned_at=now,
            scanned_by_user_id=current_user.id if current_user.is_authenticated else None,
            status='completed'
        )
        db.session.add(shipment_log)

        db.session.commit()

        logger.info(f"出荷完了: {store_code}/{tag_number} - {intake_item.customer_name}")

        return {
            'success': True,
            'message': (
                f'出荷完了： 店舗 {store_code} / タグ {tag_number} / '
                f'顧客 {intake_item.customer_name or "（不明）"} 様 / '
                f'商品 {intake_item.product_name or "（不明）"}'
            )
        }

    except Exception as e:
        db.session.rollback()
        logger.error(f"出荷処理中にエラー: {e}")
        raise


@intake_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """CSV ファイルアップロード"""
    if request.method == 'POST':
        # 日付指定の取り込みかどうかをチェック
        import_date = request.form.get('import_date', '').strip()
        if import_date:
            # 日付指定の取り込み
            try:
                from datetime import datetime
                from pathlib import Path
                from factory_shipping.intake.services import import_hanjow_csv
                
                # 日付をパース
                dt = datetime.strptime(import_date, '%Y-%m-%d')
                date_str = dt.strftime('%Y%m%d')
                
                # ファイルパスを生成
                csv_dir = Path('/var/www/html/king-req/downloads_hanjow')
                csv_file = csv_dir / f'hanjow_{date_str}.csv'
                
                # ファイル存在チェック
                if not csv_file.exists():
                    flash(f'指定された日付のCSVファイルが見つかりません: {csv_file}', 'error')
                    return redirect(url_for('intake.upload'))
                
                # CSV 取り込み処理
                result = import_hanjow_csv(str(csv_file))
                
                # 成功メッセージ
                flash(
                    f'CSV ファイルの取り込みが完了しました（{import_date}）。'
                    f'新規作成: {result["created"]}件, '
                    f'スキップ: {result["skipped"]}件, '
                    f'エラー: {result["errors"]}件',
                    'success' if result['errors'] == 0 else 'warning'
                )
                
                return redirect(url_for('intake.list_items'))
                
            except ValueError as e:
                flash(f'日付の形式が正しくありません: {import_date} (YYYY-MM-DD形式)', 'error')
                return redirect(url_for('intake.upload'))
            except Exception as e:
                logger.error(f"日付指定CSV取り込みエラー: {e}")
                flash(f'CSV ファイルの取り込み中にエラーが発生しました: {str(e)}', 'error')
                return redirect(url_for('intake.upload'))
        
        # ファイルアップロード処理
        # ファイルがアップロードされているかチェック
        if 'csv_file' not in request.files:
            flash('ファイルが選択されていません', 'error')
            return redirect(url_for('intake.upload'))

        file = request.files['csv_file']

        # ファイル名が空でないかチェック
        if file.filename == '':
            flash('ファイルが選択されていません', 'error')
            return redirect(url_for('intake.upload'))

        # ファイル拡張子チェック
        if not file.filename.lower().endswith('.csv'):
            flash('CSV ファイルのみアップロード可能です', 'error')
            return redirect(url_for('intake.upload'))

        try:
            # アップロードフォルダのパスを取得
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)

            # 安全なファイル名を生成
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = os.path.join(upload_folder, f'{timestamp}_{filename}')

            # ファイルを保存
            file.save(filepath)

            # CSV 取り込み処理
            result = import_hanjow_csv(filepath)

            # 成功メッセージ
            flash(
                f'CSV ファイルの取り込みが完了しました。'
                f'新規作成: {result["created"]}件, '
                f'スキップ: {result["skipped"]}件, '
                f'エラー: {result["errors"]}件',
                'success' if result['errors'] == 0 else 'warning'
            )

            # 一時ファイルを削除（オプション）
            # os.remove(filepath)

            return redirect(url_for('intake.list_items'))

        except FileNotFoundError as e:
            logger.error(f"ファイルが見つかりません: {e}")
            flash(f'エラー: {str(e)}', 'error')
            return redirect(url_for('intake.upload'))

        except Exception as e:
            logger.error(f"CSV 取り込みエラー: {e}")
            flash(f'CSV ファイルの取り込み中にエラーが発生しました: {str(e)}', 'error')
            return redirect(url_for('intake.upload'))

    return render_template('intake/upload.html')


@intake_bp.route('/toggle-shipment/<int:item_id>', methods=['POST'])
@login_required
def toggle_shipment(item_id):
    """出荷状態をトグル（未出荷 ↔ 出荷済み）"""
    item = IntakeItem.query.get_or_404(item_id)
    
    try:
        now = datetime.utcnow()
        
        if item.is_shipped:
            # 出荷済み → 未出荷に戻す
            item.is_shipped = False
            item.shipped_at = None
            message = f'出荷状態を「未出荷」に変更しました（店舗: {item.store_code} / タグ: {item.tag_number}）'
            logger.info(f"出荷状態を未出荷に変更: {item.store_code}/{item.tag_number} by {current_user.username}")
        else:
            # 未出荷 → 出荷済みにする
            item.is_shipped = True
            item.shipped_at = now
            
            # 出荷ログを作成
            shipment_log = ShipmentLog(
                intake_item_id=item.id,
                store_id=item.store_id,
                scanned_code=f"{item.store_code}{item.tag_number}",  # 簡易バーコード
                scanned_at=now,
                scanned_by_user_id=current_user.id if current_user.is_authenticated else None,
                status='completed'
            )
            db.session.add(shipment_log)
            
            message = f'出荷状態を「出荷済み」に変更しました（店舗: {item.store_code} / タグ: {item.tag_number}）'
            logger.info(f"出荷状態を出荷済みに変更: {item.store_code}/{item.tag_number} by {current_user.username}")
        
        db.session.commit()
        
        # JSONレスポンスを返す（AJAX用）
        from flask import jsonify
        return jsonify({
            'success': True,
            'message': message,
            'is_shipped': item.is_shipped,
            'shipped_at': item.shipped_at.strftime('%Y-%m-%d %H:%M') if item.shipped_at else None
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"出荷状態変更エラー: {e}")
        from flask import jsonify
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500


@intake_bp.route('/detail/<int:item_id>')
@login_required
def detail(item_id):
    """入荷データ詳細"""
    item = IntakeItem.query.get_or_404(item_id)
    return render_template('intake/detail.html', item=item)


@intake_bp.route('/import-status', methods=['GET'])
@login_required
def import_status():
    """
    入荷データ（売上台帳ログ）取得状況画面
    
    横軸: 店舗一覧
    縦軸: 日付
    取得できている欄には〇を表示
    """
    try:
        from datetime import timedelta
        from sqlalchemy import func
        
        # 対象店舗の定義（順序を保証するためリストのタプルとして定義）
        target_stores = [
            ('0002', 'オザム日の出店'),
            ('0006', '栄町店'),
            ('0007', 'いなげや師岡店'),
            ('0008', '牛浜店'),
            ('0011', '本社青梅店'),
            ('0012', '東青梅店'),
            ('0013', '東福生店'),
            ('0014', '狭山ヶ丘店'),
            ('0016', 'いなげや福生店'),
            ('0019', 'ﾏﾙﾌｼﾞ千ヶ瀬店'),
            ('0020', 'オザム小作店'),
            ('0021', 'コープ新町店'),
            ('0022', '所沢狭山ヶ丘店'),
            ('0024', '秋川店'),
        ]
        
        # 辞書形式も作成（検索用）
        target_stores_dict = dict(target_stores)
        
        # 日付範囲の取得（デフォルトは過去30日）
        date_from_str = request.args.get('date_from', '').strip()
        date_to_str = request.args.get('date_to', '').strip()
        sort_order = request.args.get('sort_order', 'desc').strip()  # 'asc' または 'desc'
        
        # sort_orderの検証
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                flash('開始日付の形式が正しくありません', 'warning')
                date_from = (date.today() - timedelta(days=30))
        else:
            date_from = (date.today() - timedelta(days=30))
        
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                flash('終了日付の形式が正しくありません', 'warning')
                date_to = date.today()
        else:
            date_to = date.today()
        
        # 日付リストを生成（曜日情報付き）
        date_list = []
        current_date = date_from
        weekday_names = ['月', '火', '水', '木', '金', '土', '日']
        while current_date <= date_to:
            weekday_name = weekday_names[current_date.weekday()]
            date_list.append({
                'date': current_date,
                'weekday': weekday_name
            })
            current_date += timedelta(days=1)

        # 日付をソート順に応じてソート
        # descの場合は降順（新しい日付が上）、ascの場合は昇順（古い日付が上）
        date_list.sort(key=lambda x: x['date'], reverse=(sort_order == 'desc'))
        
        # 各日付×店舗の組み合わせでデータが存在するかを確認
        # クエリ: 店舗コードと日付ごとにデータが存在するか
        status_data = {}
        
        # 対象店舗コードのリスト
        target_store_codes = [code for code, name in target_stores]
        
        # データベースから各日付×店舗の組み合わせでデータが存在するかを取得
        # 効率的にクエリを実行するため、一度に全データを取得
        try:
            query = db.session.query(
                IntakeItem.store_code,
                IntakeItem.intake_date,
                func.count(IntakeItem.id).label('count')
            ).filter(
                IntakeItem.store_code.in_(target_store_codes),
                IntakeItem.intake_date >= date_from,
                IntakeItem.intake_date <= date_to,
                IntakeItem.tag_number != '',
                IntakeItem.tag_number.isnot(None)
            ).group_by(
                IntakeItem.store_code,
                IntakeItem.intake_date
            ).all()
            
            # 結果を辞書に格納
            for store_code, intake_date, count in query:
                if store_code not in status_data:
                    status_data[store_code] = {}
                status_data[store_code][intake_date] = count > 0
        except Exception as e:
            logger.error(f"データベースクエリエラー: {e}")
            flash(f'データ取得中にエラーが発生しました: {str(e)}', 'error')
        
        # 統計情報を計算
        total_cells = len(date_list) * len(target_stores)
        filled_cells = 0
        for store_code, store_name in target_stores:
            for date_item in date_list:
                target_date = date_item['date']
                if status_data.get(store_code, {}).get(target_date, False):
                    filled_cells += 1
        
        return render_template(
            'intake/import_status.html',
            target_stores=target_stores,
            date_list=date_list,
            status_data=status_data,
            date_from=date_from,
            date_to=date_to,
            date_from_str=date_from_str,
            date_to_str=date_to_str,
            today=date.today(),
            total_cells=total_cells,
            filled_cells=filled_cells,
            sort_order=sort_order
        )
    except Exception as e:
        logger.error(f"入荷データ取得状況画面エラー: {e}", exc_info=True)
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('intake.list_items'))
