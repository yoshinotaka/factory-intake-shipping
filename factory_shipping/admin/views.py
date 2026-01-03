"""
管理者機能 - ビュー

管理者権限を持つユーザーのみがアクセスできる、各テーブルの直接編集機能を提供します。
"""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from factory_shipping.extensions import db
from factory_shipping.models import User, Store, ItemStatus, IntakeItem, ShipmentLog, DelayedItem, FactoryOperator, JournalData
from factory_shipping.admin.decorators import admin_required
from datetime import datetime, date
from sqlalchemy import desc, or_
from factory_shipping.utils import now_jst, today_jst, get_next_history_number

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)


@admin_bp.route('/')
@login_required
@admin_required
def index():
    """管理者ダッシュボード"""
    # 各テーブルのレコード数を取得
    stats = {
        'users_count': User.query.count(),
        'stores_count': Store.query.count(),
        'item_statuses_count': ItemStatus.query.count(),
        'intake_items_count': IntakeItem.query.count(),
        'shipment_logs_count': ShipmentLog.query.count(),
        'delayed_items_count': DelayedItem.query.count(),
        'journal_data_count': JournalData.query.count(),
    }
    return render_template('admin/index.html', stats=stats)


# ==================== Users 管理 ====================

@admin_bp.route('/users')
@login_required
@admin_required
def users_list():
    """ユーザー一覧"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    users = User.query.order_by(desc(User.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/users_list.html', users=users)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def users_create():
    """ユーザー作成"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email', '').strip() or None
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        is_store_staff = request.form.get('is_store_staff') == 'on'
        is_factory_staff = request.form.get('is_factory_staff') == 'on'
        is_shift_staff = request.form.get('is_shift_staff') == 'on'
        is_office_staff = request.form.get('is_office_staff') == 'on'
        is_active = request.form.get('is_active', 'on') == 'on'

        # バリデーション
        if User.query.filter_by(username=username).first():
            flash('このユーザー名は既に使用されています', 'error')
            return redirect(url_for('admin.users_create'))

        if email and User.query.filter_by(email=email).first():
            flash('このメールアドレスは既に使用されています', 'error')
            return redirect(url_for('admin.users_create'))

        user = User(
            username=username,
            email=email,
            is_admin=is_admin,
            is_store_staff=is_store_staff,
            is_factory_staff=is_factory_staff,
            is_shift_staff=is_shift_staff,
            is_office_staff=is_office_staff,
            is_active=is_active
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash(f'ユーザー「{username}」を作成しました', 'success')
        return redirect(url_for('admin.users_list'))

    return render_template('admin/users_form.html', user=None)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def users_edit(user_id):
    """ユーザー編集"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.username = request.form.get('username')
        email = request.form.get('email', '').strip() or None
        # メールアドレスの重複チェック（自分自身以外）
        if email and User.query.filter(User.email == email, User.id != user.id).first():
            flash('このメールアドレスは既に使用されています', 'error')
            return redirect(url_for('admin.users_edit', user_id=user_id))
        user.email = email
        user.is_admin = request.form.get('is_admin') == 'on'
        user.is_store_staff = request.form.get('is_store_staff') == 'on'
        user.is_factory_staff = request.form.get('is_factory_staff') == 'on'
        user.is_shift_staff = request.form.get('is_shift_staff') == 'on'
        user.is_office_staff = request.form.get('is_office_staff') == 'on'
        user.is_active = request.form.get('is_active') == 'on'

        # パスワード変更（入力されている場合のみ）
        new_password = request.form.get('password')
        if new_password:
            user.set_password(new_password)

        db.session.commit()
        flash(f'ユーザー「{user.username}」を更新しました', 'success')
        return redirect(url_for('admin.users_list'))

    return render_template('admin/users_form.html', user=user)


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def users_delete(user_id):
    """ユーザー削除"""
    user = User.query.get_or_404(user_id)

    # 自分自身は削除できない
    from flask_login import current_user
    if user.id == current_user.id:
        flash('自分自身を削除することはできません', 'error')
        return redirect(url_for('admin.users_list'))

    username = user.username
    db.session.delete(user)
    db.session.commit()

    flash(f'ユーザー「{username}」を削除しました', 'success')
    return redirect(url_for('admin.users_list'))


# ==================== ItemStatus 管理 ====================

@admin_bp.route('/item-statuses')
@login_required
@admin_required
def item_statuses_list():
    """商品状態一覧"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    statuses = ItemStatus.query.order_by(ItemStatus.display_order, ItemStatus.status_code).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/item_statuses_list.html', statuses=statuses)


@admin_bp.route('/item-statuses/create', methods=['GET', 'POST'])
@login_required
@admin_required
def item_statuses_create():
    """商品状態作成"""
    if request.method == 'POST':
        status_code = request.form.get('status_code')
        status_name = request.form.get('status_name')
        description = request.form.get('description')
        display_order = request.form.get('display_order', 0, type=int)
        is_active = request.form.get('is_active', 'on') == 'on'

        # バリデーション
        if ItemStatus.query.filter_by(status_code=status_code).first():
            flash('この状態コードは既に使用されています', 'error')
            return redirect(url_for('admin.item_statuses_create'))

        status = ItemStatus(
            status_code=status_code,
            status_name=status_name,
            description=description,
            display_order=display_order,
            is_active=is_active
        )

        db.session.add(status)
        db.session.commit()

        flash(f'商品状態「{status_name}」を作成しました', 'success')
        return redirect(url_for('admin.item_statuses_list'))

    return render_template('admin/item_statuses_form.html', status=None)


@admin_bp.route('/item-statuses/<int:status_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def item_statuses_edit(status_id):
    """商品状態編集"""
    status = ItemStatus.query.get_or_404(status_id)

    if request.method == 'POST':
        status.status_code = request.form.get('status_code')
        status.status_name = request.form.get('status_name')
        status.description = request.form.get('description')
        status.display_order = request.form.get('display_order', 0, type=int)
        status.is_active = request.form.get('is_active') == 'on'

        db.session.commit()
        flash(f'商品状態「{status.status_name}」を更新しました', 'success')
        return redirect(url_for('admin.item_statuses_list'))

    return render_template('admin/item_statuses_form.html', status=status)


@admin_bp.route('/item-statuses/<int:status_id>/delete', methods=['POST'])
@login_required
@admin_required
def item_statuses_delete(status_id):
    """商品状態削除"""
    status = ItemStatus.query.get_or_404(status_id)

    # 関連する入荷データがある場合は削除できない
    if status.intake_items.count() > 0 or status.shipment_logs.count() > 0:
        flash('この状態は使用されているため削除できません', 'error')
        return redirect(url_for('admin.item_statuses_list'))

    status_name = status.status_name
    db.session.delete(status)
    db.session.commit()

    flash(f'商品状態「{status_name}」を削除しました', 'success')
    return redirect(url_for('admin.item_statuses_list'))


# ==================== Stores 管理 ====================

@admin_bp.route('/stores')
@login_required
@admin_required
def stores_list():
    """店舗一覧"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    stores = Store.query.order_by(Store.store_code).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/stores_list.html', stores=stores)


@admin_bp.route('/stores/create', methods=['GET', 'POST'])
@login_required
@admin_required
def stores_create():
    """店舗作成"""
    if request.method == 'POST':
        store_code = request.form.get('store_code')
        store_name = request.form.get('store_name')
        is_active = request.form.get('is_active', 'on') == 'on'

        # バリデーション
        if Store.query.filter_by(store_code=store_code).first():
            flash('この店舗コードは既に使用されています', 'error')
            return redirect(url_for('admin.stores_create'))

        store = Store(
            store_code=store_code,
            store_name=store_name,
            is_active=is_active
        )

        db.session.add(store)
        db.session.commit()

        flash(f'店舗「{store_name}」を作成しました', 'success')
        return redirect(url_for('admin.stores_list'))

    return render_template('admin/stores_form.html', store=None)


@admin_bp.route('/stores/<int:store_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def stores_edit(store_id):
    """店舗編集"""
    store = Store.query.get_or_404(store_id)

    if request.method == 'POST':
        store.store_code = request.form.get('store_code')
        store.store_name = request.form.get('store_name')
        store.is_active = request.form.get('is_active') == 'on'

        db.session.commit()
        flash(f'店舗「{store.store_name}」を更新しました', 'success')
        return redirect(url_for('admin.stores_list'))

    return render_template('admin/stores_form.html', store=store)


@admin_bp.route('/stores/<int:store_id>/delete', methods=['POST'])
@login_required
@admin_required
def stores_delete(store_id):
    """店舗削除"""
    store = Store.query.get_or_404(store_id)

    # 関連する入荷データがある場合は削除できない
    if store.intake_items.count() > 0:
        flash('この店舗には入荷データが存在するため削除できません', 'error')
        return redirect(url_for('admin.stores_list'))

    store_name = store.store_name
    db.session.delete(store)
    db.session.commit()

    flash(f'店舗「{store_name}」を削除しました', 'success')
    return redirect(url_for('admin.stores_list'))


# ==================== IntakeItems 管理 ====================

@admin_bp.route('/intake-items')
@login_required
@admin_required
def intake_items_list():
    """入荷データ一覧（ページネーション付き）"""
    # ページネーション設定
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # per_pageの上限を設定（1000件まで）
    if per_page > 1000:
        per_page = 1000

    # 検索フィルター
    query = IntakeItem.query

    store_code = request.args.get('store_code')
    if store_code:
        # 2桁の場合は下2桁として検索（例: "02" → "%02"）
        if len(store_code) == 2 and store_code.isdigit():
            query = query.filter(IntakeItem.store_code.like(f'%{store_code}'))
        else:
            query = query.filter(IntakeItem.store_code.like(f'%{store_code}%'))

    tag_number = request.args.get('tag_number')
    if tag_number:
        # ハイフンを除去して検索（例: "1234" → "1234"）
        tag_number_clean = tag_number.replace('-', '')

        # 4桁の場合は下4桁として検索（例: "1234" → "%1234"）
        if len(tag_number_clean) == 4 and tag_number_clean.isdigit():
            # タグ番号からハイフンを除去したパターンで検索
            query = query.filter(
                db.func.replace(IntakeItem.tag_number, '-', '').like(f'%{tag_number_clean}')
            )
        else:
            # ハイフンありなしどちらでも検索できるように、ハイフンを除去して部分一致
            query = query.filter(
                db.func.replace(IntakeItem.tag_number, '-', '').like(f'%{tag_number_clean}%')
            )

    # 商品状態フィルタ（status_idでフィルタリング）
    status_filter = request.args.get('status_id', '').strip()
    if status_filter:
        try:
            status_id = int(status_filter)
            query = query.filter(IntakeItem.status_id == status_id)
        except ValueError:
            pass

    # 詳細検索フィルター（全てのカラムで検索可能）
    # デバッグ用: リクエストパラメータをログに出力
    all_params = dict(request.args)
    logger.info(f"検索パラメータ: {all_params}")
    
    # 店舗名
    store_name = request.args.get('store_name', '').strip()
    logger.info(f"店舗名パラメータ取得: '{store_name}' (型: {type(store_name)}, 長さ: {len(store_name) if store_name else 0})")
    if store_name:
        logger.info(f"店舗名で検索実行: {store_name}")
        # NULL値も含めて検索（COALESCEを使用）
        query = query.filter(
            db.func.coalesce(IntakeItem.store_name, '').like(f'%{store_name}%')
        )
    
    # 伝票No
    slip_number = request.args.get('slip_number', '').strip()
    if slip_number:
        logger.info(f"伝票Noで検索実行: {slip_number}")
        query = query.filter(
            db.func.coalesce(IntakeItem.slip_number, '').like(f'%{slip_number}%')
        )
    
    # 商品名
    product_name = request.args.get('product_name', '').strip()
    if product_name:
        logger.info(f"商品名で検索実行: {product_name}")
        query = query.filter(
            db.func.coalesce(IntakeItem.product_name, '').like(f'%{product_name}%')
        )
    
    # 顧客名
    customer_name = request.args.get('customer_name', '').strip()
    if customer_name:
        logger.info(f"顧客名で検索実行: {customer_name}")
        query = query.filter(
            db.func.coalesce(IntakeItem.customer_name, '').like(f'%{customer_name}%')
        )
    
    # 金額（範囲検索）
    amount_from = request.args.get('amount_from', '').strip()
    if amount_from:
        try:
            amount_from_int = int(amount_from)
            query = query.filter(IntakeItem.amount >= amount_from_int)
        except ValueError:
            pass
    
    amount_to = request.args.get('amount_to', '').strip()
    if amount_to:
        try:
            amount_to_int = int(amount_to)
            query = query.filter(IntakeItem.amount <= amount_to_int)
        except ValueError:
            pass
    
    # 数量（範囲検索）
    quantity_from = request.args.get('quantity_from', '').strip()
    if quantity_from:
        try:
            quantity_from_int = int(quantity_from)
            query = query.filter(IntakeItem.quantity >= quantity_from_int)
        except ValueError:
            pass
    
    quantity_to = request.args.get('quantity_to', '').strip()
    if quantity_to:
        try:
            quantity_to_int = int(quantity_to)
            query = query.filter(IntakeItem.quantity <= quantity_to_int)
        except ValueError:
            pass
    
    # 預かり日（範囲検索）
    intake_date_from = request.args.get('intake_date_from', '').strip()
    if intake_date_from:
        try:
            from datetime import datetime
            intake_date_from_obj = datetime.strptime(intake_date_from, '%Y-%m-%d').date()
            query = query.filter(IntakeItem.intake_date >= intake_date_from_obj)
        except ValueError:
            pass
    
    intake_date_to = request.args.get('intake_date_to', '').strip()
    if intake_date_to:
        try:
            from datetime import datetime
            intake_date_to_obj = datetime.strptime(intake_date_to, '%Y-%m-%d').date()
            query = query.filter(IntakeItem.intake_date <= intake_date_to_obj)
        except ValueError:
            pass
    
    # 出荷予定日（範囲検索）
    scheduled_date_from = request.args.get('scheduled_date_from', '').strip()
    if scheduled_date_from:
        try:
            from datetime import datetime
            scheduled_date_from_obj = datetime.strptime(scheduled_date_from, '%Y-%m-%d').date()
            query = query.filter(IntakeItem.scheduled_date >= scheduled_date_from_obj)
        except ValueError:
            pass
    
    scheduled_date_to = request.args.get('scheduled_date_to', '').strip()
    if scheduled_date_to:
        try:
            from datetime import datetime
            scheduled_date_to_obj = datetime.strptime(scheduled_date_to, '%Y-%m-%d').date()
            query = query.filter(IntakeItem.scheduled_date <= scheduled_date_to_obj)
        except ValueError:
            pass
    
    # 包装
    wrapping = request.args.get('wrapping', '').strip()
    if wrapping:
        logger.info(f"包装で検索実行: {wrapping}")
        query = query.filter(
            db.func.coalesce(IntakeItem.wrapping, '').like(f'%{wrapping}%')
        )
    
    # 出荷便
    shipping_method = request.args.get('shipping_method', '').strip()
    if shipping_method:
        logger.info(f"出荷便で検索実行: {shipping_method}")
        query = query.filter(
            db.func.coalesce(IntakeItem.shipping_method, '').like(f'%{shipping_method}%')
        )
    
    # 入荷状態
    intake_status = request.args.get('intake_status', '').strip()
    if intake_status:
        logger.info(f"入荷状態で検索実行: {intake_status}")
        query = query.filter(IntakeItem.intake_status.like(f'%{intake_status}%'))
    
    # 備考
    notes = request.args.get('notes', '').strip()
    if notes:
        logger.info(f"備考で検索実行: {notes}")
        query = query.filter(
            db.func.coalesce(IntakeItem.notes, '').like(f'%{notes}%')
        )
    
    # 出荷日時（範囲検索）
    shipped_at_from = request.args.get('shipped_at_from', '').strip()
    if shipped_at_from:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            shipped_at_from = shipped_at_from.replace('T', ' ')
            shipped_at_from_obj = datetime.strptime(shipped_at_from, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.shipped_at >= shipped_at_from_obj)
        except ValueError:
            try:
                from datetime import datetime
                shipped_at_from_obj = datetime.strptime(shipped_at_from, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.shipped_at) >= shipped_at_from_obj)
            except ValueError:
                pass
    
    shipped_at_to = request.args.get('shipped_at_to', '').strip()
    if shipped_at_to:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            shipped_at_to = shipped_at_to.replace('T', ' ')
            shipped_at_to_obj = datetime.strptime(shipped_at_to, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.shipped_at <= shipped_at_to_obj)
        except ValueError:
            try:
                from datetime import datetime
                shipped_at_to_obj = datetime.strptime(shipped_at_to, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.shipped_at) <= shipped_at_to_obj)
            except ValueError:
                pass
    
    # CSV取り込み日時（範囲検索）
    imported_at_from = request.args.get('imported_at_from', '').strip()
    if imported_at_from:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            imported_at_from = imported_at_from.replace('T', ' ')
            imported_at_from_obj = datetime.strptime(imported_at_from, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.imported_at >= imported_at_from_obj)
        except ValueError:
            try:
                from datetime import datetime
                imported_at_from_obj = datetime.strptime(imported_at_from, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.imported_at) >= imported_at_from_obj)
            except ValueError:
                pass
    
    imported_at_to = request.args.get('imported_at_to', '').strip()
    if imported_at_to:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            imported_at_to = imported_at_to.replace('T', ' ')
            imported_at_to_obj = datetime.strptime(imported_at_to, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.imported_at <= imported_at_to_obj)
        except ValueError:
            try:
                from datetime import datetime
                imported_at_to_obj = datetime.strptime(imported_at_to, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.imported_at) <= imported_at_to_obj)
            except ValueError:
                pass
    
    # 作成日時（範囲検索）
    created_at_from = request.args.get('created_at_from', '').strip()
    if created_at_from:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            created_at_from = created_at_from.replace('T', ' ')
            created_at_from_obj = datetime.strptime(created_at_from, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.created_at >= created_at_from_obj)
        except ValueError:
            try:
                from datetime import datetime
                created_at_from_obj = datetime.strptime(created_at_from, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.created_at) >= created_at_from_obj)
            except ValueError:
                pass
    
    created_at_to = request.args.get('created_at_to', '').strip()
    if created_at_to:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            created_at_to = created_at_to.replace('T', ' ')
            created_at_to_obj = datetime.strptime(created_at_to, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.created_at <= created_at_to_obj)
        except ValueError:
            try:
                from datetime import datetime
                created_at_to_obj = datetime.strptime(created_at_to, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.created_at) <= created_at_to_obj)
            except ValueError:
                pass
    
    # 更新日時（範囲検索）
    updated_at_from = request.args.get('updated_at_from', '').strip()
    if updated_at_from:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            updated_at_from = updated_at_from.replace('T', ' ')
            updated_at_from_obj = datetime.strptime(updated_at_from, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.updated_at >= updated_at_from_obj)
        except ValueError:
            try:
                from datetime import datetime
                updated_at_from_obj = datetime.strptime(updated_at_from, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.updated_at) >= updated_at_from_obj)
            except ValueError:
                pass
    
    updated_at_to = request.args.get('updated_at_to', '').strip()
    if updated_at_to:
        try:
            from datetime import datetime
            # datetime-local形式 (YYYY-MM-DDTHH:mm) を変換
            updated_at_to = updated_at_to.replace('T', ' ')
            updated_at_to_obj = datetime.strptime(updated_at_to, '%Y-%m-%d %H:%M')
            query = query.filter(IntakeItem.updated_at <= updated_at_to_obj)
        except ValueError:
            try:
                from datetime import datetime
                updated_at_to_obj = datetime.strptime(updated_at_to, '%Y-%m-%d').date()
                query = query.filter(db.func.date(IntakeItem.updated_at) <= updated_at_to_obj)
            except ValueError:
                pass

    # デバッグ用: 最終的なクエリの件数をログに出力
    total_before_pagination = query.count()
    logger.info(f"検索結果件数（ページネーション前）: {total_before_pagination}")
    
    # ページネーション付きで取得
    pagination = query.order_by(desc(IntakeItem.intake_date)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    stores = Store.query.order_by(Store.store_code).all()
    item_statuses = ItemStatus.query.filter_by(is_active=True).order_by(ItemStatus.display_order, ItemStatus.status_code).all()
    return render_template('admin/intake_items_list.html', pagination=pagination, stores=stores, item_statuses=item_statuses)


@admin_bp.route('/intake-items/create', methods=['GET', 'POST'])
@login_required
@admin_required
def intake_items_create():
    """入荷データ作成"""
    if request.method == 'POST':
        store_id = request.form.get('store_id', type=int)
        store = Store.query.get(store_id)

        if not store:
            flash('店舗が見つかりません', 'error')
            return redirect(url_for('admin.intake_items_create'))

        intake_date_str = request.form.get('intake_date')
        intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date() if intake_date_str else today_jst()

        scheduled_date_str = request.form.get('scheduled_date')
        scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%d').date() if scheduled_date_str else None

        shipped_at_str = request.form.get('shipped_at')
        shipped_at = None
        if shipped_at_str:
            try:
                # datetime-local形式 (YYYY-MM-DDTHH:MM) を処理
                shipped_at = datetime.strptime(shipped_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    # 既存の形式 (YYYY-MM-DD HH:MM:SS) もサポート
                    shipped_at = datetime.strptime(shipped_at_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass

        status_id = request.form.get('status_id', type=int)
        if status_id == 0:
            status_id = None

        item = IntakeItem(
            store_id=store_id,
            store_code=store.store_code,
            store_name=store.store_name,
            slip_number=request.form.get('slip_number'),
            tag_number=request.form.get('tag_number'),
            product_name=request.form.get('product_name'),
            customer_name=request.form.get('customer_name'),
            amount=request.form.get('amount', type=int),
            intake_date=intake_date,
            scheduled_date=scheduled_date,
            status_id=status_id,
            intake_status=request.form.get('intake_status', '通常'),
            shipped_at=shipped_at,
            quantity=request.form.get('quantity', 1, type=int),
            wrapping=request.form.get('wrapping'),
            shipping_method=request.form.get('shipping_method'),
            notes=request.form.get('notes')
        )

        db.session.add(item)
        db.session.commit()

        flash(f'入荷データを作成しました（タグ: {item.tag_number}）', 'success')
        return redirect(url_for('admin.intake_items_list'))

    stores = Store.query.filter_by(is_active=True).order_by(Store.store_code).all()
    item_statuses = ItemStatus.query.filter_by(is_active=True).order_by(ItemStatus.display_order, ItemStatus.status_code).all()
    return render_template('admin/intake_items_form.html', item=None, stores=stores, item_statuses=item_statuses)


@admin_bp.route('/intake-items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def intake_items_edit(item_id):
    """入荷データ編集"""
    item = IntakeItem.query.get_or_404(item_id)

    if request.method == 'POST':
        store_id = request.form.get('store_id', type=int)
        store = Store.query.get(store_id)

        if store:
            item.store_id = store_id
            item.store_code = store.store_code
            item.store_name = store.store_name

        item.slip_number = request.form.get('slip_number')
        item.tag_number = request.form.get('tag_number')
        item.product_name = request.form.get('product_name')
        item.customer_name = request.form.get('customer_name')
        item.amount = request.form.get('amount', type=int)

        intake_date_str = request.form.get('intake_date')
        if intake_date_str:
            item.intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()

        scheduled_date_str = request.form.get('scheduled_date')
        if scheduled_date_str:
            item.scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%d').date()
        else:
            item.scheduled_date = None

        shipped_at_str = request.form.get('shipped_at')
        if shipped_at_str:
            try:
                # datetime-local形式 (YYYY-MM-DDTHH:MM) を処理
                item.shipped_at = datetime.strptime(shipped_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    # 既存の形式 (YYYY-MM-DD HH:MM:SS) もサポート
                    item.shipped_at = datetime.strptime(shipped_at_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    item.shipped_at = None
        else:
            item.shipped_at = None

        status_id = request.form.get('status_id', type=int)
        if status_id == 0:
            item.status_id = None
        else:
            item.status_id = status_id

        item.intake_status = request.form.get('intake_status', '通常')
        item.quantity = request.form.get('quantity', 1, type=int)
        item.wrapping = request.form.get('wrapping')
        item.shipping_method = request.form.get('shipping_method')
        item.notes = request.form.get('notes')

        db.session.commit()
        flash(f'入荷データを更新しました（タグ: {item.tag_number}）', 'success')
        return redirect(url_for('admin.intake_items_list'))

    stores = Store.query.filter_by(is_active=True).order_by(Store.store_code).all()
    item_statuses = ItemStatus.query.filter_by(is_active=True).order_by(ItemStatus.display_order, ItemStatus.status_code).all()
    return render_template('admin/intake_items_form.html', item=item, stores=stores, item_statuses=item_statuses)


@admin_bp.route('/intake-items/<int:item_id>/delete', methods=['POST'])
@login_required
@admin_required
def intake_items_delete(item_id):
    """入荷データ削除"""
    item = IntakeItem.query.get_or_404(item_id)

    tag_number = item.tag_number
    db.session.delete(item)
    db.session.commit()

    flash(f'入荷データを削除しました（タグ: {tag_number}）', 'success')
    return redirect(url_for('admin.intake_items_list'))


# ==================== ShipmentLogs 管理 ====================

@admin_bp.route('/shipment-logs')
@login_required
@admin_required
def shipment_logs_list():
    """出荷ログ一覧（ページネーション付き）"""
    # ページネーション設定
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # per_pageの上限を設定（1000件まで）
    if per_page > 1000:
        per_page = 1000

    # 検索フィルター
    query = ShipmentLog.query

    store_code = request.args.get('store_code')
    if store_code:
        # 2桁の場合は下2桁として検索（例: "02" → "%02"）
        if len(store_code) == 2 and store_code.isdigit():
            query = query.filter(ShipmentLog.store_code.like(f'%{store_code}'))
        else:
            query = query.filter(ShipmentLog.store_code.like(f'%{store_code}%'))

    tag_number = request.args.get('tag_number')
    if tag_number:
        # ハイフンを除去して検索（例: "1234" → "1234"）
        tag_number_clean = tag_number.replace('-', '')

        # 4桁の場合は下4桁として検索（例: "1234" → "%1234"）
        if len(tag_number_clean) == 4 and tag_number_clean.isdigit():
            # タグ番号からハイフンを除去したパターンで検索
            query = query.filter(
                db.func.replace(ShipmentLog.tag_number, '-', '').like(f'%{tag_number_clean}')
            )
        else:
            # ハイフンありなしどちらでも検索できるように、ハイフンを除去して部分一致
            query = query.filter(
                db.func.replace(ShipmentLog.tag_number, '-', '').like(f'%{tag_number_clean}%')
            )

    # 商品状態フィルタ（new_status_idでフィルタリング）
    status_filter = request.args.get('status_id')
    if status_filter:
        try:
            status_id = int(status_filter)
            query = query.filter(ShipmentLog.new_status_id == status_id)
        except ValueError:
            pass

    # ページネーション付きで取得
    pagination = query.order_by(desc(ShipmentLog.scanned_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # フィルター用のデータ
    stores = Store.query.order_by(Store.store_code).all()
    item_statuses = ItemStatus.query.filter_by(is_active=True).order_by(ItemStatus.display_order, ItemStatus.status_code).all()

    return render_template('admin/shipment_logs_list.html', pagination=pagination, stores=stores, item_statuses=item_statuses)


@admin_bp.route('/shipment-logs/create', methods=['GET', 'POST'])
@login_required
@admin_required
def shipment_logs_create():
    """出荷ログ作成"""
    if request.method == 'POST':
        intake_item_id = request.form.get('intake_item_id', type=int)
        if not intake_item_id:
            flash('入荷データIDは必須です', 'error')
            return redirect(url_for('admin.shipment_logs_create'))

        scanned_by_user_id = request.form.get('scanned_by_user_id', type=int)
        operator_id = request.form.get('operator_id', type=int)
        scanned_code = request.form.get('scanned_code')
        scanned_at_str = request.form.get('scanned_at')
        new_status_id = request.form.get('new_status_id', type=int)
        status = request.form.get('status', 'completed')
        notes = request.form.get('notes')

        scanned_at = now_jst()
        if scanned_at_str:
            try:
                scanned_at = datetime.strptime(scanned_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                scanned_at = datetime.strptime(scanned_at_str, '%Y-%m-%d %H:%M:%S')

        if new_status_id == 0:
            new_status_id = None

        # 入荷データから複合キー情報を取得
        intake_item = IntakeItem.query.get(intake_item_id)
        if not intake_item:
            flash('入荷データが見つかりません', 'error')
            return redirect(url_for('admin.shipment_logs_create'))

        # store_idはintake_itemのstore_idを使用（整合性を保つ）
        store_id = intake_item.store_id

        # 履歴番号を計算
        history_number = get_next_history_number(
            intake_item.store_code,
            intake_item.intake_date,
            intake_item.tag_number
        )

        log = ShipmentLog(
            intake_item_id=intake_item_id,
            store_id=store_id,
            store_code=intake_item.store_code,
            intake_date=intake_item.intake_date,
            tag_number=intake_item.tag_number,
            history_number=history_number,
            scanned_by_user_id=scanned_by_user_id if scanned_by_user_id else None,
            operator_id=operator_id if operator_id else None,
            scanned_at=scanned_at,
            scanned_code=scanned_code,
            new_status_id=new_status_id,
            status=status,
            notes=notes
        )

        db.session.add(log)
        db.session.commit()

        flash('出荷ログを作成しました', 'success')
        return redirect(url_for('admin.shipment_logs_list'))

    intake_items = IntakeItem.query.order_by(desc(IntakeItem.intake_date)).limit(100).all()
    stores = Store.query.order_by(Store.store_code).all()
    users = User.query.order_by(User.username).all()
    operators = FactoryOperator.query.filter_by(is_active=True).order_by(FactoryOperator.operator_code).all()
    item_statuses = ItemStatus.query.filter_by(is_active=True).order_by(ItemStatus.display_order, ItemStatus.status_code).all()
    return render_template('admin/shipment_logs_form.html', log=None, intake_items=intake_items, stores=stores, users=users, operators=operators, item_statuses=item_statuses)


@admin_bp.route('/shipment-logs/<int:log_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def shipment_logs_edit(log_id):
    """出荷ログ編集"""
    log = ShipmentLog.query.get_or_404(log_id)

    if request.method == 'POST':
        # 入荷データIDを取得
        new_intake_item_id = request.form.get('intake_item_id', type=int)
        if not new_intake_item_id:
            flash('入荷データIDは必須です', 'error')
            return redirect(url_for('admin.shipment_logs_edit', log_id=log_id))

        intake_item = IntakeItem.query.get(new_intake_item_id)
        if not intake_item:
            flash('入荷データが見つかりません', 'error')
            return redirect(url_for('admin.shipment_logs_edit', log_id=log_id))

        # 入荷データIDが変更された場合は複合キーも更新
        if new_intake_item_id != log.intake_item_id:
            log.intake_item_id = new_intake_item_id
            log.store_code = intake_item.store_code
            log.intake_date = intake_item.intake_date
            log.tag_number = intake_item.tag_number
            # 履歴番号も再計算
            log.history_number = get_next_history_number(
                intake_item.store_code,
                intake_item.intake_date,
                intake_item.tag_number
            )
            # store_idもintake_itemのstore_idに合わせる
            log.store_id = intake_item.store_id
        else:
            # 入荷データIDが変更されていない場合でも、store_idがintake_itemと一致することを確認
            if log.store_id != intake_item.store_id:
                # store_idをintake_itemのstore_idに合わせる（整合性を保つ）
                log.store_id = intake_item.store_id
            # 複合キー情報もintake_itemから取得して更新（整合性を保つ）
            log.store_code = intake_item.store_code
            log.intake_date = intake_item.intake_date
            log.tag_number = intake_item.tag_number

        scanned_by_user_id = request.form.get('scanned_by_user_id', type=int)
        log.scanned_by_user_id = scanned_by_user_id if scanned_by_user_id else None

        operator_id = request.form.get('operator_id', type=int)
        log.operator_id = operator_id if operator_id else None

        log.scanned_code = request.form.get('scanned_code')

        scanned_at_str = request.form.get('scanned_at')
        if scanned_at_str:
            try:
                # datetime-local形式 (YYYY-MM-DDTHH:MM) を処理
                log.scanned_at = datetime.strptime(scanned_at_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    # 既存の形式 (YYYY-MM-DD HH:MM:SS) もサポート
                    log.scanned_at = datetime.strptime(scanned_at_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass

        new_status_id = request.form.get('new_status_id', type=int)
        if new_status_id == 0:
            log.new_status_id = None
        else:
            log.new_status_id = new_status_id

        log.status = request.form.get('status', 'completed')
        log.notes = request.form.get('notes')

        db.session.commit()
        flash('出荷ログを更新しました', 'success')
        return redirect(url_for('admin.shipment_logs_list'))

    intake_items = IntakeItem.query.order_by(desc(IntakeItem.intake_date)).limit(100).all()
    stores = Store.query.order_by(Store.store_code).all()
    users = User.query.order_by(User.username).all()
    operators = FactoryOperator.query.filter_by(is_active=True).order_by(FactoryOperator.operator_code).all()
    item_statuses = ItemStatus.query.filter_by(is_active=True).order_by(ItemStatus.display_order, ItemStatus.status_code).all()
    return render_template('admin/shipment_logs_form.html', log=log, intake_items=intake_items, stores=stores, users=users, operators=operators, item_statuses=item_statuses)


@admin_bp.route('/shipment-logs/<int:log_id>/delete', methods=['POST'])
@login_required
@admin_required
def shipment_logs_delete(log_id):
    """出荷ログ削除"""
    log = ShipmentLog.query.get_or_404(log_id)

    # 関連する入荷データの状態をリセット
    if log.intake_item:
        received_status = ItemStatus.query.filter_by(status_code='received').first()
        log.intake_item.status_id = received_status.id if received_status else None
        log.intake_item.shipped_at = None

    scanned_code = log.scanned_code
    db.session.delete(log)
    db.session.commit()

    flash(f'出荷ログを削除しました（コード: {scanned_code}）', 'success')
    return redirect(url_for('admin.shipment_logs_list'))


# ==================== DelayedItems 管理 ====================

@admin_bp.route('/delayed-items')
@login_required
@admin_required
def delayed_items_list():
    """遅れ品一覧"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = DelayedItem.query

    # 未解決のみ表示オプション
    show_unresolved = request.args.get('show_unresolved')
    if show_unresolved == '1':
        query = query.filter(DelayedItem.resolved == False)

    items = query.order_by(desc(DelayedItem.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/delayed_items_list.html', items=items)


@admin_bp.route('/delayed-items/create', methods=['GET', 'POST'])
@login_required
@admin_required
def delayed_items_create():
    """遅れ品作成"""
    if request.method == 'POST':
        intake_item_id = request.form.get('intake_item_id', type=int)
        delay_reason = request.form.get('delay_reason')
        expected_date_str = request.form.get('expected_date')

        expected_date = None
        if expected_date_str:
            expected_date = datetime.strptime(expected_date_str, '%Y-%m-%d').date()

        item = DelayedItem(
            intake_item_id=intake_item_id,
            delay_reason=delay_reason,
            expected_date=expected_date,
            resolved=False
        )

        db.session.add(item)
        db.session.commit()

        flash('遅れ品を登録しました', 'success')
        return redirect(url_for('admin.delayed_items_list'))

    # 未出荷の入荷データのみ選択可能（status_idがshipped以外）
    shipped_status = ItemStatus.query.filter_by(status_code='shipped').first()
    if shipped_status:
        intake_items = IntakeItem.query.filter(IntakeItem.status_id != shipped_status.id).order_by(desc(IntakeItem.intake_date)).limit(100).all()
    else:
        intake_items = IntakeItem.query.order_by(desc(IntakeItem.intake_date)).limit(100).all()
    return render_template('admin/delayed_items_form.html', item=None, intake_items=intake_items)


@admin_bp.route('/delayed-items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def delayed_items_edit(item_id):
    """遅れ品編集"""
    item = DelayedItem.query.get_or_404(item_id)

    if request.method == 'POST':
        item.delay_reason = request.form.get('delay_reason')

        expected_date_str = request.form.get('expected_date')
        if expected_date_str:
            item.expected_date = datetime.strptime(expected_date_str, '%Y-%m-%d').date()
        else:
            item.expected_date = None

        item.resolved = request.form.get('resolved') == 'on'
        if item.resolved and not item.resolved_at:
            item.resolved_at = now_jst()

        db.session.commit()
        flash('遅れ品を更新しました', 'success')
        return redirect(url_for('admin.delayed_items_list'))

    # 未出荷の入荷データのみ選択可能（status_idがshipped以外）
    shipped_status = ItemStatus.query.filter_by(status_code='shipped').first()
    if shipped_status:
        intake_items = IntakeItem.query.filter(IntakeItem.status_id != shipped_status.id).order_by(desc(IntakeItem.intake_date)).limit(100).all()
    else:
        intake_items = IntakeItem.query.order_by(desc(IntakeItem.intake_date)).limit(100).all()
    return render_template('admin/delayed_items_form.html', item=item, intake_items=intake_items)


@admin_bp.route('/delayed-items/<int:item_id>/delete', methods=['POST'])
@login_required
@admin_required
def delayed_items_delete(item_id):
    """遅れ品削除"""
    item = DelayedItem.query.get_or_404(item_id)

    db.session.delete(item)
    db.session.commit()

    flash('遅れ品を削除しました', 'success')
    return redirect(url_for('admin.delayed_items_list'))


# ==================== JournalData 管理 ====================

@admin_bp.route('/journal-data')
@login_required
@admin_required
def journal_data_list():
    """ジャーナルデータ一覧"""
    page = request.args.get('page', 1, type=int)
    per_page = 50

    # 検索条件
    search_date = request.args.get('search_date', '')
    search_store_no = request.args.get('search_store_no', '')
    search_slip_no = request.args.get('search_slip_no', '')
    search_customer_name = request.args.get('search_customer_name', '')

    query = JournalData.query

    # 検索フィルタ適用
    if search_date:
        try:
            date_obj = datetime.strptime(search_date, '%Y-%m-%d').date()
            query = query.filter(JournalData.date == date_obj)
        except ValueError:
            pass

    if search_store_no:
        query = query.filter(JournalData.store_no.like(f'%{search_store_no}%'))

    if search_slip_no:
        query = query.filter(JournalData.slip_no.like(f'%{search_slip_no}%'))

    if search_customer_name:
        query = query.filter(JournalData.customer_name.like(f'%{search_customer_name}%'))

    journal_data = query.order_by(desc(JournalData.date), desc(JournalData.imported_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('admin/journal_data_list.html',
                         journal_data=journal_data,
                         search_date=search_date,
                         search_store_no=search_store_no,
                         search_slip_no=search_slip_no,
                         search_customer_name=search_customer_name)


@admin_bp.route('/journal-data/create', methods=['GET', 'POST'])
@login_required
@admin_required
def journal_data_create():
    """ジャーナルデータ作成"""
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('日付の形式が正しくありません', 'error')
            return redirect(url_for('admin.journal_data_create'))

        store_no = request.form.get('store_no')
        slip_no = request.form.get('slip_no')
        customer_name = request.form.get('customer_name')
        phone = request.form.get('phone', '')
        slip_content = request.form.get('slip_content', '')

        # 重複チェック
        existing = JournalData.query.filter_by(
            date=date_obj,
            store_no=store_no,
            slip_no=slip_no,
            customer_name=customer_name
        ).first()

        if existing:
            flash('同じレコードが既に存在します', 'error')
            return redirect(url_for('admin.journal_data_create'))

        journal = JournalData(
            date=date_obj,
            store_no=store_no,
            slip_no=slip_no,
            customer_name=customer_name,
            phone=phone,
            slip_content=slip_content,
            imported_at=now_jst()
        )

        db.session.add(journal)
        db.session.commit()

        flash('ジャーナルデータを作成しました', 'success')
        return redirect(url_for('admin.journal_data_list'))

    return render_template('admin/journal_data_form.html', journal=None)


@admin_bp.route('/journal-data/<int:journal_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def journal_data_edit(journal_id):
    """ジャーナルデータ編集"""
    journal = JournalData.query.get_or_404(journal_id)

    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('日付の形式が正しくありません', 'error')
            return redirect(url_for('admin.journal_data_edit', journal_id=journal_id))

        journal.date = date_obj
        journal.store_no = request.form.get('store_no')
        journal.slip_no = request.form.get('slip_no')
        journal.customer_name = request.form.get('customer_name')
        journal.phone = request.form.get('phone', '')
        journal.slip_content = request.form.get('slip_content', '')

        db.session.commit()
        flash('ジャーナルデータを更新しました', 'success')
        return redirect(url_for('admin.journal_data_list'))

    return render_template('admin/journal_data_form.html', journal=journal)


@admin_bp.route('/journal-data/<int:journal_id>/delete', methods=['POST'])
@login_required
@admin_required
def journal_data_delete(journal_id):
    """ジャーナルデータ削除"""
    journal = JournalData.query.get_or_404(journal_id)

    db.session.delete(journal)
    db.session.commit()

    flash('ジャーナルデータを削除しました', 'success')
    return redirect(url_for('admin.journal_data_list'))


@admin_bp.route('/journal-data/import-status', methods=['GET'])
@login_required
@admin_required
def journal_import_status():
    """
    ジャーナルデータ取得状況画面

    横軸: 店舗一覧
    縦軸: 日付
    取得できている欄には件数を表示
    """
    try:
        from datetime import timedelta
        from sqlalchemy import func

        # 対象店舗の定義（順序を保証するためリストのタプルとして定義）
        target_stores = [
            ('0002', 'オザム日の出店'),
            ('0006', '栄町店'),
            ('0007', 'いなげや師岡店'),
            ('0008', '牛浜店'),
            ('0011', '本社青梅店'),
            ('0012', '東青梅店'),
            ('0013', '東福生店'),
            ('0014', '狭山ヶ丘店'),
            ('0016', 'いなげや福生店'),
            ('0019', 'ﾏﾙﾌｼﾞ千ヶ瀬店'),
            ('0020', 'オザム小作店'),
            ('0021', 'コープ新町店'),
            ('0022', '所沢狭山ヶ丘店'),
            ('0024', '秋川店'),
        ]

        # 辞書形式も作成（検索用）
        target_stores_dict = dict(target_stores)

        # 日付範囲の取得（デフォルトは2025年10月1日から今日まで）
        date_from_str = request.args.get('date_from', '').strip()
        date_to_str = request.args.get('date_to', '').strip()
        sort_order = request.args.get('sort_order', 'desc').strip()  # 'asc' または 'desc'

        # sort_orderの検証
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'

        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                flash('開始日付の形式が正しくありません', 'warning')
                date_from = date(2025, 10, 1)  # 2025年10月1日
        else:
            date_from = date(2025, 10, 1)  # 2025年10月1日

        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                flash('終了日付の形式が正しくありません', 'warning')
                date_to = date.today()
        else:
            date_to = date.today()

        # 日付リストを生成（曜日情報付き）
        date_list = []
        current_date = date_from
        weekday_names = ['月', '火', '水', '木', '金', '土', '日']
        while current_date <= date_to:
            weekday_name = weekday_names[current_date.weekday()]
            date_list.append({
                'date': current_date,
                'weekday': weekday_name
            })
            current_date += timedelta(days=1)

        # 日付をソート順に応じてソート
        # descの場合は降順（新しい日付が上）、ascの場合は昇順（古い日付が上）
        date_list.sort(key=lambda x: x['date'], reverse=(sort_order == 'desc'))

        # 各日付×店舗の組み合わせでデータが存在するかを確認
        # クエリ: 店舗番号と日付ごとにデータが存在するか
        status_data = {}

        # 対象店舗コードのリスト
        target_store_codes = [code for code, name in target_stores]

        # データベースから各日付×店舗の組み合わせでデータが存在するかを取得
        # 効率的にクエリを実行するため、一度に全データを取得
        try:
            query = db.session.query(
                JournalData.store_no,
                JournalData.date,
                func.count(JournalData.id).label('count')
            ).filter(
                JournalData.store_no.in_(target_store_codes),
                JournalData.date >= date_from,
                JournalData.date <= date_to
            ).group_by(
                JournalData.store_no,
                JournalData.date
            ).all()

            # 結果を辞書に格納（件数も保持）
            for store_no, journal_date, count in query:
                if store_no not in status_data:
                    status_data[store_no] = {}
                status_data[store_no][journal_date] = {
                    'has_data': count > 0,
                    'count': count
                }
        except Exception as e:
            logger.error(f"データベースクエリエラー: {e}")
            flash(f'データ取得中にエラーが発生しました: {str(e)}', 'error')

        # 統計情報を計算
        total_cells = len(date_list) * len(target_stores)
        filled_cells = 0
        for store_code, store_name in target_stores:
            for date_item in date_list:
                target_date = date_item['date']
                cell_data = status_data.get(store_code, {}).get(target_date, {})
                if isinstance(cell_data, dict) and cell_data.get('has_data', False):
                    filled_cells += 1

        return render_template(
            'admin/journal_import_status.html',
            target_stores=target_stores,
            date_list=date_list,
            status_data=status_data,
            date_from=date_from,
            date_to=date_to,
            date_from_str=date_from_str,
            date_to_str=date_to_str,
            today=date.today(),
            now=now_jst(),
            total_cells=total_cells,
            filled_cells=filled_cells,
            sort_order=sort_order
        )
    except Exception as e:
        logger.error(f"ジャーナルデータ取得状況画面エラー: {e}", exc_info=True)
        flash(f'エラーが発生しました: {str(e)}', 'error')
        return redirect(url_for('admin.journal_data_list'))


@admin_bp.route('/journal-data/fetch-csv-progress/<date_str>', methods=['GET'])
@login_required
@admin_required
def get_journal_csv_fetch_progress(date_str):
    """
    ジャーナルCSVダウンロードの進捗状況を取得（ログファイルの最新20行）

    Args:
        date_str (str): 日付（YYYY-MM-DD形式）

    Returns:
        JSON: ログの最新行
    """
    try:
        from pathlib import Path

        # 今日のログファイルパスを取得
        log_file = Path(f'/var/www/html/king-req/log_cron/hanjow_journal_downloader.log')

        if not log_file.exists():
            return jsonify({
                'success': True,
                'logs': ['ログファイルが見つかりません。処理開始前か、ログファイルがまだ作成されていません。']
            })

        # ファイルの最新20行を取得
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # 最新20行を取得
                last_lines = lines[-20:] if len(lines) > 20 else lines
                # ログメッセージを抽出
                log_messages = []
                for line in last_lines:
                    line = line.strip()
                    if line:
                        # タイムスタンプ部分を除去
                        if ' - ' in line:
                            parts = line.split(' - ', 1)
                            if len(parts) > 1:
                                log_messages.append(parts[1].strip())
                        else:
                            log_messages.append(line)

                return jsonify({
                    'success': True,
                    'logs': log_messages if log_messages else ['ログを読み込み中...']
                })
        except Exception as e:
            logger.error(f"ログファイル読み込みエラー: {e}")
            return jsonify({
                'success': False,
                'logs': [f'ログの読み込みに失敗しました: {str(e)}']
            })

    except Exception as e:
        logger.error(f"進捗取得エラー: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'logs': [f'エラー: {str(e)}']
        })


@admin_bp.route('/journal-data/fetch-csv/<date_str>', methods=['POST'])
@login_required
@admin_required
def fetch_journal_csv_for_date(date_str):
    """
    指定日付のジャーナルCSVをダウンロードして取り込む

    Args:
        date_str (str): 日付（YYYY-MM-DD形式）

    Returns:
        JSON: 処理結果
    """
    import subprocess
    from pathlib import Path

    try:
        # 日付の妥当性チェック
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'message': f'日付の形式が正しくありません: {date_str}'
            }), 400

        # 未来の日付はエラー
        if target_date > date.today():
            return jsonify({
                'success': False,
                'message': f'未来の日付は指定できません: {date_str}'
            }), 400

        # hanjow_journal_downloader.pyのパス
        downloader_script = '/var/www/html/king-req/hanjow_journal_downloader.py'
        python_path = '/var/www/html/king-req/venv-king/bin/python3'

        # スクリプトの存在確認
        if not Path(downloader_script).exists():
            logger.error(f"ダウンローダースクリプトが見つかりません: {downloader_script}")
            return jsonify({
                'success': False,
                'message': 'ジャーナルCSVダウンロードスクリプトが見つかりません'
            }), 500

        logger.info(f"ジャーナルCSVダウンロード開始: {date_str} (ユーザー: {current_user.username})")

        # hanjow_journal_downloader.py を実行（タイムアウト: 5分）
        try:
            result = subprocess.run(
                [python_path, downloader_script, '--date', date_str],
                cwd='/var/www/html/king-req',
                capture_output=True,
                text=True,
                timeout=300,  # 5分
                check=False
            )

            if result.returncode != 0:
                logger.error(f"ジャーナルCSVダウンロードエラー (exit code: {result.returncode})")
                logger.error(f"stderr: {result.stderr}")
                return jsonify({
                    'success': False,
                    'message': f'ジャーナルCSVダウンロードに失敗しました。ログを確認してください。',
                    'details': result.stderr[-500:] if result.stderr else None  # 最後の500文字
                }), 500

            logger.info(f"ジャーナルCSVダウンロード成功: {date_str}")

        except subprocess.TimeoutExpired:
            logger.error(f"ジャーナルCSVダウンロードタイムアウト: {date_str}")
            return jsonify({
                'success': False,
                'message': 'ジャーナルCSVダウンロードがタイムアウトしました（5分以上かかっています）'
            }), 500

        # ダウンロードした.txtファイルをCSVに変換する（extract_journal_data.py を実行）
        logger.info(f"ジャーナル.txtファイルをCSVに変換中: {date_str}")
        try:
            king_req_python = '/var/www/html/king-req/venv-king/bin/python3'
            extract_script = '/var/www/html/king-req/extract_journal_data.py'

            extract_result = subprocess.run(
                [king_req_python, extract_script, date_str],
                cwd='/var/www/html/king-req',
                capture_output=True,
                text=True,
                timeout=300,  # 5分
                check=False
            )

            if extract_result.returncode != 0:
                logger.error(f"ジャーナルCSV変換エラー (exit code: {extract_result.returncode})")
                logger.error(f"stderr: {extract_result.stderr}")
                return jsonify({
                    'success': False,
                    'message': f'ジャーナル.txtファイルのダウンロードには成功しましたが、CSV変換に失敗しました',
                    'download_success': True,
                    'convert_success': False
                }), 500

            logger.info(f"ジャーナルCSV変換成功: {date_str}")

        except subprocess.TimeoutExpired:
            logger.error(f"ジャーナルCSV変換タイムアウト: {date_str}")
            return jsonify({
                'success': False,
                'message': 'ジャーナル.txtファイルのダウンロードには成功しましたが、CSV変換がタイムアウトしました（5分以上かかっています）',
                'download_success': True,
                'convert_success': False
            }), 500
        except Exception as e:
            logger.error(f"ジャーナルCSV変換エラー: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'ジャーナル.txtファイルのダウンロードには成功しましたが、CSV変換に失敗しました: {str(e)}',
                'download_success': True,
                'convert_success': False
            }), 500

        # ダウンロード・変換したCSVファイルのパスを確認
        csv_dir = Path('/var/www/html/king-req/journal_data_csv')
        csv_file = csv_dir / f'journal_data_{target_date.strftime("%Y%m%d")}.csv'

        if not csv_file.exists():
            logger.warning(f"ジャーナルCSVファイルが見つかりません: {csv_file}")
            return jsonify({
                'success': False,
                'message': 'ジャーナル.txtファイルのダウンロードとCSV変換には成功しましたが、CSVファイルが見つかりません'
            }), 500

        # CSVファイルをデータベースに取り込む（run.py import-journal を実行）
        logger.info(f"ジャーナルCSV取り込み開始: {csv_file}")
        try:
            venv_python = '/var/www/html/factory-intake-shipping/venv/bin/python'
            run_script = '/var/www/html/factory-intake-shipping/run.py'

            import_result = subprocess.run(
                [venv_python, run_script, 'import-journal', '--date', date_str],
                cwd='/var/www/html/factory-intake-shipping',
                capture_output=True,
                text=True,
                timeout=300,
                check=False
            )

            if import_result.returncode != 0:
                logger.error(f"ジャーナルCSV取り込みエラー: {import_result.stderr}")
                return jsonify({
                    'success': False,
                    'message': f'CSVのダウンロードには成功しましたが、取り込みに失敗しました',
                    'download_success': True,
                    'import_success': False
                }), 500

            # 出力から結果を解析
            output = import_result.stdout
            created = 0
            skipped = 0
            errors = 0

            # ログから新規作成、スキップ、エラーの件数を抽出
            for line in output.split('\n'):
                if '新規作成:' in line:
                    try:
                        created = int(line.split('新規作成:')[1].split('件')[0].strip())
                    except:
                        pass
                if 'スキップ:' in line:
                    try:
                        skipped = int(line.split('スキップ:')[1].split('件')[0].strip())
                    except:
                        pass
                if 'エラー:' in line:
                    try:
                        errors = int(line.split('エラー:')[1].split('件')[0].strip())
                    except:
                        pass

            logger.info(f"ジャーナルCSV取り込み完了: 作成={created}, スキップ={skipped}, エラー={errors}")

            return jsonify({
                'success': True,
                'message': f'{date_str} のジャーナルCSVダウンロードと取り込みが完了しました',
                'download_success': True,
                'import_result': {
                    'created': created,
                    'skipped': skipped,
                    'errors': errors,
                    'total_rows': created + skipped
                }
            })

        except subprocess.TimeoutExpired:
            logger.error(f"ジャーナルCSV取り込みタイムアウト: {date_str}")
            return jsonify({
                'success': False,
                'message': f'CSVのダウンロードには成功しましたが、取り込みがタイムアウトしました',
                'download_success': True,
                'import_success': False
            }), 500
        except Exception as e:
            logger.error(f"ジャーナルCSV取り込みエラー: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'CSVのダウンロードには成功しましたが、取り込みに失敗しました: {str(e)}',
                'download_success': True,
                'import_success': False
            }), 500

    except Exception as e:
        logger.error(f"ジャーナルCSVダウンロード・取り込みエラー: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500
