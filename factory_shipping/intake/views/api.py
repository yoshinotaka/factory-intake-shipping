"""
入荷機能 - JSON API（外部システム連携用）

king-req 側の店舗請求フォームから AJAX で呼び出され、
店舗番号 + タグ番号（任意で受付日）から intake_items を検索して
請求フォーム自動補完用の JSON を返す。

設計書: docs/intake_lookup_billing_design.md
"""

import logging
from datetime import datetime, timedelta

from flask import jsonify, request
from flask_login import login_required

from factory_shipping.models import IntakeItem
from factory_shipping.utils import normalize_tag_number_for_search, today_jst
from factory_shipping.intake.views import intake_bp

logger = logging.getLogger(__name__)


def _normalize_store_code(store_code: str) -> str:
    """店舗コードを4桁ゼロ埋めに正規化する。
    "2"→"0002", "02"→"0002", "024"→"0024", "0024"→"0024"
    """
    if not store_code:
        return store_code
    if store_code.isdigit():
        return store_code.zfill(4)
    return store_code


def _max_age_filter():
    """max_age_days（任意）があれば「預り日が今日からその日数以内」の条件を返す。無ければ None。

    同じタグは周回して再利用される（最短 100 日）。当日受付でまだ取り込まれていない品物を探すと、
    前回そのタグを使った品目が見つかってしまうので、呼び出し側が期間を絞れるようにする。
    """
    raw = (request.args.get('max_age_days') or '').strip()
    if not raw:
        return None
    try:
        days = max(1, min(3650, int(raw)))
    except ValueError:
        return None
    return IntakeItem.intake_date >= today_jst() - timedelta(days=days)


def _serialize_item(item: IntakeItem) -> dict:
    """IntakeItem をフロント転送用 JSON に変換する。"""
    return {
        'id': item.id,
        'store_code': item.store_code,
        'store_name': item.store_name,
        'tag_number': item.tag_number,
        'formatted_tag_number': item.get_formatted_tag_number(),
        'intake_date': item.intake_date.strftime('%Y-%m-%d') if item.intake_date else None,
        'product_name': item.product_name,
        'customer_name': item.customer_name,
        'quantity': item.quantity,
        'amount': item.amount,
        'wrapping': item.wrapping,
        'shipping_method': item.shipping_method,
        'notes': item.notes,
        'intake_status': item.intake_status,
        'status_name': item.status.status_name if item.status else None,
    }


@intake_bp.route('/api/lookup', methods=['GET'])
@login_required
def api_lookup():
    """店舗番号+タグ番号から入荷データを検索して JSON を返す（単発検索）。

    クエリパラメータ:
        store_code (必須): 店舗コード（2〜4桁、自動でゼロ埋め）
        tag_number (必須): タグ番号（"0-123" や "0123" など複数形式に対応）
        max_age_days (任意): 預り日が今日からこの日数以内の品目だけ

    レスポンス:
        { found, item, candidates } または { found: false, message, candidates: [] }
    """
    store_code = (request.args.get('store_code') or '').strip()
    tag_number = (request.args.get('tag_number') or '').strip()

    if not store_code:
        return jsonify({'found': False, 'error': 'store_code は必須です'}), 400
    if not tag_number:
        return jsonify({'found': False, 'error': 'tag_number は必須です'}), 400

    store_code = _normalize_store_code(store_code)

    tag_patterns = normalize_tag_number_for_search(tag_number)
    if not tag_patterns:
        return jsonify({'found': False, 'error': 'tag_number の形式が不正です'}), 400

    # 過去分（2025-09 以前）は請求の対象にならないので出さない
    query = IntakeItem.query.filter(
        IntakeItem.store_code == store_code,
        IntakeItem.tag_number.in_(tag_patterns),
        IntakeItem.in_business_scope(),
    )
    age_filter = _max_age_filter()
    if age_filter is not None:
        query = query.filter(age_filter)
    items = query.order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc()).all()

    if not items:
        logger.info(f"lookup miss: store_code={store_code}, tag_number={tag_number}")
        return jsonify({
            'found': False,
            'message': '該当するタグが入荷データに見つかりませんでした',
            'candidates': [],
        })

    primary = items[0]
    logger.info(
        f"lookup hit: id={primary.id}, store_code={primary.store_code}, "
        f"tag_number={primary.tag_number}, hits={len(items)}"
    )

    candidates = [
        {
            'id': i.id,
            'intake_date': i.intake_date.strftime('%Y-%m-%d') if i.intake_date else None,
            'tag_number': i.tag_number,
            'product_name': i.product_name,
        }
        for i in items
    ]

    return jsonify({
        'found': True,
        'item': _serialize_item(primary),
        'candidates': candidates,
    })


def _build_tag_4digit(tag_input: str) -> tuple:
    """ユーザ入力タグを (left_part, right_part_int, right_width) に分解する。

    "1123"   → ("1", 123, 3)
    "07-001" → ("07", 1, 3)
    "0-12"   → ("0", 12, 2)
    None / 不正 → None
    """
    s = (tag_input or '').strip()
    if not s:
        return None
    if '-' in s:
        parts = s.split('-')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return (parts[0], int(parts[1]), max(len(parts[1]), 1))
        return None
    if s.isdigit() and len(s) == 4:
        return (s[0], int(s[1:]), 3)
    return None


def _format_tag_for_display(left: str, right_int: int, right_width: int) -> str:
    """(left, right, width) → "left-rightZeroPad"。検索用ではなく UI 表示用。"""
    return f"{left}-{str(right_int).zfill(right_width)}"


@intake_bp.route('/api/lookup_range', methods=['GET'])
@login_required
def api_lookup_range():
    """店舗番号+開始タグから連番で count 件分を一括検索して JSON を返す。

    クエリパラメータ:
        store_code (必須): 店舗コード（2〜4桁、自動でゼロ埋め）
        tag_number (必須): 開始タグ番号
        count (任意): 取得件数。既定 6（開始 + 5）。1〜20 にクランプ
        max_age_days (任意): 預り日が今日からこの日数以内の品目だけ（前回そのタグを使った品目を拾わないため）

    レスポンス:
        {
          "items": [
            { "requested_tag": "1-123", "found": true,  "item": { ... } },
            { "requested_tag": "1-124", "found": false, "item": null   },
            ...
          ]
        }
    """
    store_code = (request.args.get('store_code') or '').strip()
    tag_number = (request.args.get('tag_number') or '').strip()
    count_str = (request.args.get('count') or '6').strip()

    if not store_code:
        return jsonify({'error': 'store_code は必須です'}), 400
    if not tag_number:
        return jsonify({'error': 'tag_number は必須です'}), 400

    try:
        count = int(count_str)
    except ValueError:
        return jsonify({'error': 'count は整数で指定してください'}), 400
    count = max(1, min(20, count))

    parts = _build_tag_4digit(tag_number)
    if not parts:
        return jsonify({'error': 'tag_number の形式が不正です（例: 1123, 07-001）'}), 400

    left, start_right, right_width = parts
    store_code = _normalize_store_code(store_code)

    # 全候補タグを生成し、検索パターンを和集合で 1 クエリにまとめる
    target_tags = []
    pattern_to_tag = {}
    all_patterns = set()
    for offset in range(count):
        rint = start_right + offset
        display_tag = _format_tag_for_display(left, rint, right_width)
        # 入力形式を保ったまま検索パターン展開
        patterns = normalize_tag_number_for_search(display_tag)
        target_tags.append({'display': display_tag, 'patterns': patterns})
        for p in patterns:
            all_patterns.add(p)
            pattern_to_tag.setdefault(p, set()).add(display_tag)

    query = IntakeItem.query.filter(
        IntakeItem.store_code == store_code,
        IntakeItem.tag_number.in_(list(all_patterns)),
        IntakeItem.in_business_scope(),  # 過去分（2025-09 以前）は出さない
    )
    age_filter = _max_age_filter()
    if age_filter is not None:
        query = query.filter(age_filter)
    rows = query.order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc()).all()

    # 同タグで複数日付ヒットする場合は最新の 1 件を採用
    items_by_tag = {}
    for r in rows:
        # この row の tag_number から該当する display_tag を逆引き
        for display_tag in pattern_to_tag.get(r.tag_number, set()):
            if display_tag not in items_by_tag:
                items_by_tag[display_tag] = r

    result_items = []
    hit_count = 0
    for t in target_tags:
        intake = items_by_tag.get(t['display'])
        if intake is not None:
            hit_count += 1
            result_items.append({
                'requested_tag': t['display'],
                'found': True,
                'item': _serialize_item(intake),
            })
        else:
            result_items.append({
                'requested_tag': t['display'],
                'found': False,
                'item': None,
            })

    logger.info(
        f"lookup_range: store={store_code}, start={tag_number}, count={count}, hits={hit_count}/{count}"
    )

    return jsonify({'items': result_items})
