"""
出荷機能 - ビュー

バーコードスキャンによる出荷処理
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from factory_shipping.extensions import db
from factory_shipping.models import IntakeItem, ShipmentLog
from datetime import datetime

shipping_bp = Blueprint('shipping', __name__)


@shipping_bp.route('/')
@login_required
def index():
    """出荷スキャン画面"""
    return render_template('shipping/index.html')


@shipping_bp.route('/scan', methods=['POST'])
@login_required
def scan():
    """バーコードスキャン処理（API）"""
    scanned_code = request.json.get('code')

    if not scanned_code:
        return jsonify({'error': 'スキャンコードが空です'}), 400

    # TODO: スキャンコードから商品を検索し、出荷処理を実行
    # ここでは簡易的な実装例

    # 商品検索
    item = IntakeItem.query.filter_by(item_code=scanned_code, is_shipped=False).first()

    if not item:
        return jsonify({'error': '該当する入荷データが見つかりません'}), 404

    # 出荷ログを作成
    log = ShipmentLog(
        intake_item_id=item.id,
        store_id=item.store_id,
        scanned_by_user_id=current_user.id,
        scanned_code=scanned_code,
        status='completed'
    )

    # 入荷データを出荷済みに更新
    item.is_shipped = True
    item.shipped_at = datetime.utcnow()

    db.session.add(log)
    db.session.commit()

    return jsonify({
        'success': True,
        'item': {
            'code': item.item_code,
            'name': item.item_name,
            'store': item.store.store_name
        }
    })


@shipping_bp.route('/history')
@login_required
def history():
    """出荷履歴"""
    logs = ShipmentLog.query.order_by(ShipmentLog.scanned_at.desc()).limit(100).all()
    return render_template('shipping/history.html', logs=logs)
