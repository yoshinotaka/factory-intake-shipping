"""
ステータス確認機能 - ビュー

未出荷一覧、遅れ品管理
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from factory_shipping.models import IntakeItem, DelayedItem
from factory_shipping.extensions import db
from datetime import datetime, timedelta

status_bp = Blueprint('status', __name__)


@status_bp.route('/')
@login_required
def index():
    """ステータス一覧（ダッシュボード）"""
    return render_template('status/index.html')


@status_bp.route('/unshipped')
@login_required
def unshipped():
    """未出荷一覧"""
    items = IntakeItem.query.filter_by(is_shipped=False).order_by(IntakeItem.scheduled_date).all()
    return render_template('status/unshipped.html', items=items)


@status_bp.route('/delayed')
@login_required
def delayed():
    """遅れ品管理（未入荷商品を遅れ品ステータスに変更して工場請求）"""
    from factory_shipping.models import Store

    today = datetime.utcnow().date()

    # 店舗フィルター
    selected_store = request.args.get('store', '')

    # 未出荷の商品を表示（入荷状態が「通常」または「遅れ品」）
    query = IntakeItem.query.filter(
        IntakeItem.is_shipped == False
    )

    # 店舗で絞り込み
    if selected_store:
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
    items = IntakeItem.query.filter_by(store_id=store.id).order_by(IntakeItem.scheduled_date.desc()).all()

    return render_template('status/by_store.html', store=store, items=items)
