"""
入荷機能 - JSON API（外部システム連携用）

king-req 側の店舗請求フォームから AJAX で呼び出され、
店舗番号 + タグ番号（任意で受付日）から intake_items を検索して
請求フォーム自動補完用の JSON を返す。

設計書: docs/intake_lookup_billing_design.md
"""

import logging
from datetime import datetime

from flask import jsonify, request
from flask_login import login_required

from factory_shipping.models import IntakeItem
from factory_shipping.utils import normalize_tag_number_for_search
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
    """店舗番号+タグ番号から入荷データを検索して JSON を返す。

    クエリパラメータ:
        store_code (必須): 店舗コード（2〜4桁、自動でゼロ埋め）
        tag_number (必須): タグ番号（"0-123" や "0123" など複数形式に対応）
        intake_date (任意): YYYY-MM-DD。指定すれば絞り込み、無ければ最新を採用

    レスポンス:
        { found, item, candidates } または { found: false, message, candidates: [] }
    """
    store_code = (request.args.get('store_code') or '').strip()
    tag_number = (request.args.get('tag_number') or '').strip()
    intake_date_str = (request.args.get('intake_date') or '').strip()

    if not store_code:
        return jsonify({'found': False, 'error': 'store_code は必須です'}), 400
    if not tag_number:
        return jsonify({'found': False, 'error': 'tag_number は必須です'}), 400

    store_code = _normalize_store_code(store_code)

    tag_patterns = normalize_tag_number_for_search(tag_number)
    if not tag_patterns:
        return jsonify({'found': False, 'error': 'tag_number の形式が不正です'}), 400

    query = IntakeItem.query.filter(
        IntakeItem.store_code == store_code,
        IntakeItem.tag_number.in_(tag_patterns),
    )

    if intake_date_str:
        try:
            intake_date_obj = datetime.strptime(intake_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'found': False, 'error': 'intake_date は YYYY-MM-DD 形式で指定してください'}), 400
        query = query.filter(IntakeItem.intake_date == intake_date_obj)

    items = query.order_by(IntakeItem.intake_date.desc(), IntakeItem.id.desc()).all()

    if not items:
        logger.info(f"lookup miss: store_code={store_code}, tag_number={tag_number}, intake_date={intake_date_str or '-'}")
        return jsonify({
            'found': False,
            'message': '該当するタグが入荷データに見つかりませんでした',
            'candidates': [],
        })

    primary = items[0]
    logger.info(
        f"lookup hit: id={primary.id}, store_code={primary.store_code}, "
        f"tag_number={primary.tag_number}, intake_date={primary.intake_date}, "
        f"hits={len(items)}"
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
