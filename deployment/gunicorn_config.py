"""
Gunicorn 設定ファイル

使い方:
    gunicorn -c deployment/gunicorn_config.py 'factory_shipping:create_app()'
"""

import os
import multiprocessing

# プロジェクトルート
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# バインドアドレス
# Unix ソケットを使用する場合（推奨）
bind = os.environ.get('GUNICORN_BIND', f'unix:{BASE_DIR}/gunicorn.sock')

# TCP ポートを使用する場合
# bind = '127.0.0.1:8000'

# ワーカー数（推奨: CPU コア数 × 2 + 1）
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

# ワーカークラス（同期/非同期）
worker_class = 'sync'  # sync, gevent, eventlet など

# タイムアウト（秒）
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))

# KeepAlive
keepalive = 5

# ログ設定
accesslog = '/var/log/factory-shipping/access.log'
errorlog = '/var/log/factory-shipping/error.log'
loglevel = 'info'

# プロセス名
proc_name = 'factory-shipping'

# デーモン化（systemd を使う場合は False）
daemon = False

# PID ファイル（systemd を使う場合は不要）
# pidfile = f'{BASE_DIR}/gunicorn.pid'

# 一時ディレクトリ
worker_tmp_dir = '/dev/shm'

# リクエストヘッダーサイズ上限
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# リクエストボディサイズ上限（0 = 無制限）
# 注意: Flask の MAX_CONTENT_LENGTH と合わせること
limit_request_body = 0

# 最大リクエスト数（ワーカーの自動再起動）
max_requests = 1000
max_requests_jitter = 50

# プリロード（アプリケーションをフォーク前にロード）
preload_app = True

# グレースフルシャットダウンのタイムアウト
graceful_timeout = 30


def on_starting(server):
    """サーバー起動時のフック"""
    print(f"Gunicorn が起動しました: {bind}")


def on_reload(server):
    """リロード時のフック"""
    print("Gunicorn がリロードされました")


def worker_int(worker):
    """ワーカーが SIGINT を受信した時のフック"""
    print(f"ワーカー {worker.pid} が中断されました")


def post_fork(server, worker):
    """ワーカープロセスがフォークされた後のフック"""
    print(f"ワーカー {worker.pid} が起動しました")
