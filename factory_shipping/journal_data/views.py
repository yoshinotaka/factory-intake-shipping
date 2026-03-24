"""
ジャーナルデータ操作 - ビュー

ジャーナルデータのCSV取得・取得状況確認機能（管理者専用）を提供します。
CRUD管理（一覧・作成・編集・削除）は admin ブループリントが担当します。
"""

import logging
import jpholiday
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from factory_shipping.extensions import db
from factory_shipping.models import JournalData, JournalDownloadNote
from factory_shipping.admin.decorators import admin_required
from datetime import datetime, date
from sqlalchemy import func
from factory_shipping.utils import now_jst

journal_data_bp = Blueprint('journal_data', __name__)
logger = logging.getLogger(__name__)


@journal_data_bp.route('/import-status', methods=['GET'])
@login_required
@admin_required
def journal_import_status():
    """
    ジャーナルデータ取得状況画面

    横軸: 店舗一覧
    縦軸: 日付
    取得できている欄には件数を表示
    """
    try:
        from datetime import timedelta

        # 臨時定休日（火曜日）の期間：2026-01-13〜2026-03-17（全店）
        temp_tuesday_start = date(2026, 1, 13)
        temp_tuesday_end = date(2026, 3, 17)

        # 閉店した店舗コード
        closed_store_codes = {'0016'}

        # 全対象店舗の定義（順序を保証するためリストのタプルとして定義）
        all_target_stores = [
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

        # 閉店店舗の表示切り替え（デフォルト: 非表示）
        show_closed = request.args.get('show_closed', '0') == '1'
        if show_closed:
            target_stores = all_target_stores
        else:
            target_stores = [(code, name) for code, name in all_target_stores if code not in closed_store_codes]

        # 辞書形式も作成（検索用）
        target_stores_dict = dict(target_stores)

        # 日付範囲の取得（デフォルトは2025年10月1日から今日まで）
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
                date_from = date(2025, 10, 1)  # 2025年10月1日
        else:
            date_from = date(2025, 10, 1)  # 2025年10月1日

        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                flash('終了日付の形式が正しくありません', 'warning')
                date_to = date.today()
        else:
            date_to = date.today()

        # 祝日（本社青梅店の定休日）- 表示期間内を jpholiday で動的に取得
        holiday_dates = frozenset(
            date_from + timedelta(days=i)
            for i in range((date_to - date_from).days + 1)
            if jpholiday.is_holiday(date_from + timedelta(days=i))
        )

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
        # クエリ: 店舗番号と日付ごとにデータが存在するか
        status_data = {}

        # 対象店舗コードのリスト
        target_store_codes = [code for code, name in target_stores]

        # データベースから各日付×店舗の組み合わせでデータが存在するかを取得
        # 効率的にクエリを実行するため、一度に全データを取得
        try:
            query = db.session.query(
                JournalData.store_no,
                JournalData.date,
                func.count(JournalData.id).label('count')
            ).filter(
                JournalData.store_no.in_(target_store_codes),
                JournalData.date >= date_from,
                JournalData.date <= date_to
            ).group_by(
                JournalData.store_no,
                JournalData.date
            ).all()

            # 結果を辞書に格納（件数も保持）
            for store_no, journal_date, count in query:
                if store_no not in status_data:
                    status_data[store_no] = {}
                status_data[store_no][journal_date] = {
                    'has_data': count > 0,
                    'count': count
                }
        except Exception as e:
            logger.error(f"データベースクエリエラー: {e}")
            flash(f'データ取得中にエラーが発生しました: {str(e)}', 'error')

        # 統計情報を計算
        total_cells = len(date_list) * len(target_stores)
        filled_cells = 0
        for store_code, store_name in target_stores:
            for date_item in date_list:
                target_date = date_item['date']
                cell_data = status_data.get(store_code, {}).get(target_date, {})
                if isinstance(cell_data, dict) and cell_data.get('has_data', False):
                    filled_cells += 1

        # メモデータを取得
        notes_data = {}
        try:
            notes_query = JournalDownloadNote.query.filter(
                JournalDownloadNote.date >= date_from,
                JournalDownloadNote.date <= date_to
            ).all()
            notes_data = {n.date: n.note for n in notes_query}
        except Exception as e:
            logger.warning(f"メモデータ取得エラー: {e}")

        return render_template(
            'admin/journal_import_status.html',
            target_stores=target_stores,
            date_list=date_list,
            status_data=status_data,
            notes_data=notes_data,
            date_from=date_from,
            date_to=date_to,
            date_from_str=date_from_str,
            date_to_str=date_to_str,
            today=date.today(),
            now=now_jst(),
            total_cells=total_cells,
            filled_cells=filled_cells,
            sort_order=sort_order,
            show_closed=show_closed,
            closed_store_codes=closed_store_codes,
            holiday_dates=holiday_dates,
            temp_tuesday_start=temp_tuesday_start,
            temp_tuesday_end=temp_tuesday_end
        )
    except Exception as e:
        logger.error(f"ジャーナルデータ取得状況画面エラー: {e}", exc_info=True)
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('admin.journal_data_list'))


@journal_data_bp.route('/fetch-csv-progress/<date_str>', methods=['GET'])
@login_required
@admin_required
def get_journal_csv_fetch_progress(date_str):
    """
    ジャーナルCSVダウンロードの進捗状況を取得

    バックグラウンドジョブの完了ステータスと、現在の実行分のログのみを返す。

    Args:
        date_str (str): 日付（YYYY-MM-DD形式）

    Returns:
        JSON: ログの最新行（今回の実行分のみ）と完了ステータス
    """
    import json as json_mod
    import re
    from datetime import datetime as dt
    try:
        from pathlib import Path

        # バックグラウンドジョブのステータスファイルを確認
        status_file = Path(f'/tmp/journal_fetch_status_{date_str}.json')
        final_status = None
        started_at = None
        if status_file.exists():
            try:
                data = json_mod.loads(status_file.read_text(encoding='utf-8'))
                started_at_str = data.get('started_at')
                if started_at_str:
                    try:
                        started_at = dt.fromisoformat(started_at_str)
                    except Exception:
                        pass
                if data.get('status') in ('success', 'error'):
                    final_status = data
            except Exception:
                pass

        # 今日のログファイルを探す
        today = dt.now().strftime('%Y%m%d')
        log_file = Path(f'/var/www/html/king-req/log_hanjow/journal_downloader_{today}.log')
        if not log_file.exists():
            return jsonify({
                'success': True,
                'logs': ['ダウンロード開始を待機中...'],
                'final_status': final_status
            })

        # ログを読み込み、今回の実行開始以降の行のみ抽出
        ts_pattern = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\]')
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            log_messages = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # started_at がある場合はタイムスタンプでフィルタ
                if started_at:
                    m = ts_pattern.match(line)
                    if m:
                        try:
                            line_ts = dt.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                            if line_ts < started_at:
                                continue
                        except Exception:
                            pass
                # タイムスタンプとログレベルを除去してメッセージ部分だけ抽出
                if ' - ' in line:
                    parts = line.split(' - ', 1)
                    if len(parts) > 1:
                        log_messages.append(parts[1].strip())
                else:
                    log_messages.append(line)

            # 最新20行のみ返す
            last_messages = log_messages[-20:] if len(log_messages) > 20 else log_messages

            # ステータスファイルの step_message があればログの末尾に追加
            if not final_status and status_file.exists():
                try:
                    _d = json_mod.loads(status_file.read_text(encoding='utf-8'))
                    step_msg = _d.get('step_message')
                    if step_msg:
                        last_messages = list(last_messages)
                        if not last_messages or last_messages[-1] != f'>>> {step_msg}':
                            last_messages.append(f'>>> {step_msg}')
                except Exception:
                    pass

            return jsonify({
                'success': True,
                'logs': last_messages if last_messages else ['ダウンロード開始を待機中...'],
                'final_status': final_status
            })
        except Exception as e:
            logger.error(f"ログファイル読み込みエラー: {e}")
            return jsonify({
                'success': False,
                'logs': [f'ログの読み込みに失敗しました: {str(e)}'],
                'final_status': final_status
            })

    except Exception as e:
        logger.error(f"進捗取得エラー: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'logs': [f'エラー: {str(e)}'],
            'final_status': None
        })


@journal_data_bp.route('/fetch-csv/<date_str>', methods=['POST'])
@login_required
@admin_required
def fetch_journal_csv_for_date(date_str):
    """
    指定日付のジャーナルCSVをバックグラウンドでダウンロードして取り込む

    DBを照会してデータが未取得の店舗のみをダウンロード対象とすることで、
    処理時間を短縮する。
    ダウンロード・変換・インポートは journal_fetch_runner.py がバックグラウンドで実行し、
    完了後に /tmp/journal_fetch_status_<date>.json にステータスを書き込む。
    フロントエンドは fetch-csv-progress エンドポイントをポーリングして完了を検知する。

    Args:
        date_str (str): 日付（YYYY-MM-DD形式）

    Returns:
        JSON: {"status": "started"} — 即時返却
    """
    import subprocess
    from pathlib import Path

    # 全対象店舗コード（journal_import_status と同一リスト）
    all_target_stores = [
        '0002', '0006', '0007', '0008', '0011', '0012', '0013',
        '0014', '0016', '0019', '0020', '0021', '0022', '0024',
    ]

    try:
        # 日付の妥当性チェック
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'message': f'日付の形式が正しくありません: {date_str}'
            }), 400

        # 未来の日付はエラー
        if target_date > date.today():
            return jsonify({
                'success': False,
                'message': f'未来の日付は指定できません: {date_str}'
            }), 400

        # DBから当日データが存在する店舗コードを取得し、未取得店舗だけを対象にする
        try:
            existing_rows = db.session.query(JournalData.store_no).filter(
                JournalData.date == target_date,
                JournalData.store_no.in_(all_target_stores)
            ).distinct().all()
            existing_stores = {r.store_no for r in existing_rows}
            missing_stores = [c for c in all_target_stores if c not in existing_stores]
        except Exception as e:
            logger.warning(f"店舗照会エラー（全店舗を対象にします）: {e}")
            missing_stores = all_target_stores

        if not missing_stores:
            return jsonify({
                'success': False,
                'message': f'{date_str} は全店舗のデータが既に取り込まれています'
            }), 400

        logger.info(
            f"ジャーナルCSVダウンロード開始（バックグラウンド）: {date_str} "
            f"対象店舗 {missing_stores} (ユーザー: {current_user.username})"
        )

        # ランナースクリプトのパス
        runner_script = Path('/var/www/html/factory-intake-shipping/scripts/journal_fetch_runner.py')
        venv_python = '/var/www/html/factory-intake-shipping/venv/bin/python'

        if not runner_script.exists():
            logger.error(f"ランナースクリプトが見つかりません: {runner_script}")
            return jsonify({
                'success': False,
                'message': 'ランナースクリプトが見つかりません'
            }), 500

        # 完了ステータスファイルのパス（古いファイルを削除してからジョブ開始）
        status_file = f'/tmp/journal_fetch_status_{date_str}.json'
        try:
            Path(status_file).unlink(missing_ok=True)
        except Exception:
            pass

        # バックグラウンドプロセスとして起動（Flask ワーカーをブロックしない）
        # missing_stores を引数として渡し、不要な店舗のダウンロードをスキップ
        try:
            subprocess.Popen(
                [venv_python, str(runner_script), date_str, status_file] + missing_stores,
                cwd='/var/www/html/factory-intake-shipping',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True   # Flask のプロセスグループから切り離す
            )
        except Exception as e:
            logger.error(f"バックグラウンドプロセス起動エラー: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'バックグラウンドプロセスの起動に失敗しました: {str(e)}'
            }), 500

        return jsonify({
            'status': 'started',
            'message': (
                f'{date_str} のジャーナルCSVダウンロードを開始しました。'
                f'対象店舗: {len(missing_stores)}店舗。完了まで数分かかります。'
            )
        })

    except Exception as e:
        logger.error(f"ジャーナルCSVダウンロード開始エラー: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500


@journal_data_bp.route('/note/<date_str>', methods=['POST'])
@login_required
@admin_required
def save_journal_download_note(date_str):
    """
    指定日付のジャーナルダウンロードメモを保存（空文字で削除）

    JSON body: {"note": "メモ内容"}

    Args:
        date_str (str): 日付（YYYY-MM-DD形式）

    Returns:
        JSON: {"success": true, "action": "saved"|"deleted"}
    """
    try:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': f'日付の形式が正しくありません: {date_str}'}), 400

        data = request.get_json()
        note_text = (data.get('note') or '').strip() if data else ''

        existing = JournalDownloadNote.query.get(target_date)
        if not note_text:
            if existing:
                db.session.delete(existing)
                db.session.commit()
                logger.info(f"ジャーナルメモ削除: {date_str} (ユーザー: {current_user.username})")
            return jsonify({'success': True, 'action': 'deleted'})

        if existing:
            existing.note = note_text
            existing.created_by = current_user.username
        else:
            db.session.add(JournalDownloadNote(
                date=target_date,
                note=note_text,
                created_by=current_user.username
            ))
        db.session.commit()
        logger.info(f"ジャーナルメモ保存: {date_str} (ユーザー: {current_user.username})")
        return jsonify({'success': True, 'action': 'saved'})

    except Exception as e:
        logger.error(f"ジャーナルメモ保存エラー: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'message': f'エラーが発生しました: {str(e)}'}), 500
