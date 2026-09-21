"""顧客利用状況分析 API のセキュリティ層

設計要件:
  - 別システム https://kingdrysystem.com からのみアクセス許可
  - API キー (環境変数 ANALYTICS_API_KEY) で認証
  - 失敗は最小限の情報のみ返却 (列挙攻撃を回避)
  - 監査ログを log/analytics_api_audit.log に出力
  - 1 IP あたり 60req/min、1 キーあたり 300req/min のスライディングウィンドウ
"""

from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from collections import deque
from functools import wraps
from logging.handlers import RotatingFileHandler
from typing import Deque, Tuple
from urllib.parse import urlparse

from flask import current_app, g, jsonify, request

# ---------------------------------------------------------------------------
# 定数 / 設定
# ---------------------------------------------------------------------------

# 別システムからのアクセスを許可するオリジン (Origin / Referer ヘッダで検証)
ALLOWED_ORIGIN = 'https://kingdrysystem.com'
ALLOWED_ORIGIN_HOST = urlparse(ALLOWED_ORIGIN).netloc  # "kingdrysystem.com"

# 環境変数で追加オリジンを許可する場合 (カンマ区切り)
_EXTRA_ORIGINS_ENV = os.environ.get('ANALYTICS_API_EXTRA_ORIGINS', '').strip()
EXTRA_ORIGIN_HOSTS = {
    urlparse(o.strip()).netloc
    for o in _EXTRA_ORIGINS_ENV.split(',')
    if o.strip()
}

# レート制限
RATE_LIMIT_PER_IP_PER_MIN = int(os.environ.get('ANALYTICS_API_RATE_IP', '60'))
RATE_LIMIT_PER_KEY_PER_MIN = int(os.environ.get('ANALYTICS_API_RATE_KEY', '300'))
RATE_WINDOW_SEC = 60

# ページネーション上限 (DoS 防止)
MAX_PAGE_SIZE = 1000
DEFAULT_PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# 監査ログ (専用ローテーションファイル)
# ---------------------------------------------------------------------------

_audit_logger: logging.Logger | None = None


def _get_audit_logger() -> logging.Logger:
    global _audit_logger
    if _audit_logger is not None:
        return _audit_logger

    logger = logging.getLogger('analytics_api.audit')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_dir = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        'log',
    )
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'analytics_api_audit.log')

    handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=14,
        encoding='utf-8',
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s\t%(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z',
    ))
    logger.addHandler(handler)

    _audit_logger = logger
    return logger


def _audit(event: str, **fields) -> None:
    """監査ログを TSV 形式で書き出す。"""
    parts = [event]
    for k, v in fields.items():
        parts.append(f'{k}={v}')
    _get_audit_logger().info('\t'.join(parts))


# ---------------------------------------------------------------------------
# レート制限 (プロセス内インメモリ、スライディングウィンドウ)
#
# 注: gunicorn ワーカーごとに独立。複数ワーカー構成では Redis に移行すること。
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_rate_buckets: dict[str, Deque[float]] = {}


def _rate_check(bucket_key: str, limit: int) -> Tuple[bool, int]:
    """指定バケットでレート制限に引っかかるか判定。

    Returns:
        (allowed, retry_after_seconds)
    """
    if limit <= 0:
        return True, 0
    now = time.monotonic()
    cutoff = now - RATE_WINDOW_SEC
    with _rate_lock:
        q = _rate_buckets.setdefault(bucket_key, deque())
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            retry_after = max(1, int(RATE_WINDOW_SEC - (now - q[0])))
            return False, retry_after
        q.append(now)
    return True, 0


# ---------------------------------------------------------------------------
# 認証 / オリジン検証ヘルパー
# ---------------------------------------------------------------------------

def _get_expected_api_key() -> str | None:
    """環境変数から API キーを取得。未設定時は None。"""
    key = os.environ.get('ANALYTICS_API_KEY', '').strip()
    return key or None


def _extract_bearer_token() -> str | None:
    """Authorization ヘッダから Bearer トークンを抽出。"""
    auth = request.headers.get('Authorization', '')
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    return parts[1].strip() or None


def _check_origin_allowed() -> Tuple[bool, str]:
    """Origin または Referer が許可ホストと一致するか確認。

    どちらか少なくとも一方が一致すれば OK。両方欠落時は拒否。
    """
    allowed_hosts = {ALLOWED_ORIGIN_HOST} | EXTRA_ORIGIN_HOSTS

    origin = request.headers.get('Origin', '').strip()
    referer = request.headers.get('Referer', '').strip()

    if origin:
        if urlparse(origin).scheme != 'https':
            return False, 'origin_not_https'
        if urlparse(origin).netloc in allowed_hosts:
            return True, ''
        return False, 'origin_mismatch'

    if referer:
        ref = urlparse(referer)
        if ref.scheme != 'https':
            return False, 'referer_not_https'
        if ref.netloc in allowed_hosts:
            return True, ''
        return False, 'referer_mismatch'

    # Origin/Referer どちらも無い場合は拒否
    return False, 'origin_missing'


def _client_ip() -> str:
    """nginx 後段の X-Forwarded-For を尊重したクライアント IP 取得。

    本番 nginx で `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`
    を設定している前提。
    """
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or 'unknown'


# ---------------------------------------------------------------------------
# デコレータ
# ---------------------------------------------------------------------------

def require_analytics_api_auth(view_func):
    """全 API エンドポイントに付与する複合セキュリティデコレータ。

    順序:
      1. HTTPS 確認 (X-Forwarded-Proto)
      2. Origin/Referer 検証
      3. API キー認証
      4. レート制限
    途中で失敗したら以降の検査をスキップして即座に拒否。
    監査ログは成功/失敗を問わず記録。
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        ip = _client_ip()
        path = request.path
        method = request.method

        # 1. HTTPS 必須
        proto = request.headers.get('X-Forwarded-Proto', request.scheme)
        if proto != 'https' and not current_app.debug:
            _audit('reject_https', ip=ip, path=path)
            return jsonify({'error': 'https_required'}), 400

        # 2. Origin / Referer 検証
        origin_ok, origin_reason = _check_origin_allowed()
        if not origin_ok:
            _audit(
                'reject_origin',
                ip=ip,
                path=path,
                reason=origin_reason,
                origin=request.headers.get('Origin', ''),
                referer=request.headers.get('Referer', ''),
            )
            return jsonify({'error': 'forbidden_origin'}), 403

        # 3. API キー認証 (定数時間比較)
        expected = _get_expected_api_key()
        if not expected:
            _audit('reject_no_server_key', ip=ip, path=path)
            return jsonify({'error': 'server_misconfigured'}), 503

        presented = _extract_bearer_token()
        if not presented:
            _audit('reject_no_token', ip=ip, path=path)
            return jsonify({'error': 'unauthorized'}), 401

        if not hmac.compare_digest(presented, expected):
            _audit('reject_bad_token', ip=ip, path=path)
            return jsonify({'error': 'unauthorized'}), 401

        # 4. レート制限
        key_id = _short_key_id(presented)
        ok_ip, retry_ip = _rate_check(f'ip:{ip}', RATE_LIMIT_PER_IP_PER_MIN)
        if not ok_ip:
            _audit('reject_rate_ip', ip=ip, path=path, retry=retry_ip)
            resp = jsonify({'error': 'rate_limited'})
            resp.headers['Retry-After'] = str(retry_ip)
            return resp, 429
        ok_key, retry_key = _rate_check(f'key:{key_id}', RATE_LIMIT_PER_KEY_PER_MIN)
        if not ok_key:
            _audit('reject_rate_key', ip=ip, path=path, key=key_id, retry=retry_key)
            resp = jsonify({'error': 'rate_limited'})
            resp.headers['Retry-After'] = str(retry_key)
            return resp, 429

        # 認証成功 — リクエストコンテキストに記録
        g.analytics_api_key_id = key_id
        g.analytics_api_client_ip = ip

        _audit('accept', ip=ip, path=path, method=method, key=key_id)
        return view_func(*args, **kwargs)

    return wrapper


def _short_key_id(key: str) -> str:
    """ログ用の安全なキー識別子 (生キーは記録しない)。"""
    import hashlib
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]


# ---------------------------------------------------------------------------
# CORS 付加レスポンス
# ---------------------------------------------------------------------------

def add_cors_headers(response):
    """許可オリジンに対してのみ CORS ヘッダを付与する after_request 用ヘルパ。

    Origin ヘッダがマッチしない場合は何も付与しない (= ブロック)。
    """
    origin = request.headers.get('Origin', '').strip()
    if not origin:
        return response
    allowed_hosts = {ALLOWED_ORIGIN_HOST} | EXTRA_ORIGIN_HOSTS
    if urlparse(origin).netloc not in allowed_hosts:
        return response
    response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Vary'] = 'Origin'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
    response.headers['Access-Control-Max-Age'] = '600'
    # クレデンシャル付き fetch は許可しない (Cookie 共有を防ぐ)
    return response
