"""
monitoring機能 - ビュー

cronジョブの実行状況を確認し、ログファイルを表示する機能
"""

import logging
import os
from datetime import datetime
from flask import Blueprint, render_template, request, current_app
from flask_login import login_required

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
        
        return render_template('monitoring/index.html', jobs=jobs_status)
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
