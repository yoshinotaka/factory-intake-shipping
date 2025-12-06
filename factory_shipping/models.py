"""
新・出荷システム - データモデル

データベーステーブルの定義を行います。
将来的に他のシステムと統合する際は、共通モデルをここに配置できます。
"""

from factory_shipping.extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    """ユーザーモデル"""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def set_password(self, password):
        """パスワードをハッシュ化して保存"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """パスワードの検証"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Store(db.Model):
    """店舗マスタ"""

    __tablename__ = 'stores'

    id = db.Column(db.Integer, primary_key=True)
    store_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    store_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # リレーション
    intake_items = db.relationship('IntakeItem', backref='store', lazy='dynamic')
    shipment_logs = db.relationship('ShipmentLog', backref='store', lazy='dynamic')

    def __repr__(self):
        return f'<Store {self.store_code}: {self.store_name}>'


class IntakeItem(db.Model):
    """入荷データ（CSV取り込み元）"""

    __tablename__ = 'intake_items'

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)

    # 店舗情報（CSV取り込み時に設定、非正規化だが検索・表示の高速化のため）
    store_code = db.Column(db.String(10), nullable=False, index=True)  # 店舗コード（例: "024"）
    store_name = db.Column(db.String(100), nullable=True)  # 店舗名（例: "オザム日の出店"）

    # 伝票・タグ情報
    slip_number = db.Column(db.String(20), nullable=True, index=True)  # 伝票No
    tag_number = db.Column(db.String(20), nullable=False, index=True)  # タグ番号（例: "4-212" または "4212"）

    # 商品・顧客情報
    product_name = db.Column(db.String(200), nullable=True)  # 商品名
    customer_name = db.Column(db.String(100), nullable=True)  # 顧客名

    # 金額
    amount = db.Column(db.Integer, nullable=True)  # 売価（税込、円単位）

    # 日付情報
    intake_date = db.Column(db.Date, nullable=False, index=True)  # 預かり日（重要：検索・ソートのキー）
    scheduled_date = db.Column(db.Date, nullable=True, index=True)  # 出荷予定日（将来用）

    # 出荷状態
    is_shipped = db.Column(db.Boolean, default=False, nullable=False, index=True)
    shipped_at = db.Column(db.DateTime, nullable=True)  # 出荷日時

    # 入荷状態（通常、工場請求中、完了済み、など）
    intake_status = db.Column(db.String(20), default='通常', nullable=False, index=True)

    # 旧フィールド（後方互換性のため残す）
    item_code = db.Column(db.String(50), nullable=True, index=True)  # 旧: tag_number のエイリアス
    item_name = db.Column(db.String(200), nullable=True)  # 旧: product_name のエイリアス
    quantity = db.Column(db.Integer, nullable=False, default=1)  # 数量（通常は1）

    notes = db.Column(db.Text, nullable=True)  # 備考
    imported_at = db.Column(db.DateTime, nullable=True, index=True)  # CSV取り込み日時
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # リレーション
    shipment_logs = db.relationship('ShipmentLog', backref='intake_item', lazy='dynamic')

    def get_formatted_tag_number(self):
        """タグ番号を0-000形式で返す（先頭1桁を除去）"""
        if not self.tag_number:
            return ''
        # タグ番号から先頭1文字を除去して、残りを0-000形式に整形
        tag = self.tag_number.replace('-', '')  # ハイフンを除去
        if len(tag) >= 4:
            # 先頭1桁を除いた残り4桁を0-000形式に
            return f"{tag[1]}-{tag[2:5]}"
        return self.tag_number  # 4桁未満の場合はそのまま返す

    def __repr__(self):
        return f'<IntakeItem {self.store_code}/{self.tag_number}: {self.product_name}>'


class ShipmentLog(db.Model):
    """出荷ログ（スキャン履歴）"""

    __tablename__ = 'shipment_logs'

    id = db.Column(db.Integer, primary_key=True)
    intake_item_id = db.Column(db.Integer, db.ForeignKey('intake_items.id'), nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)
    scanned_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    scanned_code = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='completed', nullable=False)  # completed, error など
    notes = db.Column(db.Text, nullable=True)

    # リレーション
    scanned_by = db.relationship('User', backref='shipment_logs')

    def __repr__(self):
        return f'<ShipmentLog {self.scanned_code} at {self.scanned_at}>'


class DelayedItem(db.Model):
    """遅れ品管理"""

    __tablename__ = 'delayed_items'

    id = db.Column(db.Integer, primary_key=True)
    intake_item_id = db.Column(db.Integer, db.ForeignKey('intake_items.id'), nullable=False, index=True)
    delay_reason = db.Column(db.String(200), nullable=True)
    expected_date = db.Column(db.Date, nullable=True)
    resolved = db.Column(db.Boolean, default=False, nullable=False, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # リレーション
    intake_item = db.relationship('IntakeItem', backref='delayed_items')

    def __repr__(self):
        return f'<DelayedItem {self.intake_item_id}: {self.delay_reason}>'
