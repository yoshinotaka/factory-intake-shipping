"""
ステータス確認機能 - ビュー

未出荷一覧、遅れ品管理
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from factory_shipping.models import IntakeItem, DelayedItem, ItemStatus
from factory_shipping.extensions import db
from datetime import datetime, timedelta
from factory_shipping.utils import today_jst

status_bp = Blueprint('status', __name__)


@status_bp.route('/')
@login_required
def index():
    """ステータス一覧（ダッシュボード）"""
    return render_template('status/index.html')


@status_bp.route('/unshipped')
@login_required
def unshipped():
    """未出荷一覧（status_idがshipped以外）"""
    shipped_status = ItemStatus.query.filter_by(status_code='shipped').first()
    if shipped_status:
        items = IntakeItem.query.filter(IntakeItem.status_id != shipped_status.id,
                                        IntakeItem.in_business_scope()).order_by(IntakeItem.scheduled_date).all()
    else:
        items = IntakeItem.query.filter(IntakeItem.in_business_scope()).order_by(IntakeItem.scheduled_date).all()
    return render_template('status/unshipped.html', items=items)


@status_bp.route('/delayed')
@login_required
def delayed():
    """遅れ品管理（未入荷商品を遅れ品ステータスに変更して工場請求）"""
    from factory_shipping.models import Store

    today = today_jst()

    # 店舗フィルター
    selected_store = request.args.get('store', '')

    # 未出荷の商品を表示（status_idがshipped以外）
    shipped_status = ItemStatus.query.filter_by(status_code='shipped').first()
    if shipped_status:
        query = IntakeItem.query.filter(IntakeItem.status_id != shipped_status.id)
    else:
        query = IntakeItem.query
    # 過去分（2025-09 以前）は「出荷済以外」でも遅れ品ではないので出さない
    query = query.filter(IntakeItem.in_business_scope())

    # 店舗で絞り込み（2桁の場合は4桁に変換）
    if selected_store:
        # 2桁の場合は左側に"00"を追加して4桁にする（例: "02" → "0002"）
        if len(selected_store) == 2 and selected_store.isdigit():
            selected_store = '00' + selected_store
        query = query.filter(IntakeItem.store_code == selected_store)

    items = query.order_by(IntakeItem.intake_date).all()

    # 全店舗を取得
    stores = Store.query.filter_by(is_active=True).order_by(Store.store_code).all()

    return render_template('status/delayed.html',
                           items=items,
                           stores=stores,
                           selected_store=selected_store,
                           today=today)


@status_bp.route('/update-intake-status/<int:item_id>', methods=['POST'])
@login_required
def update_intake_status(item_id):
    """入荷状態を更新する（工場請求中に変更）"""
    try:
        item = IntakeItem.query.get_or_404(item_id)

        # リクエストから新しいステータスを取得
        data = request.get_json()
        new_status = data.get('status', '工場請求中')

        # ステータスを更新
        item.intake_status = new_status
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'入荷状態を「{new_status}」に変更しました',
            'status': new_status
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@status_bp.route('/store/<store_code>')
@login_required
def by_store(store_code):
    """店舗別ステータス"""
    from factory_shipping.models import Store
    store = Store.query.filter_by(store_code=store_code).first_or_404()
    items = IntakeItem.query.filter_by(store_id=store.id).filter(
        IntakeItem.in_business_scope()).order_by(IntakeItem.scheduled_date.desc()).all()

    return render_template('status/by_store.html', store=store, items=items)
