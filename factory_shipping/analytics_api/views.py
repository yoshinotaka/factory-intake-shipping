"""顧客利用状況分析 API のエンドポイント (GET のみ・読み取り専用)。

すべて /fi/api/v1/analytics/ 配下にマウントされる。
詳細は docs/ANALYTICS_API.md を参照。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from flask import jsonify, request
from sqlalchemy import func

from factory_shipping.analytics_api import analytics_api_bp
from factory_shipping.analytics_api.security import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    add_cors_headers,
    require_analytics_api_auth,
)
from factory_shipping.extensions import db
from factory_shipping.models import IntakeItem, ItemStatus, Store

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# 期間の指定が無いときに全期間（2021-01〜）を部分一致・集計しないための既定の期間（日）。
# /customers/search と /stats/products だけに使う（kinglinesystem は期間なしで呼ばない。2026-09-21 確認）。
DEFAULT_PERIOD_DAYS = 365


def _default_from_date(from_date, to_date):
    """from_date も to_date も無ければ、今日から DEFAULT_PERIOD_DAYS 日前を返す。"""
    if from_date or to_date:
        return from_date
    return datetime.now(JST).date() - timedelta(days=DEFAULT_PERIOD_DAYS)


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------

def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'invalid date format: {value}')


def _clamp_pagination() -> tuple[int, int]:
    """limit / offset を取得してクランプ。"""
    try:
        limit = int(request.args.get('limit', DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = DEFAULT_PAGE_SIZE
    try:
        offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(MAX_PAGE_SIZE, limit))
    offset = max(0, offset)
    return limit, offset


def _serialize_item(item: IntakeItem) -> dict:
    """IntakeItem を API レスポンス用 dict に変換。"""
    # 返却済（returned_at あり）は工場側の状態より優先する（intake/returns.py 参照）
    status_code, status_name = item.display_status
    return {
        'id': item.id,
        'store_code': item.store_code,
        'store_name': item.store_name,
        'slip_number': item.slip_number,
        'tag_number': item.tag_number,
        'line_seq': item.line_seq,
        'product_name': item.product_name,
        'customer_name': item.customer_name,
        'customer_code': item.customer_code,
        'amount': item.amount,
        'quantity': item.quantity,
        'intake_date': item.intake_date.isoformat() if item.intake_date else None,
        'scheduled_date': item.scheduled_date.isoformat() if item.scheduled_date else None,
        'intake_status': item.intake_status,
        'status_code': status_code,
        'status_name': status_name,
        'shipped_at': item.shipped_at.isoformat() if item.shipped_at else None,
        # DB は JST の naive datetime。利用側で迷わないようオフセット付きで返す
        'returned_at': item.returned_at.replace(tzinfo=JST).isoformat() if item.returned_at else None,
        'wrapping': item.wrapping,
        'shipping_method': item.shipping_method,
        'imported_at': item.imported_at.isoformat() if item.imported_at else None,
    }


def _apply_common_filters(query, *, from_date, to_date, store_code, intake_status):
    if from_date:
        query = query.filter(IntakeItem.intake_date >= from_date)
    if to_date:
        query = query.filter(IntakeItem.intake_date <= to_date)
    if store_code:
        query = query.filter(IntakeItem.store_code == store_code)
    if intake_status:
        query = query.filter(IntakeItem.intake_status == intake_status)
    return query


def _error(message: str, code: int = 400):
    return jsonify({'error': message}), code


# ---------------------------------------------------------------------------
# CORS preflight (OPTIONS)
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/<path:_unused>', methods=['OPTIONS'])
@analytics_api_bp.route('/', methods=['OPTIONS'])
def preflight(_unused: str = ''):
    """CORS preflight 用。許可オリジンのみ ACAO を返す (after_request で付与)。"""
    return ('', 204)


@analytics_api_bp.after_request
def _attach_cors(response):
    return add_cors_headers(response)


# ---------------------------------------------------------------------------
# ヘルスチェック (認証あり / DB を軽く確認)
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/health', methods=['GET'])
@require_analytics_api_auth
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat() + 'Z'})
    except Exception:
        logger.exception('analytics_api health check failed')
        return _error('db_unavailable', 503)


# ---------------------------------------------------------------------------
# 1. 店舗マスタ
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/stores', methods=['GET'])
@require_analytics_api_auth
def list_stores():
    rows = (
        Store.query
        .filter_by(is_active=True)
        .order_by(Store.store_code.asc())
        .all()
    )
    return jsonify({
        'count': len(rows),
        'items': [
            {'store_code': s.store_code, 'store_name': s.store_name}
            for s in rows
        ],
    })


# ---------------------------------------------------------------------------
# 2. 入荷品一覧 (フィルタ + ページネーション)
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/intake-items', methods=['GET'])
@require_analytics_api_auth
def list_intake_items():
    """汎用の intake_items 検索。
    クエリパラメータ:
      from_date, to_date  -- 預り日範囲 (YYYY-MM-DD)
      store_code          -- 店舗コード
      intake_status       -- 入荷状態 ("通常" 等)
      customer_name       -- 顧客名 (完全一致)
      customer_code       -- 顧客コード (完全一致、12 桁)
      limit, offset       -- ページネーション
    """
    try:
        from_date = _parse_date(request.args.get('from_date'))
        to_date = _parse_date(request.args.get('to_date'))
    except ValueError as e:
        return _error(str(e))

    store_code = (request.args.get('store_code') or '').strip() or None
    intake_status = (request.args.get('intake_status') or '').strip() or None
    customer_name = (request.args.get('customer_name') or '').strip() or None
    customer_code = (request.args.get('customer_code') or '').strip() or None
    limit, offset = _clamp_pagination()

    q = IntakeItem.query
    q = _apply_common_filters(
        q,
        from_date=from_date,
        to_date=to_date,
        store_code=store_code,
        intake_status=intake_status,
    )
    if customer_name:
        q = q.filter(IntakeItem.customer_name == customer_name)
    if customer_code:
        q = q.filter(IntakeItem.customer_code == customer_code)

    total = q.with_entities(func.count(IntakeItem.id)).scalar()
    rows = (
        q.order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc())
         .limit(limit)
         .offset(offset)
         .all()
    )
    return jsonify({
        'total': int(total or 0),
        'limit': limit,
        'offset': offset,
        'items': [_serialize_item(r) for r in rows],
    })


# ---------------------------------------------------------------------------
# 3. 顧客検索 (部分一致 + 集計)
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/customers/search', methods=['GET'])
@require_analytics_api_auth
def search_customers():
    """顧客名で部分一致検索。来店回数と最終来店日も返す。

    クエリパラメータ:
      q              -- 検索文字列 (必須、最低 1 文字)
      from_date, to_date -- 集計対象期間。どちらも無ければ直近 1 年（部分一致は索引が効かないため）
      store_code     -- 店舗フィルタ
      limit, offset

    visit_count は来店回数 = (店舗, 預り日) のユニーク数。品目数は item_count。
    """
    q_str = (request.args.get('q') or '').strip()
    if not q_str:
        return _error('q is required')
    if len(q_str) > 100:
        return _error('q too long')

    try:
        from_date = _parse_date(request.args.get('from_date'))
        to_date = _parse_date(request.args.get('to_date'))
    except ValueError as e:
        return _error(str(e))

    store_code = (request.args.get('store_code') or '').strip() or None
    limit, offset = _clamp_pagination()
    from_date = _default_from_date(from_date, to_date)

    # 部分一致。autoescape で q 中の % と _ はワイルドカードではなく文字として扱う
    filtered = IntakeItem.query.filter(
        IntakeItem.customer_name.isnot(None),
        IntakeItem.customer_name.contains(q_str, autoescape=True),
    )
    filtered = _apply_common_filters(
        filtered,
        from_date=from_date,
        to_date=to_date,
        store_code=store_code,
        intake_status=None,
    )

    # まず来店 (顧客 × 店舗 × 預り日) 単位に畳み、その上で顧客ごとに集計する。
    # 同じ日に何品目出しても来店は 1 回と数えるため。
    visits = (
        filtered.with_entities(
            IntakeItem.customer_name.label('customer_name'),
            IntakeItem.intake_date.label('intake_date'),
            func.count(IntakeItem.id).label('item_count'),
            func.sum(IntakeItem.amount).label('total_amount'),
        )
        .group_by(IntakeItem.customer_name, IntakeItem.store_code, IntakeItem.intake_date)
        .subquery()
    )
    last_visit = func.max(visits.c.intake_date)
    per_customer = db.session.query(
        visits.c.customer_name.label('customer_name'),
        func.count().label('visit_count'),
        func.sum(visits.c.item_count).label('item_count'),
        func.sum(visits.c.total_amount).label('total_amount'),
        func.min(visits.c.intake_date).label('first_intake_date'),
        last_visit.label('last_intake_date'),
    ).group_by(visits.c.customer_name)

    # GROUP BY 付きのクエリに .scalar() すると、顧客が 2 名以上ヒットした時点で
    # MultipleResultsFound になる。件数はグループ化した結果を数える。
    total = per_customer.count()
    rows = (
        per_customer.order_by(last_visit.desc(), visits.c.customer_name.asc())
            .limit(limit)
            .offset(offset)
            .all()
    )

    items = [
        {
            'customer_name': r.customer_name,
            'visit_count': int(r.visit_count or 0),
            'item_count': int(r.item_count or 0),
            'total_amount': int(r.total_amount or 0),
            'first_intake_date': r.first_intake_date.isoformat() if r.first_intake_date else None,
            'last_intake_date': r.last_intake_date.isoformat() if r.last_intake_date else None,
        }
        for r in rows
    ]
    return jsonify({
        'query': q_str,
        'total': int(total or 0),
        'limit': limit,
        'offset': offset,
        'items': items,
    })


# ---------------------------------------------------------------------------
# 4. 顧客サマリ
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/customers/summary', methods=['GET'])
@require_analytics_api_auth
def customer_summary():
    """指定顧客の利用統計を返す。

    クエリパラメータ:
      customer_name (必須) -- 完全一致
      from_date, to_date
      store_code

    回数の定義:
      visit_count -- 来店回数 = (店舗, 預り日) のユニーク数
      slip_count  -- 伝票数   = (店舗, 預り日, 伝票No) のユニーク数
      item_count  -- 品目数   = 明細行数
    """
    customer_name = (request.args.get('customer_name') or '').strip()
    if not customer_name:
        return _error('customer_name is required')
    if len(customer_name) > 100:
        return _error('customer_name too long')

    try:
        from_date = _parse_date(request.args.get('from_date'))
        to_date = _parse_date(request.args.get('to_date'))
    except ValueError as e:
        return _error(str(e))

    store_code = (request.args.get('store_code') or '').strip() or None

    q = IntakeItem.query.filter(IntakeItem.customer_name == customer_name)
    q = _apply_common_filters(
        q,
        from_date=from_date,
        to_date=to_date,
        store_code=store_code,
        intake_status=None,
    )

    visit_days_expr = func.count(func.distinct(IntakeItem.intake_date))
    agg = q.with_entities(
        func.count(IntakeItem.id),
        func.sum(IntakeItem.amount),
        func.sum(IntakeItem.quantity),
        func.min(IntakeItem.intake_date),
        func.max(IntakeItem.intake_date),
        visit_days_expr,
    ).one()
    item_count, total_amount, total_quantity, first_date, last_date, visit_days = agg

    # 来店回数: 同じ店舗・同じ預り日の品目は、何品目・何伝票でも 1 回と数える
    visit_count = (
        q.with_entities(IntakeItem.store_code, IntakeItem.intake_date)
        .distinct()
        .count()
    )
    # 伝票数: 伝票No の無い旧データは、同じ店舗・同じ預り日の分を 1 伝票とみなす
    # (SELECT DISTINCT は NULL 同士を同一視する)
    slip_count = (
        q.with_entities(IntakeItem.store_code, IntakeItem.intake_date, IntakeItem.slip_number)
        .distinct()
        .count()
    )

    # 店舗別来店回数 TOP 5 (店舗内では 預り日のユニーク数 = 来店回数)
    stores_rows = (
        q.with_entities(
            IntakeItem.store_code,
            IntakeItem.store_name,
            visit_days_expr.label('visits'),
            func.count(IntakeItem.id).label('cnt'),
            func.sum(IntakeItem.amount).label('amt'),
        )
        .group_by(IntakeItem.store_code, IntakeItem.store_name)
        .order_by(
            visit_days_expr.desc(),
            func.count(IntakeItem.id).desc(),
            IntakeItem.store_code.asc(),
        )
        .limit(5)
        .all()
    )

    # 商品別利用回数 TOP 5
    products_rows = (
        q.with_entities(
            IntakeItem.product_name,
            func.count(IntakeItem.id).label('cnt'),
        )
        .filter(IntakeItem.product_name.isnot(None))
        .group_by(IntakeItem.product_name)
        .order_by(func.count(IntakeItem.id).desc())
        .limit(5)
        .all()
    )

    # 平均来店間隔 (日数)。来店日 (ユニークな預り日) ベース。
    # 品目数で割ると、同じ日に複数品目を出した顧客ほど間隔が短く出てしまう。
    avg_interval_days: Optional[float] = None
    if first_date and last_date and visit_days and visit_days > 1:
        span = (last_date - first_date).days
        avg_interval_days = round(span / (visit_days - 1), 2)

    return jsonify({
        'customer_name': customer_name,
        'visit_count': int(visit_count or 0),
        'slip_count': int(slip_count or 0),
        'item_count': int(item_count or 0),
        'total_amount': int(total_amount or 0),
        'total_quantity': int(total_quantity or 0),
        'first_intake_date': first_date.isoformat() if first_date else None,
        'last_intake_date': last_date.isoformat() if last_date else None,
        'avg_interval_days': avg_interval_days,
        'top_stores': [
            {
                'store_code': r.store_code,
                'store_name': r.store_name,
                'visit_count': int(r.visits or 0),
                'item_count': int(r.cnt or 0),
                'total_amount': int(r.amt or 0),
            }
            for r in stores_rows
        ],
        'top_products': [
            {'product_name': r.product_name, 'count': int(r.cnt or 0)}
            for r in products_rows
        ],
    })


# ---------------------------------------------------------------------------
# 5. 顧客の利用履歴 (intake_items の明細)
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/customers/history', methods=['GET'])
@require_analytics_api_auth
def customer_history():
    """指定顧客の利用明細を新しい順で返す。

    クエリパラメータ:
      customer_name -- 完全一致
      customer_code -- 完全一致（12 桁）。customer_name とどちらか一方は必須。両方あれば両方で絞る
      from_date, to_date -- 無ければ全期間（(customer_name|customer_code, intake_date) の索引で引く）
      store_code
      limit, offset
    """
    customer_name = (request.args.get('customer_name') or '').strip()
    customer_code = (request.args.get('customer_code') or '').strip()
    if not customer_name and not customer_code:
        return _error('customer_name or customer_code is required')
    if len(customer_name) > 100:
        return _error('customer_name too long')
    if len(customer_code) > 20:
        return _error('customer_code too long')

    try:
        from_date = _parse_date(request.args.get('from_date'))
        to_date = _parse_date(request.args.get('to_date'))
    except ValueError as e:
        return _error(str(e))

    store_code = (request.args.get('store_code') or '').strip() or None
    limit, offset = _clamp_pagination()

    q = IntakeItem.query
    if customer_name:
        q = q.filter(IntakeItem.customer_name == customer_name)
    if customer_code:
        q = q.filter(IntakeItem.customer_code == customer_code)
    q = _apply_common_filters(
        q,
        from_date=from_date,
        to_date=to_date,
        store_code=store_code,
        intake_status=None,
    )

    total = q.with_entities(func.count(IntakeItem.id)).scalar()
    rows = (
        q.order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc())
         .limit(limit)
         .offset(offset)
         .all()
    )
    return jsonify({
        'customer_name': customer_name or None,
        'customer_code': customer_code or None,
        'total': int(total or 0),
        'limit': limit,
        'offset': offset,
        'items': [_serialize_item(r) for r in rows],
    })


# ---------------------------------------------------------------------------
# 6. 日次サマリ (グラフ化用)
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/stats/daily', methods=['GET'])
@require_analytics_api_auth
def daily_stats():
    """日別の入荷件数・売上合計・ユニーク顧客数を返す。

    クエリパラメータ:
      from_date (必須), to_date (必須) -- 最大 366 日
      store_code
    """
    try:
        from_date = _parse_date(request.args.get('from_date'))
        to_date = _parse_date(request.args.get('to_date'))
    except ValueError as e:
        return _error(str(e))

    if not from_date or not to_date:
        return _error('from_date and to_date are required')
    if to_date < from_date:
        return _error('to_date must be >= from_date')
    if (to_date - from_date).days > 366:
        return _error('date range too wide (max 366 days)')

    store_code = (request.args.get('store_code') or '').strip() or None

    q = db.session.query(
        IntakeItem.intake_date.label('d'),
        func.count(IntakeItem.id).label('cnt'),
        func.sum(IntakeItem.amount).label('amt'),
        func.count(func.distinct(IntakeItem.customer_name)).label('customers'),
    ).filter(
        IntakeItem.intake_date >= from_date,
        IntakeItem.intake_date <= to_date,
    )
    if store_code:
        q = q.filter(IntakeItem.store_code == store_code)
    q = q.group_by(IntakeItem.intake_date).order_by(IntakeItem.intake_date.asc())

    rows = q.all()
    return jsonify({
        'from_date': from_date.isoformat(),
        'to_date': to_date.isoformat(),
        'store_code': store_code,
        'series': [
            {
                'date': r.d.isoformat(),
                'item_count': int(r.cnt or 0),
                'total_amount': int(r.amt or 0),
                'unique_customers': int(r.customers or 0),
            }
            for r in rows
        ],
    })


# ---------------------------------------------------------------------------
# 7. 商品分類別サマリ
# ---------------------------------------------------------------------------

@analytics_api_bp.route('/stats/products', methods=['GET'])
@require_analytics_api_auth
def product_stats():
    """商品名別の取扱件数・売上合計の TOP N を返す。

    クエリパラメータ:
      from_date, to_date -- どちらも無ければ直近 1 年
      store_code
      limit (default 50, max 500)
    """
    try:
        from_date = _parse_date(request.args.get('from_date'))
        to_date = _parse_date(request.args.get('to_date'))
    except ValueError as e:
        return _error(str(e))

    store_code = (request.args.get('store_code') or '').strip() or None
    from_date = _default_from_date(from_date, to_date)

    try:
        limit = int(request.args.get('limit', 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(500, limit))

    q = db.session.query(
        IntakeItem.product_name,
        func.count(IntakeItem.id).label('cnt'),
        func.sum(IntakeItem.amount).label('amt'),
        func.count(func.distinct(IntakeItem.customer_name)).label('customers'),
    ).filter(IntakeItem.product_name.isnot(None))
    q = _apply_common_filters(
        q,
        from_date=from_date,
        to_date=to_date,
        store_code=store_code,
        intake_status=None,
    )
    q = q.group_by(IntakeItem.product_name).order_by(func.count(IntakeItem.id).desc()).limit(limit)

    rows = q.all()
    return jsonify({
        'limit': limit,
        'items': [
            {
                'product_name': r.product_name,
                'item_count': int(r.cnt or 0),
                'total_amount': int(r.amt or 0),
                'unique_customers': int(r.customers or 0),
            }
            for r in rows
        ],
    })
