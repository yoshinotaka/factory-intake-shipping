"""
出荷機能 - ビュー

バーコードスキャンによる出荷処理
"""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import and_, func, desc
from factory_shipping.extensions import db, socketio
from factory_shipping.models import IntakeItem, ShipmentLog, Store, ItemStatus, FactoryOperator
from factory_shipping.shipping.utils import parse_tag_barcode
from datetime import datetime
from factory_shipping.utils import now_jst, get_next_history_number, normalize_tag_number_for_search

shipping_bp = Blueprint('shipping', __name__)
logger = logging.getLogger(__name__)


@shipping_bp.route('/')
@login_required
def index():
    """出荷スキャン画面"""
    return render_template('shipping/index.html')


@shipping_bp.route('/scan', methods=['POST'])
@login_required
def scan():
    """バーコードスキャン処理（API）"""
    scanned_code = request.json.get('code')

    if not scanned_code:
        return jsonify({'error': 'スキャンコードが空です'}), 400

    # TODO: スキャンコードから商品を検索し、出荷処理を実行
    # ここでは簡易的な実装例

    # 商品検索（未出荷 = status_idがshipped以外）
    shipped_status = ItemStatus.query.filter_by(status_code='shipped').first()
    if not shipped_status:
        return jsonify({'error': '出荷済み状態が見つかりません'}), 500
    
    item = IntakeItem.query.filter(
        IntakeItem.item_code == scanned_code,
        IntakeItem.status_id != shipped_status.id,
        IntakeItem.in_business_scope(),
    ).order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc()).first()

    if not item:
        return jsonify({'error': '該当する入荷データが見つかりません'}), 404

    # 出荷ログを作成
    log = ShipmentLog(
        intake_item_id=item.id,
        store_id=item.store_id,
        scanned_by_user_id=current_user.id,
        scanned_code=scanned_code,
        status='completed',
        new_status_id=shipped_status.id
    )

    # 入荷データを出荷済みに更新
    item.status_id = shipped_status.id
    item.shipped_at = now_jst()

    db.session.add(log)
    db.session.commit()

    return jsonify({
        'success': True,
        'item': {
            'code': item.item_code,
            'name': item.item_name,
            'store': item.store.store_name
        }
    })


@shipping_bp.route('/history')
@login_required
def history():
    """出荷履歴"""
    logs = ShipmentLog.query.order_by(ShipmentLog.scanned_at.desc()).limit(100).all()
    return render_template('shipping/history.html', logs=logs)


@shipping_bp.route('/process', methods=['GET', 'POST'])
@login_required
def process():
    """
    出荷処理画面

    バーコードスキャンまたは手動入力で出荷処理を行い、
    セッション内で処理したアイテムのみを表示する

    GET: 処理済みアイテム一覧表示
    POST: バーコード入力による出荷処理
    """
    # セッションから処理済みアイテムIDリストを取得（初回は空）
    if 'processed_items' not in session:
        session['processed_items'] = []
        session.modified = True

    # POST: バーコード出荷処理
    if request.method == 'POST':
        scanned_code = request.form.get('scanned_code', '').strip()
        operator_id = request.form.get('operator_id', '').strip()

        # 担当者IDをバリデーション（フォームから渡されなければセッションから取得）
        if operator_id and operator_id.isdigit():
            operator_id = int(operator_id)
        else:
            operator_id = session.get('operator_id')  # セッションから取得

        if scanned_code:
            try:
                # バーコード処理を実行（担当者IDを渡す）
                result = process_barcode_shipment_for_screen(scanned_code, operator_id)

                if result['success']:
                    flash(result['message'], 'success')
                    # セッションに処理済みアイテムIDを追加
                    if 'item' in result and result['item']:
                        processed_items = session.get('processed_items', [])
                        if result['item'].id not in processed_items:
                            processed_items.append(result['item'].id)
                            session['processed_items'] = processed_items
                            session.modified = True
                else:
                    flash(result['message'], 'warning')

            except Exception as e:
                logger.error(f"バーコード処理エラー: {e}")
                flash(f'エラーが発生しました: {str(e)}', 'error')

        # POST後はGETにリダイレクト（PRGパターン）
        # 絞り込みパラメータを保持してリダイレクト
        redirect_args = {}
        if request.args.get('filter_store'):
            redirect_args['filter_store'] = request.args.get('filter_store')
        if request.args.get('filter_tag'):
            redirect_args['filter_tag'] = request.args.get('filter_tag')
        if request.args.get('filter_product'):
            redirect_args['filter_product'] = request.args.get('filter_product')
        if request.args.get('filter_status'):
            redirect_args['filter_status'] = request.args.get('filter_status')
        if request.args.get('show_latest_only'):
            redirect_args['show_latest_only'] = request.args.get('show_latest_only')

        return redirect(url_for('shipping.process', **redirect_args))

    # GET: 出荷ログを取得
    processed_item_ids = session.get('processed_items', [])
    items = []

    # 絞り込みパラメータを取得
    filter_store = request.args.get('filter_store', '').strip()
    filter_tag = request.args.get('filter_tag', '').strip()
    filter_product = request.args.get('filter_product', '').strip()
    filter_status = request.args.get('filter_status', '').strip()

    # 表示モードを取得（クエリパラメータまたはセッションから）
    show_latest_only_param = request.args.get('show_latest_only', '')
    if show_latest_only_param != '':
        # クエリパラメータが指定されている場合はそれを使用
        show_latest_only = show_latest_only_param.lower() == 'true'
        session['show_latest_only'] = show_latest_only
        session.modified = True
        logger.info(f"表示モード変更: show_latest_only={show_latest_only} (パラメータ: {show_latest_only_param})")
    else:
        # クエリパラメータがない場合はセッションから取得（デフォルトはTrue=最新のみ表示）
        show_latest_only = session.get('show_latest_only', True)
        logger.info(f"表示モード取得: show_latest_only={show_latest_only} (セッションから)")

    # 全出荷ログを取得（管理画面と同じクエリ）
    if show_latest_only:
        # 店舗コード+タグ番号の組み合わせごとに最新のログのみを取得
        # サブクエリで各店舗コード+タグ番号の最新scanned_atを取得
        subquery = db.session.query(
            ShipmentLog.store_code,
            ShipmentLog.tag_number,
            func.max(ShipmentLog.scanned_at).label('max_scanned_at')
        ).filter(
            ShipmentLog.store_code.isnot(None),
            ShipmentLog.tag_number.isnot(None)
        ).group_by(
            ShipmentLog.store_code,
            ShipmentLog.tag_number
        ).subquery()

        # 最新のログを取得（同じscanned_atの場合はidが最大のものを取得）
        all_latest_logs = db.session.query(ShipmentLog).join(
            subquery,
            and_(
                ShipmentLog.store_code == subquery.c.store_code,
                ShipmentLog.tag_number == subquery.c.tag_number,
                ShipmentLog.scanned_at == subquery.c.max_scanned_at
            )
        ).all()

        # 同じ店舗コード+タグ番号で複数のログがある場合（同じscanned_at）、idが最大のものを選択
        latest_logs_dict = {}
        for log in all_latest_logs:
            # 店舗コード+タグ番号をキーとして使用
            key = f"{log.store_code or ''}|{log.tag_number or ''}"
            if key not in latest_logs_dict:
                latest_logs_dict[key] = log
            elif log.id > latest_logs_dict[key].id:
                latest_logs_dict[key] = log

        logs = sorted(latest_logs_dict.values(), key=lambda x: x.scanned_at, reverse=True)
        logger.info(f"最新のみ表示モード: {len(logs)}件のログを取得（店舗+タグ番号でグループ化）")
    else:
        # 全ログを取得（管理画面と同じクエリを使用）
        logs = ShipmentLog.query.order_by(desc(ShipmentLog.scanned_at)).all()
        logger.info(f"全ログ表示モード: {len(logs)}件のログを取得")

    # 絞り込み処理を適用
    if filter_store or filter_tag or filter_product or filter_status:
        filtered_logs = []
        for log in logs:
            # 店舗コードで絞り込み
            if filter_store:
                if not log.store_code or filter_store.lower() not in log.store_code.lower():
                    continue

            # タグ番号で絞り込み
            if filter_tag:
                if not log.tag_number or filter_tag.lower() not in log.tag_number.lower():
                    continue

            # 商品名で絞り込み
            if filter_product:
                product_name = log.intake_item.product_name if log.intake_item else ''
                if not product_name or filter_product.lower() not in product_name.lower():
                    continue

            # 状態で絞り込み
            if filter_status:
                if not log.new_status_id or str(log.new_status_id) != filter_status:
                    continue

            filtered_logs.append(log)

        logs = filtered_logs
        logger.info(f"絞り込み適用後: {len(logs)}件のログ")
    
    # 処理済みアイテム情報（必要に応じて）
    if processed_item_ids:
        items = IntakeItem.query.filter(
            IntakeItem.id.in_(processed_item_ids)
        ).order_by(IntakeItem.shipped_at.desc()).all()

    # 店舗一覧（手動入力フォーム用）
    stores = Store.query.filter_by(is_active=True).order_by(Store.store_code).all()

    # 状態一覧（状態変更用）
    statuses = ItemStatus.query.filter_by(is_active=True).order_by(ItemStatus.display_order).all()

    # 担当者一覧（出荷処理用）
    operators = FactoryOperator.query.filter_by(is_active=True).order_by(FactoryOperator.operator_code).all()

    return render_template(
        'shipping/process.html',
        items=items,
        logs=logs,
        stores=stores,
        statuses=statuses,
        operators=operators,
        processed_count=len(processed_item_ids),
        show_latest_only=show_latest_only,
        filter_store=filter_store,
        filter_tag=filter_tag,
        filter_product=filter_product,
        filter_status=filter_status
    )


def process_barcode_shipment_for_screen(scanned_code: str, operator_id: int = None) -> dict:
    """
    バーコードから出荷処理を実行する（出荷処理画面用）

    Args:
        scanned_code (str): 9桁のバーコード
        operator_id (int): 担当者ID（任意）

    Returns:
        dict: {'success': bool, 'message': str, 'item': IntakeItem or None}
    """
    try:
        # バーコードから店舗コードとタグ番号を抽出
        store_code, tag_number = parse_tag_barcode(scanned_code)

    except ValueError as e:
        logger.warning(f"バーコードパースエラー: {scanned_code} - {e}")
        return {
            'success': False,
            'message': f'バーコードの形式が正しくありません: {str(e)}',
            'item': None
        }

    # 店舗コードを4桁に変換
    if len(store_code) == 3 and store_code.isdigit():
        store_code = '0' + store_code
    elif len(store_code) == 2 and store_code.isdigit():
        store_code = '00' + store_code

    # 店舗を検索
    store = Store.query.filter_by(store_code=store_code).first()
    if not store:
        logger.warning(f"店舗が見つかりません: {store_code}")
        return {
            'success': False,
            'message': f'該当する店舗が見つかりません（店舗コード: {store_code}）',
            'item': None
        }

    # タグ番号を複数の形式に正規化して検索
    tag_search_patterns = normalize_tag_number_for_search(tag_number)

    # 出荷済み状態を取得
    shipped_status = ItemStatus.query.filter_by(status_code='shipped').first()
    if not shipped_status:
        return {
            'success': False,
            'message': '出荷済み状態が見つかりません。データベースの初期設定を確認してください。',
            'item': None
        }

    # 未出荷の入荷データを検索（status_idが出荷済み以外）
    intake_item = None
    for pattern in tag_search_patterns:
        intake_item = IntakeItem.query.filter(
            and_(
                IntakeItem.store_id == store.id,
                IntakeItem.tag_number == pattern,
                IntakeItem.status_id != shipped_status.id,
                IntakeItem.in_business_scope(),  # 過去分（2025-09 以前）は出荷しない
            )
        ).order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc()).first()
        if intake_item:
            logger.debug(f"タグ番号マッチ: 検索パターン={pattern}, DB値={intake_item.tag_number}")
            break

    if not intake_item:
        # 該当データなし
        logger.warning(f"該当する入荷データが見つかりません: {store_code}/{tag_number}")

        # 既に出荷済みかチェック
        shipped_item = None
        for pattern in tag_search_patterns:
            shipped_item = IntakeItem.query.filter(
                and_(
                    IntakeItem.store_id == store.id,
                    IntakeItem.tag_number == pattern,
                    IntakeItem.status_id == shipped_status.id,
                    IntakeItem.in_business_scope(),
                )
            ).order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc()).first()
            if shipped_item:
                break

        if shipped_item:
            return {
                'success': False,
                'message': f'このタグは既に出荷済みです（店舗: {store_code} / タグ: {tag_number}）',
                'item': None
            }
        else:
            return {
                'success': False,
                'message': f'該当する入荷データが見つかりません（店舗: {store_code} / タグ: {tag_number}）',
                'item': None
            }

    # トランザクション開始
    try:
        # 出荷処理
        now = now_jst()
        intake_item.shipped_at = now
        intake_item.status_id = shipped_status.id  # 状態を更新

        # 履歴番号を取得
        history_number = get_next_history_number(
            intake_item.store_code,
            intake_item.intake_date,
            intake_item.tag_number
        )

        # 出荷ログを作成（状態変更履歴）
        shipment_log = ShipmentLog(
            intake_item_id=intake_item.id,
            store_id=store.id,
            store_code=intake_item.store_code,  # 複合キー
            intake_date=intake_item.intake_date,  # 複合キー
            tag_number=intake_item.tag_number,  # 複合キー
            history_number=history_number,  # 履歴番号
            scanned_code=scanned_code,
            scanned_at=now,
            scanned_by_user_id=current_user.id if current_user.is_authenticated else None,
            operator_id=operator_id,  # 担当者ID
            status='completed',
            new_status_id=shipped_status.id  # 変更後の状態
        )
        db.session.add(shipment_log)

        db.session.commit()

        logger.info(f"出荷完了: {store_code}/{tag_number} - {intake_item.customer_name}")

        # WebSocketで全クライアントに出荷完了を通知
        socketio.emit('shipment_updated', {
            'item_id': intake_item.id,
            'store_code': intake_item.store_code,
            'tag_number': intake_item.tag_number,
            'formatted_tag_number': intake_item.get_formatted_tag_number(),
            'status_id': intake_item.status_id,
            'status_code': shipped_status.status_code,
            'status_name': shipped_status.status_name,
            'product_name': intake_item.product_name,
            'intake_date': intake_item.intake_date.strftime('%Y-%m-%d') if intake_item.intake_date else None,
            'shipped_at': intake_item.shipped_at.strftime('%Y-%m-%d %H:%M:%S') if intake_item.shipped_at else None,
            'shipped_at_short': intake_item.shipped_at.strftime('%Y-%m-%d %H:%M') if intake_item.shipped_at else None
        })

        return {
            'success': True,
            'message': (
                f'出荷完了： 店舗 {store_code} / タグ {tag_number} / '
                f'受付日 {intake_item.intake_date.strftime("%Y-%m-%d") if intake_item.intake_date else "（不明）"} / '
                f'商品 {intake_item.product_name or "（不明）"}'
            ),
            'item': intake_item
        }

    except Exception as e:
        db.session.rollback()
        logger.error(f"出荷処理中にエラー: {e}")
        raise


@shipping_bp.route('/change-status/<int:item_id>', methods=['POST'])
@login_required
def change_status(item_id):
    """
    商品の状態を変更し、ShipmentLogに履歴を記録

    Args:
        item_id (int): 商品ID

    Returns:
        JSON: {'success': bool, 'message': str}
    """
    try:
        # リクエストから新しい状態IDを取得
        new_status_id = request.json.get('status_id')
        notes = request.json.get('notes', '')

        if not new_status_id:
            return jsonify({'success': False, 'message': '状態が指定されていません'}), 400

        # 商品を取得
        item = IntakeItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'message': '該当する商品が見つかりません'}), 404

        # 新しい状態を取得
        new_status = ItemStatus.query.get(new_status_id)
        if not new_status:
            return jsonify({'success': False, 'message': '該当する状態が見つかりません'}), 404

        # 現在の状態と同じ場合はスキップ
        if item.status_id == new_status_id:
            return jsonify({
                'success': False,
                'message': f'既に「{new_status.status_name}」状態です'
            }), 400

        # トランザクション開始
        now = now_jst()

        # 商品の状態を更新
        old_status_id = item.status_id
        item.status_id = new_status_id
        item.shipped_at = now  # 最新の状態変更日時を更新

        # 履歴番号を取得
        history_number = get_next_history_number(
            item.store_code,
            item.intake_date,
            item.tag_number
        )

        # セッションから担当者を取得
        operator_id = session.get('operator_id')

        # ShipmentLogに履歴を記録
        log = ShipmentLog(
            intake_item_id=item.id,
            store_id=item.store_id,
            store_code=item.store_code,  # 複合キー
            intake_date=item.intake_date,  # 複合キー
            tag_number=item.tag_number,  # 複合キー
            history_number=history_number,  # 履歴番号
            scanned_code=None,  # 手動変更なのでNULL
            scanned_at=now,
            scanned_by_user_id=current_user.id,
            operator_id=operator_id,  # セッションから取得した担当者ID
            status='completed',
            new_status_id=new_status_id,
            notes=notes or f'手動で状態を変更: {new_status.status_name}'
        )
        db.session.add(log)

        db.session.commit()

        logger.info(
            f"状態変更完了: Item#{item_id} {item.store_code}/{item.tag_number} "
            f"- {new_status.status_name} (User: {current_user.username})"
        )

        # WebSocketで全クライアントに状態変更を通知
        socketio.emit('shipment_updated', {
            'item_id': item.id,
            'store_code': item.store_code,
            'tag_number': item.tag_number,
            'formatted_tag_number': item.get_formatted_tag_number(),
            'status_id': item.status_id,
            'status_code': new_status.status_code,
            'status_name': new_status.status_name,
            'product_name': item.product_name,
            'intake_date': item.intake_date.strftime('%Y-%m-%d') if item.intake_date else None,
            'shipped_at': item.shipped_at.strftime('%Y-%m-%d %H:%M:%S') if item.shipped_at else None,
            'shipped_at_short': item.shipped_at.strftime('%Y-%m-%d %H:%M') if item.shipped_at else None
        })

        return jsonify({
            'success': True,
            'message': f'状態を「{new_status.status_name}」に変更しました',
            'item': {
                'id': item.id,
                'status_id': item.status_id,
                'status_name': new_status.status_name
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"状態変更エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500
