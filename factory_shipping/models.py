"""
新・出荷システム - データモデル

データベーステーブルの定義を行います。
将来的に他のシステムと統合する際は、共通モデルをここに配置できます。
"""

from factory_shipping.extensions import db
from flask_login import UserMixin
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash
from factory_shipping.utils import now_jst


class User(UserMixin, db.Model):
    """ユーザーモデル（king-req の auth_users を参照）

    ユーザー管理は king-req 側に一元化済み。このモデルは auth_users テーブルを
    読み書きするだけで、ユーザーのCRUD UIは /admin/users/ (king-req) に存在する。

    既存コードとの互換を保つため、旧スキーマの Boolean フラグ（is_admin ほか）は
    `role` から派生するプロパティとして提供する。
    """

    __tablename__ = 'auth_users'
    __bind_key__ = 'auth_db'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='user', index=True)
    employee_code = db.Column(db.String(50), nullable=True, unique=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    # --- role から派生する旧 Boolean フラグ互換シム ---
    # admin は全ての役割を兼ねる（king-req 側 user_has_role と同等のセマンティクス）
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_store_staff(self):
        return self.role in ('admin', 'shop_staff')

    @property
    def is_factory_staff(self):
        return self.role in ('admin', 'factory_worker')

    @property
    def is_shift_staff(self):
        return self.role in ('admin', 'shift')

    @property
    def is_office_staff(self):
        return self.role in ('admin', 'office')

    # --- パスワード（auth_users は pbkdf2:sha256:260000 を採用） ---
    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256:260000')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Store(db.Model):
    """店舗マスタ"""

    __tablename__ = 'stores'

    id = db.Column(db.Integer, primary_key=True)
    store_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    store_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    # リレーション
    intake_items = db.relationship('IntakeItem', backref='store', lazy='dynamic')
    shipment_logs = db.relationship('ShipmentLog', backref='store', lazy='dynamic')

    def __repr__(self):
        return f'<Store {self.store_code}: {self.store_name}>'


class ItemStatus(db.Model):
    """商品状態マスタ

    商品の状態を管理するマスタテーブル。
    状態は柔軟に追加・変更できるようにデータベースで管理。
    """

    __tablename__ = 'item_statuses'

    id = db.Column(db.Integer, primary_key=True)
    status_code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # コード（例: 'received', 'shipped'）
    status_name = db.Column(db.String(100), nullable=False)  # 表示名（例: '入荷', '出荷済'）
    description = db.Column(db.String(200), nullable=True)  # 説明
    display_order = db.Column(db.Integer, nullable=False, default=0)  # 表示順序
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # 有効/無効
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    # リレーション
    intake_items = db.relationship('IntakeItem', foreign_keys='IntakeItem.status_id', backref='status', lazy='dynamic')
    shipment_logs = db.relationship('ShipmentLog', foreign_keys='ShipmentLog.new_status_id', lazy='dynamic')

    def __repr__(self):
        return f'<ItemStatus {self.status_code}: {self.status_name}>'


# 工場の業務（入荷一覧・出荷スキャン・状態変更・未出荷・遅れ品など）で扱う品目の預り日の下限。
# これより前の品目は、kinglinesystem の会員利用履歴のために 2026-09 に取り込んだ過去分
# （預り日 2021-01-04〜2025-09-30。intake/historical.py）で、業務の画面や処理には出さない。
BUSINESS_MIN_INTAKE_DATE = date(2025, 10, 1)


class IntakeItem(db.Model):
    """入荷データ（CSV取り込み元）= 商品テーブル

    各商品の現在の状態を保持し、状態変更履歴はShipmentLogで管理する。
    """

    __tablename__ = 'intake_items'

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)

    # 店舗情報（CSV取り込み時に設定、非正規化だが検索・表示の高速化のため）
    store_code = db.Column(db.String(10), nullable=False, index=True)  # 店舗コード（例: "024"）
    store_name = db.Column(db.String(100), nullable=True)  # 店舗名（例: "オザム日の出店"）

    # 伝票・タグ情報
    slip_number = db.Column(db.String(20), nullable=True, index=True)  # 伝票No
    tag_number = db.Column(db.String(20), nullable=False, index=True)  # タグ番号（例: "4-212" または "4212"）
    # 同一 (店,日付,伝票,タグ,商品名) 内の出現順（1,2,3…）。空タグの付帯行
    # （会員登録料 / ﾏﾃﾞ早期引取 等）が同一キーに潰れて脱落する不具合の対策。
    # 重複排除キーに商品名＋本連番を含めることで空タグ行を 1:1 保存する。
    # 商品名単位の採番のため、会員登録料は常に seq=1 となりローリング再取込でも冪等。
    line_seq = db.Column(db.Integer, nullable=False, default=1, index=True)

    # 商品・顧客情報
    product_name = db.Column(db.String(200), nullable=True)  # 商品名
    customer_name = db.Column(db.String(100), nullable=True)  # 顧客名
    customer_code = db.Column(db.String(20), nullable=True)  # 顧客ｺｰﾄﾞ（12 桁）。索引は (customer_code, intake_date)

    # 金額
    amount = db.Column(db.Integer, nullable=True)  # 売価（税込、円単位）

    # 日付情報
    intake_date = db.Column(db.Date, nullable=False, index=True)  # 預かり日（重要：検索・ソートのキー）
    scheduled_date = db.Column(db.Date, nullable=True, index=True)  # 出荷予定日（将来用）

    # 現在の状態（最新のShipmentLogの状態と一致）
    status_id = db.Column(db.Integer, db.ForeignKey('item_statuses.id'), nullable=True, index=True)
    shipped_at = db.Column(db.DateTime, nullable=True)  # 最新の状態変更日時

    # お客様への返却日時（JST）。返却日指定 CSV から intake/returns.py が設定する。
    # status_id とは独立に持ち、預り日 CSV の再取り込みや出荷スキャンでは変わらない。
    returned_at = db.Column(db.DateTime, nullable=True, index=True)

    # 入荷状態（通常、工場請求中、完了済み、など）
    intake_status = db.Column(db.String(20), default='通常', nullable=False, index=True)

    # 旧フィールド（後方互換性のため残す）
    item_code = db.Column(db.String(50), nullable=True, index=True)  # 旧: tag_number のエイリアス
    item_name = db.Column(db.String(200), nullable=True)  # 旧: product_name のエイリアス
    quantity = db.Column(db.Integer, nullable=False, default=1)  # 数量（通常は1）

    # 包装・出荷便情報
    wrapping = db.Column(db.String(100), nullable=True)  # 包装
    shipping_method = db.Column(db.String(100), nullable=True)  # 出荷便

    notes = db.Column(db.Text, nullable=True)  # 備考
    imported_at = db.Column(db.DateTime, nullable=True, index=True)  # CSV取り込み日時
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    # リレーション
    shipment_logs = db.relationship('ShipmentLog', backref='intake_item', lazy='dynamic')

    # お客様に返却した品目（returned_at あり）の状態。status_id より優先する。
    # item_statuses には登録しない: 'returned' は「再戻」で使用中で、マスタに足すと
    # 工場画面の手動の状態変更に出てしまうため。
    RETURNED_STATUS_CODE = 'returned_to_customer'
    RETURNED_STATUS_NAME = '返却済'
    # 過去分（預り日が BUSINESS_MIN_INTAKE_DATE より前）で返却の記録が無い品目の状態。
    # 何年も前の品物を「入荷」と出すと店頭で「まだ店にある」と誤解されるため。
    # 返却済と同じく item_statuses には登録しない（表示用の状態）。
    NO_RETURN_RECORD_STATUS_CODE = 'no_return_record'
    NO_RETURN_RECORD_STATUS_NAME = '返却記録なし'

    @classmethod
    def in_business_scope(cls):
        """業務の画面・処理で扱う品目の条件（過去分を除く）。query.filter() に渡す。"""
        return cls.intake_date >= BUSINESS_MIN_INTAKE_DATE

    @property
    def display_status(self):
        """画面・API に出す状態 (status_code, status_name)。未設定なら (None, None)。

        返却済 > 返却記録なし（過去分） > 工場側の状態 の順に決める。
        """
        if self.returned_at is not None:
            return self.RETURNED_STATUS_CODE, self.RETURNED_STATUS_NAME
        if self.intake_date is not None and self.intake_date < BUSINESS_MIN_INTAKE_DATE:
            return self.NO_RETURN_RECORD_STATUS_CODE, self.NO_RETURN_RECORD_STATUS_NAME
        if self.status:
            return self.status.status_code, self.status.status_name
        return None, None

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
    """出荷ログ（状態変更履歴）

    商品の状態変更履歴を記録する。
    各レコードは状態変更を表し、最新のレコードの状態が商品の現在の状態と一致する。
    """

    __tablename__ = 'shipment_logs'

    id = db.Column(db.Integer, primary_key=True)
    intake_item_id = db.Column(db.Integer, db.ForeignKey('intake_items.id'), nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)

    # 複合キー（店舗コード + 預かり日 + タグ番号）
    store_code = db.Column(db.String(20), nullable=True, index=True)  # 店舗コード
    intake_date = db.Column(db.Date, nullable=True, index=True)  # 預かり日
    tag_number = db.Column(db.String(20), nullable=True, index=True)  # タグ番号
    history_number = db.Column(db.Integer, nullable=True)  # 履歴番号（同じ商品の何回目の変更か）

    # scanned_by_user_id は king-req の auth_users.id を参照する。
    # cross-bind のためFK制約・relationship は定義せず、`scanned_by` プロパティで解決する。
    scanned_by_user_id = db.Column(db.Integer, nullable=True)
    operator_id = db.Column(db.Integer, db.ForeignKey('factory_operators.id'), nullable=True, index=True)  # 担当者ID
    scanned_at = db.Column(db.DateTime, default=now_jst, nullable=False, index=True)
    scanned_code = db.Column(db.String(100), nullable=True)  # バーコード（手動変更の場合はNULL）

    # 状態変更
    new_status_id = db.Column(db.Integer, db.ForeignKey('item_statuses.id'), nullable=True, index=True)  # 変更後の状態

    # 後方互換性のため残す
    status = db.Column(db.String(20), default='completed', nullable=False)  # completed, error など

    notes = db.Column(db.Text, nullable=True)  # 備考・理由

    # リレーション
    operator = db.relationship('FactoryOperator', backref='shipment_logs')
    new_status = db.relationship('ItemStatus', foreign_keys=[new_status_id])

    @property
    def scanned_by(self):
        """スキャン実行ユーザー（auth_users 参照）。後方互換のため relationship と同名のプロパティを提供。"""
        if not self.scanned_by_user_id:
            return None
        return User.query.get(self.scanned_by_user_id)

    def __repr__(self):
        return f'<ShipmentLog Item#{self.intake_item_id} at {self.scanned_at}>'


class DelayedItem(db.Model):
    """遅れ品管理"""

    __tablename__ = 'delayed_items'

    id = db.Column(db.Integer, primary_key=True)
    intake_item_id = db.Column(db.Integer, db.ForeignKey('intake_items.id'), nullable=False, index=True)
    delay_reason = db.Column(db.String(200), nullable=True)
    expected_date = db.Column(db.Date, nullable=True)
    resolved = db.Column(db.Boolean, default=False, nullable=False, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    # リレーション
    intake_item = db.relationship('IntakeItem', backref='delayed_items')

    def __repr__(self):
        return f'<DelayedItem {self.intake_item_id}: {self.delay_reason}>'


class FactoryOperator(db.Model):
    """工場担当者マスター

    工場の従業員（担当者）を管理する。
    ログインユーザーとは別に、実際に出荷作業を行う担当者を記録する。
    """

    __tablename__ = 'factory_operators'

    id = db.Column(db.Integer, primary_key=True)
    operator_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    operator_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    def __repr__(self):
        return f'<FactoryOperator {self.operator_code}: {self.operator_name}>'


class JournalData(db.Model):
    """ジャーナルデータ

    日次でCSVからインポートされるジャーナルデータを管理する。
    顧客情報や伝票情報を記録し、検索・分析に使用する。
    """

    __tablename__ = 'journal_data'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)  # 日付
    store_no = db.Column(db.String(10), nullable=False, index=True)  # 店舗番号
    slip_no = db.Column(db.String(20), nullable=False, index=True)  # 伝票番号
    customer_name = db.Column(db.String(100), nullable=True, index=True)  # 顧客名
    phone = db.Column(db.String(20), nullable=True)  # 電話番号
    slip_content = db.Column(db.Text, nullable=True)  # 伝票内容
    imported_at = db.Column(db.DateTime, nullable=False)  # インポート日時
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    def __repr__(self):
        return f'<JournalData {self.date} {self.store_no}/{self.slip_no}: {self.customer_name}>'


class JournalDownloadNote(db.Model):
    """ジャーナルダウンロードメモ（日付単位）

    ダウンロードできなかった日付に管理者がメモを残すためのモデル。
    """

    __tablename__ = 'journal_download_notes'

    date = db.Column(db.Date, primary_key=True)
    note = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=now_jst, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_jst, onupdate=now_jst, nullable=False)

    def __repr__(self):
        return f'<JournalDownloadNote {self.date}: {self.note[:30]}>'
