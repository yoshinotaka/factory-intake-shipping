"""
monitoring機能 - ビュー

cronジョブの実行状況を確認し、ログファイルを表示する機能
"""

import logging
import os
from datetime import datetime, date, timedelta
from factory_shipping.utils import now_jst
from flask import Blueprint, render_template, request, current_app, url_for, redirect, jsonify
from flask_login import login_required
from factory_shipping.models import IntakeItem, JournalData, Store
from sqlalchemy import func

monitoring_bp = Blueprint('monitoring', __name__)
logger = logging.getLogger(__name__)

# cronジョブの設定
CRON_JOBS = [
    {
        'name': 'hanjow CSV 自動取り込み',
        'schedule': '毎日 22:35',
        'log_file': '/var/log/factory-shipping/auto-import.log',
        'error_log_file': '/var/log/factory-shipping/auto-import-error.log',
        'script': '/var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh'
    },
    {
        'name': 'hanjow CSV ダウンロード（king-req）',
        'schedule': '毎日 22:30',
        'log_file': '/var/www/html/king-req/log_cron/hanjow_downloader.log',
        'error_log_file': None,
        'script': '/var/www/html/king-req/hanjow_csv_downloader.py'
    },
    {
        'name': 'ジャーナルデータ抽出（CSV変換）',
        'schedule': '毎日 22:50',
        'log_file': '/var/www/html/king-req/log_cron/extract_journal_data.log',
        'error_log_file': None,
        'script': '/var/www/html/king-req/run_extract_journal_data.sh'
    },
    {
        'name': 'ジャーナルデータDB取り込み',
        'schedule': '毎日 23:00',
        'log_file': '/var/log/factory-shipping/import-journal.log',
        'error_log_file': None,
        'script': '/var/www/html/factory-intake-shipping/run.py'
    },
    {
        'name': 'ジャーナルCSVダウンロード（半蔵）',
        'schedule': '毎日 22:45',
        'log_file': '/var/www/html/king-req/log_cron/hanjow_journal_downloader.log',
        'error_log_file': None,
        'script': '/var/www/html/king-req/hanjow_journal_downloader.py'
    },
    {
        'name': 'ジャーナルデータDB自動取り込み',
        'schedule': '毎日 23:00',
        'log_file': '/var/log/factory-shipping/import-journal.log',
        'error_log_file': None,
        'script': '/var/www/html/factory-intake-shipping/run.py import-journal'
    }
]

# アプリケーションログの設定
APP_LOGS = [
    {
        'name': 'アプリケーションログ（エラー・警告）',
        'log_file': '/var/log/factory-shipping/error.log',
        'description': 'Flaskアプリケーションのエラーログと警告ログ'
    },
    {
        'name': 'アクセスログ',
        'log_file': '/var/log/factory-shipping/access.log',
        'description': 'HTTPアクセスログ（Gunicorn）'
    },
    {
        'name': 'hanjow ダウンロード詳細ログ（本日）',
        'log_file': f'/var/www/html/king-req/log_hanjow/hanjow_downloader_{now_jst().strftime("%Y%m%d")}.log',
        'description': 'Selenium WebDriverによるCSVダウンロードの詳細ログ'
    }
]


def get_file_last_modified(file_path):
    """ファイルの最終更新時刻を取得"""
    try:
        if os.path.exists(file_path):
            return datetime.fromtimestamp(os.path.getmtime(file_path))
        return None
    except Exception as e:
        logger.error(f"ファイル更新時刻取得エラー: {file_path} - {e}")
        return None


def get_file_size(file_path):
    """ファイルサイズを取得"""
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0
    except Exception as e:
        logger.error(f"ファイルサイズ取得エラー: {file_path} - {e}")
        return 0


def check_job_status(job):
    """ジョブの実行状況を確認"""
    log_file = job['log_file']
    error_log_file = job.get('error_log_file')
    
    status = {
        'name': job['name'],
        'schedule': job['schedule'],
        'log_file': log_file,
        'error_log_file': error_log_file,
        'last_run': None,
        'log_size': 0,
        'error_log_size': 0,
        'has_error': False,
        'status': 'unknown'  # 'success', 'error', 'unknown', 'not_run'
    }
    
    # ログファイルの最終更新時刻を確認
    last_modified = get_file_last_modified(log_file)
    if last_modified:
        status['last_run'] = last_modified
        status['log_size'] = get_file_size(log_file)
    
    # エラーログファイルの確認
    if error_log_file and os.path.exists(error_log_file):
        error_last_modified = get_file_last_modified(error_log_file)
        status['error_log_size'] = get_file_size(error_log_file)
        
        # エラーログがログファイルより新しい場合はエラーと判断
        if error_last_modified and last_modified:
            if error_last_modified > last_modified:
                status['has_error'] = True
                status['status'] = 'error'
            else:
                status['status'] = 'success'
        elif error_last_modified:
            status['has_error'] = True
            status['status'] = 'error'
    
    # ステータス判定
    if not last_modified:
        status['status'] = 'not_run'
    elif status['status'] == 'unknown':
        # ログファイルの内容を確認してエラーがないかチェック
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    # 最後の数行を確認
                    lines = f.readlines()
                    if lines:
                        last_lines = ''.join(lines[-10:])
                        if 'ERROR' in last_lines or 'エラー' in last_lines or 'error' in last_lines.lower():
                            status['has_error'] = True
                            status['status'] = 'error'
                        else:
                            status['status'] = 'success'
            except Exception as e:
                logger.error(f"ログファイル読み込みエラー: {log_file} - {e}")
                status['status'] = 'unknown'
    
    return status


@monitoring_bp.route('/')
@login_required
def index():
    """monitoringページ - cronジョブの実行状況一覧"""
    try:
        jobs_status = []
        for job in CRON_JOBS:
            status = check_job_status(job)
            jobs_status.append(status)

        # アプリケーションログの情報を収集
        app_logs_status = []
        for log_config in APP_LOGS:
            log_file = log_config['log_file']
            log_status = {
                'name': log_config['name'],
                'description': log_config['description'],
                'log_file': log_file,
                'exists': os.path.exists(log_file),
                'last_modified': get_file_last_modified(log_file) if os.path.exists(log_file) else None,
                'size': get_file_size(log_file) if os.path.exists(log_file) else 0
            }
            app_logs_status.append(log_status)

        return render_template('monitoring/index.html', jobs=jobs_status, app_logs=app_logs_status)
    except Exception as e:
        logger.error(f"monitoringページエラー: {e}", exc_info=True)
        from flask import flash, redirect, url_for
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('main.index'))


@monitoring_bp.route('/log/<int:job_index>')
@login_required
def view_log(job_index):
    """ログファイルの内容を表示（最終100行）"""
    try:
        if job_index < 0 or job_index >= len(CRON_JOBS):
            from flask import flash, redirect
            flash('無効なジョブインデックスです', 'error')
            return redirect(url_for('monitoring.index'))
        
        job = CRON_JOBS[job_index]
        log_file = job['log_file']
        
        # ログファイルの存在確認
        if not os.path.exists(log_file):
            from flask import flash, redirect
            flash('ログファイルが見つかりません', 'error')
            return redirect(url_for('monitoring.index'))
        
        # ログファイルの最終100行を読み込む
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # 最終100行を取得
                last_lines = lines[-100:] if len(lines) > 100 else lines
                log_content = ''.join(last_lines)
        except Exception as e:
            logger.error(f"ログファイル読み込みエラー: {log_file} - {e}")
            from flask import flash, redirect
            flash(f'ログファイルの読み込みに失敗しました: {str(e)}', 'error')
            return redirect(url_for('monitoring.index'))
        
        # ファイル情報
        file_info = {
            'path': log_file,
            'size': get_file_size(log_file),
            'last_modified': get_file_last_modified(log_file),
            'total_lines': len(lines),
            'displayed_lines': len(last_lines)
        }
        
        return render_template(
            'monitoring/log_viewer.html',
            job=job,
            log_content=log_content,
            file_info=file_info
        )
    except Exception as e:
        logger.error(f"ログ表示エラー: {e}", exc_info=True)
        from flask import flash, redirect
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('monitoring.index'))


@monitoring_bp.route('/error-log/<int:job_index>')
@login_required
def view_error_log(job_index):
    """エラーログファイルの内容を表示（最終100行）"""
    try:
        if job_index < 0 or job_index >= len(CRON_JOBS):
            from flask import flash, redirect
            flash('無効なジョブインデックスです', 'error')
            return redirect(url_for('monitoring.index'))
        
        job = CRON_JOBS[job_index]
        error_log_file = job.get('error_log_file')
        
        if not error_log_file:
            from flask import flash, redirect
            flash('エラーログファイルが設定されていません', 'error')
            return redirect(url_for('monitoring.index'))
        
        # エラーログファイルの存在確認
        if not os.path.exists(error_log_file):
            from flask import flash, redirect
            flash('エラーログファイルが見つかりません', 'error')
            return redirect(url_for('monitoring.index'))
        
        # エラーログファイルの最終100行を読み込む
        try:
            with open(error_log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # 最終100行を取得
                last_lines = lines[-100:] if len(lines) > 100 else lines
                log_content = ''.join(last_lines)
        except Exception as e:
            logger.error(f"エラーログファイル読み込みエラー: {error_log_file} - {e}")
            from flask import flash, redirect
            flash(f'エラーログファイルの読み込みに失敗しました: {str(e)}', 'error')
            return redirect(url_for('monitoring.index'))
        
        # ファイル情報
        file_info = {
            'path': error_log_file,
            'size': get_file_size(error_log_file),
            'last_modified': get_file_last_modified(error_log_file),
            'total_lines': len(lines),
            'displayed_lines': len(last_lines)
        }
        
        return render_template(
            'monitoring/log_viewer.html',
            job=job,
            log_content=log_content,
            file_info=file_info,
            is_error_log=True
        )
    except Exception as e:
        logger.error(f"エラーログ表示エラー: {e}", exc_info=True)
        from flask import flash, redirect
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('monitoring.index'))


@monitoring_bp.route('/app-log/<int:log_index>')
@login_required
def view_app_log(log_index):
    """アプリケーションログファイルの内容を表示（最終200行）"""
    try:
        if log_index < 0 or log_index >= len(APP_LOGS):
            from flask import flash, redirect
            flash('無効なログインデックスです', 'error')
            return redirect(url_for('monitoring.index'))

        log_config = APP_LOGS[log_index]
        log_file = log_config['log_file']

        # ログファイルの存在確認
        if not os.path.exists(log_file):
            from flask import flash, redirect
            flash('ログファイルが見つかりません', 'error')
            return redirect(url_for('monitoring.index'))

        # ログファイルの最終200行を読み込む
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # 最終200行を取得
                last_lines = lines[-200:] if len(lines) > 200 else lines
                log_content = ''.join(last_lines)
        except Exception as e:
            logger.error(f"ログファイル読み込みエラー: {log_file} - {e}")
            from flask import flash, redirect
            flash(f'ログファイルの読み込みに失敗しました: {str(e)}', 'error')
            return redirect(url_for('monitoring.index'))

        # ファイル情報
        file_info = {
            'path': log_file,
            'size': get_file_size(log_file),
            'last_modified': get_file_last_modified(log_file),
            'total_lines': len(lines),
            'displayed_lines': len(last_lines)
        }

        # ログ情報（job形式に合わせる）
        log_info = {
            'name': log_config['name'],
            'log_file': log_file,
            'schedule': log_config.get('description', '')
        }

        return render_template(
            'monitoring/log_viewer.html',
            job=log_info,
            log_content=log_content,
            file_info=file_info,
            is_app_log=True
        )
    except Exception as e:
        logger.error(f"アプリケーションログ表示エラー: {e}", exc_info=True)
        from flask import flash, redirect
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('monitoring.index'))


def _build_import_status_data(days: int = 14) -> dict:
    """入荷データ・仕訳データの店舗別取込み状況を構築する"""
    today = date.today()
    start_date = today - timedelta(days=days - 1)
    dates = [start_date + timedelta(days=i) for i in range(days)]
    date_strs = [d.strftime('%Y-%m-%d') for d in dates]

    # ---- 入荷データ（IntakeItem × Store マスタ）----
    stores = Store.query.filter_by(is_active=True).order_by(Store.store_code).all()
    intake_rows = (
        IntakeItem.query
        .with_entities(IntakeItem.intake_date, IntakeItem.store_code, func.count().label('cnt'))
        .filter(IntakeItem.intake_date >= start_date, IntakeItem.intake_date <= today)
        .group_by(IntakeItem.intake_date, IntakeItem.store_code)
        .all()
    )
    intake_done = {(r.intake_date.strftime('%Y-%m-%d'), r.store_code) for r in intake_rows if r.cnt > 0}

    intake_status = {}
    for d in date_strs:
        intake_status[d] = {s.store_code: (d, s.store_code) in intake_done for s in stores}

    intake_summary = {
        'stores': [{'code': s.store_code, 'name': s.store_name} for s in stores],
        'dates': date_strs,
        'status': intake_status,
        'date_stats': [
            {
                'date': d,
                'ok': sum(1 for s in stores if intake_status[d].get(s.store_code)),
                'total': len(stores),
            }
            for d in date_strs
        ],
    }

    # ---- 仕訳データ（JournalData × 過去登場 store_no）----
    since_master = today - timedelta(days=60)
    expected_store_nos = sorted({
        r[0] for r in
        JournalData.query
            .with_entities(JournalData.store_no)
            .filter(JournalData.date >= since_master)
            .distinct().all()
    })

    journal_rows = (
        JournalData.query
        .with_entities(JournalData.date, JournalData.store_no, func.count().label('cnt'))
        .filter(JournalData.date >= start_date, JournalData.date <= today)
        .group_by(JournalData.date, JournalData.store_no)
        .all()
    )
    journal_done = {(r.date.strftime('%Y-%m-%d'), r.store_no) for r in journal_rows if r.cnt > 0}

    journal_status = {}
    for d in date_strs:
        journal_status[d] = {sno: (d, sno) in journal_done for sno in expected_store_nos}

    journal_summary = {
        'store_nos': expected_store_nos,
        'dates': date_strs,
        'status': journal_status,
        'date_stats': [
            {
                'date': d,
                'ok': sum(1 for sno in expected_store_nos if journal_status[d].get(sno)),
                'total': len(expected_store_nos),
            }
            for d in date_strs
        ],
    }

    return {
        'intake': intake_summary,
        'journal': journal_summary,
        'days': days,
        'today': today.strftime('%Y-%m-%d'),
    }


@monitoring_bp.route('/import-status')
@login_required
def import_status():
    """入荷データ・仕訳データの取込み状況ページ"""
    try:
        days = int(request.args.get('days', 14))
        days = max(3, min(days, 60))
        data = _build_import_status_data(days)
        return render_template('monitoring/import_status.html', data=data)
    except Exception as e:
        logger.error(f"import-statusページエラー: {e}", exc_info=True)
        from flask import flash
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('monitoring.index'))


@monitoring_bp.route('/api/import-status')
@login_required
def api_import_status():
    """取込み状況JSON API"""
    try:
        days = int(request.args.get('days', 14))
        days = max(3, min(days, 60))
        data = _build_import_status_data(days)
        return jsonify(data)
    except Exception as e:
        logger.error(f"api/import-statusエラー: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500













