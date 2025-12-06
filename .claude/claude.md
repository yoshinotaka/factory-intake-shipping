# 新・出荷システム - プロジェクトガイド

このドキュメントは、AI アシスタントや新しい開発者がプロジェクトを理解するための包括的なガイドです。

---

## 📋 プロジェクト概要

### システム名
**新・出荷システム（Factory Intake & Shipping System）**

### 目的
工場での入荷・出荷管理を効率化し、リアルタイムでステータスを把握できるようにする。

### 主要機能
1. **入荷管理**: CSV ファイルからのデータ取り込み
2. **出荷スキャン**: バーコードスキャンによる出荷登録
3. **未出荷一覧**: 未出荷商品の一覧表示
4. **遅れ品管理**: 予定日を過ぎた商品の管理
5. **認証機能**: ユーザーログイン・権限管理

### URL プレフィックス
- すべてのエンドポイントは `/fi/` 配下に配置
- 例: `http://example.com/fi/intake/`, `http://example.com/fi/shipping/`

### 対象ユーザー
- 工場スタッフ（入荷・出荷担当者）
- 管理者（全体のステータス確認）

---

## 🏗️ 技術スタック

### バックエンド
- **Python**: 3.9+（推奨: 3.10+）
- **Flask**: 3.0.0+ - Web フレームワーク
- **Flask-SQLAlchemy**: 3.1.0+ - ORM
- **Flask-Login**: 0.6.3+ - 認証管理
- **Alembic**: 1.13.0+ - データベースマイグレーション
- **Gunicorn**: 21.2.0+ - WSGI サーバー

### データベース
- **MySQL/MariaDB**: 5.7+ / 10.3+
- **PyMySQL**: MySQL ドライバー

### フロントエンド
- **Bootstrap 5.3**: UI フレームワーク
- **Vanilla JavaScript**: 最小限の JS

### デプロイメント
- **systemd**: サービス管理
- **Apache 2.4+ / Nginx 1.18+**: リバースプロキシ
- **Unix Socket**: Gunicorn ⇔ Web サーバー間の通信

---

## 📁 ディレクトリ構造

```
/var/www/html/factory-intake-shipping/
│
├── 🔧 設定ファイル
│   ├── config.py                      # 環境別設定（開発/本番/テスト）
│   ├── .env                           # 環境変数（Git 管理外）
│   ├── .env.example                   # 環境変数テンプレート
│   └── requirements.txt               # Python パッケージ依存関係
│
├── 🚀 エントリポイント
│   ├── run.py                         # 開発サーバー起動 & CLI コマンド
│   └── setup_venv.sh                  # 仮想環境セットアップスクリプト
│
├── 📦 アプリケーション本体
│   └── factory_shipping/
│       ├── __init__.py                # アプリケーションファクトリ（create_app）
│       ├── extensions.py              # Flask 拡張機能（db, login_manager）
│       ├── models.py                  # データモデル（ORM）
│       ├── views.py                   # メインビュー（ルートパス）
│       │
│       ├── intake/                    # 入荷機能モジュール
│       │   ├── __init__.py
│       │   └── views.py               # Blueprint: intake_bp
│       │
│       ├── shipping/                  # 出荷機能モジュール
│       │   ├── __init__.py
│       │   └── views.py               # Blueprint: shipping_bp
│       │
│       ├── status/                    # ステータス確認モジュール
│       │   ├── __init__.py
│       │   └── views.py               # Blueprint: status_bp
│       │
│       └── auth/                      # 認証機能モジュール
│           ├── __init__.py
│           └── views.py               # Blueprint: auth_bp
│
├── 🎨 テンプレート & 静的ファイル
│   ├── templates/
│   │   ├── base.html                  # ベーステンプレート
│   │   ├── index.html                 # ホーム画面
│   │   ├── auth/                      # 認証関連テンプレート
│   │   ├── intake/                    # 入荷関連テンプレート
│   │   ├── shipping/                  # 出荷関連テンプレート
│   │   ├── status/                    # ステータス関連テンプレート
│   │   └── errors/                    # エラーページ（404, 500, 403）
│   │
│   └── static/
│       ├── css/style.css              # カスタムスタイル
│       └── js/main.js                 # JavaScript
│
├── 🗄️ データベース
│   └── migrations/                    # Alembic マイグレーション
│
├── 🚢 デプロイメント設定
│   └── deployment/
│       ├── factory-shipping.service   # systemd サービスファイル
│       ├── gunicorn_config.py         # Gunicorn 設定
│       ├── apache-vhost.conf          # Apache 設定例
│       └── nginx-site.conf            # Nginx 設定例
│
├── 📚 ドキュメント
│   ├── README.md                      # セットアップ手順書
│   └── docs/
│       └── DEPLOYMENT.md              # デプロイメントガイド
│
├── 📤 データファイル
│   └── uploads/                       # CSV アップロード保存先
│
└── 🔒 Git 管理
    ├── .gitignore                     # Git 除外設定
    └── .claude/                       # Claude 用設定
        ├── claude.md                  # このファイル
        └── settings.local.json        # Claude Code 設定
```

---

## 🎯 アーキテクチャ設計

### アプリケーションファクトリパターン

**理由**: 環境ごとに異なる設定を使用でき、テストしやすくなる

**実装場所**: `factory_shipping/__init__.py`

```python
def create_app(config_name=None):
    """
    Flask アプリケーションを作成する

    Args:
        config_name: 'development', 'production', 'testing'

    Returns:
        Flask アプリケーションインスタンス
    """
    app = Flask(__name__)

    # 設定の読み込み
    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # 拡張機能の初期化
    init_extensions(app)

    # ブループリントの登録
    register_blueprints(app)

    return app
```

### ブループリント構成

各機能はブループリントとして独立したモジュールになっている。

| ブループリント | URL プレフィックス | 機能 |
|--------------|------------------|------|
| `main_bp` | `/fi` | ホーム画面・ダッシュボード |
| `auth_bp` | `/fi/auth` | ログイン・ログアウト・認証 |
| `intake_bp` | `/fi/intake` | CSV 取り込み・入荷管理 |
| `shipping_bp` | `/fi/shipping` | バーコードスキャン・出荷登録 |
| `status_bp` | `/fi/status` | 未出荷一覧・遅れ品管理 |

### データベース設計

#### テーブル一覧

1. **users** - ユーザー情報
2. **stores** - 店舗マスタ
3. **intake_items** - 入荷データ
4. **shipment_logs** - 出荷ログ
5. **delayed_items** - 遅れ品管理

#### ER 図（概要）

```
users (1) ─────< (N) shipment_logs

stores (1) ─────< (N) intake_items
stores (1) ─────< (N) shipment_logs

intake_items (1) ─────< (N) shipment_logs
intake_items (1) ─────< (N) delayed_items
```

#### 主要モデルの説明

**User モデル** (`factory_shipping/models.py:13`)
```python
class User(UserMixin, db.Model):
    """ユーザーモデル"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
```

**IntakeItem モデル** (`factory_shipping/models.py:59`)
```python
class IntakeItem(db.Model):
    """入荷データ"""
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'))
    item_code = db.Column(db.String(50), nullable=False)
    item_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, default=0)
    scheduled_date = db.Column(db.Date)
    is_shipped = db.Column(db.Boolean, default=False)
    shipped_at = db.Column(db.DateTime)
```

**ShipmentLog モデル** (`factory_shipping/models.py:85`)
```python
class ShipmentLog(db.Model):
    """出荷ログ（スキャン履歴）"""
    id = db.Column(db.Integer, primary_key=True)
    intake_item_id = db.Column(db.Integer, db.ForeignKey('intake_items.id'))
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'))
    scanned_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    scanned_code = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='completed')
```

---

## 🔧 開発ガイドライン

### 環境セットアップ（開発者向け）

```bash
# 1. リポジトリをクローン（または既存ディレクトリに移動）
cd /var/www/html/factory-intake-shipping

# 2. 仮想環境をセットアップ
bash setup_venv.sh python3.10

# 3. 環境変数を設定
cp .env.example .env
vi .env  # SECRET_KEY と DATABASE_URL を設定

# 4. データベースを準備
python run.py init-db
python run.py seed-db

# 5. 開発サーバーを起動
python run.py
```

### コーディング規約

#### Python コード

- **PEP 8** に準拠
- 日本語コメントを使用（可読性優先）
- docstring は日本語でも可
- インデント: スペース 4 つ

**関数の docstring 例:**
```python
def create_app(config_name=None):
    """
    Flask アプリケーションを作成する

    Args:
        config_name (str): 環境名 ('development', 'production', 'testing')

    Returns:
        Flask: 設定済みの Flask アプリケーション
    """
    pass
```

#### テンプレート（Jinja2）

- インデント: スペース 2 つ
- ブロック名は明確に（`{% block content %}`, `{% block extra_js %}` など）
- すべてのテンプレートは `base.html` を継承

#### JavaScript

- ES6+ を使用
- コメントは日本語でも可
- イベントリスナーは `DOMContentLoaded` 後に登録

#### CSS

- クラス名は BEM 記法に準拠（緩め）
- Bootstrap のユーティリティクラスを優先使用

### ブランチ戦略（Git を使用する場合）

- `main`: 本番環境用（安定版）
- `develop`: 開発版
- `feature/xxx`: 新機能開発
- `bugfix/xxx`: バグ修正
- `hotfix/xxx`: 緊急修正

### コミットメッセージ規約

```
[種別] 概要（50文字以内）

詳細説明（必要に応じて）

例:
[feat] 出荷スキャン機能のバーコード読み取りを実装
[fix] ログイン後のリダイレクト先が正しくない問題を修正
[docs] README にデプロイ手順を追加
[refactor] IntakeItem モデルのクエリを最適化
```

---

## 🛠️ よくある開発タスク

### 新しいブループリント（機能モジュール）の追加

1. **ディレクトリ作成**
```bash
mkdir -p factory_shipping/new_feature
touch factory_shipping/new_feature/__init__.py
touch factory_shipping/new_feature/views.py
```

2. **ブループリント定義** (`factory_shipping/new_feature/views.py`)
```python
from flask import Blueprint, render_template
from flask_login import login_required

new_feature_bp = Blueprint('new_feature', __name__)

@new_feature_bp.route('/')
@login_required
def index():
    return render_template('new_feature/index.html')
```

3. **ブループリント登録** (`factory_shipping/__init__.py:32`)
```python
def register_blueprints(app):
    # 既存のブループリント...

    # 新しいブループリントを追加
    from factory_shipping.new_feature.views import new_feature_bp
    app.register_blueprint(new_feature_bp, url_prefix='/fi/new_feature')
```

4. **テンプレート作成**
```bash
mkdir -p templates/new_feature
touch templates/new_feature/index.html
```

### 新しいモデルの追加

1. **モデル定義** (`factory_shipping/models.py`)
```python
class NewModel(db.Model):
    """新しいモデルの説明"""
    __tablename__ = 'new_models'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

2. **マイグレーション作成**
```bash
alembic revision --autogenerate -m "Add NewModel"
```

3. **マイグレーション適用**
```bash
alembic upgrade head
```

### API エンドポイントの追加（JSON レスポンス）

```python
from flask import jsonify

@shipping_bp.route('/api/scan', methods=['POST'])
@login_required
def api_scan():
    """出荷スキャン API"""
    data = request.get_json()

    # 処理...

    return jsonify({
        'success': True,
        'message': 'スキャン完了',
        'data': {...}
    })
```

---

## 🔐 セキュリティ考慮事項

### 実装済みのセキュリティ対策

1. **パスワード管理**
   - Werkzeug の `generate_password_hash` でハッシュ化
   - 平文パスワードは保存しない

2. **認証**
   - Flask-Login によるセッション管理
   - `@login_required` デコレータで保護

3. **SQL インジェクション対策**
   - SQLAlchemy ORM を使用（パラメータバインド）

4. **XSS 対策**
   - Jinja2 の自動エスケープ機能

5. **CSRF 対策**
   - Flask-WTF（導入予定）

### 今後実装すべき対策

- [ ] CSRF トークンの実装（Flask-WTF）
- [ ] レート制限（Flask-Limiter）
- [ ] セッションタイムアウト設定
- [ ] ファイルアップロードの検証強化
- [ ] セキュリティヘッダーの追加（CSP, HSTS など）

---

## 🚀 デプロイメント

### 開発環境

```bash
# 開発サーバー起動
python run.py

# アクセス
http://localhost:5000/fi/
```

### 本番環境

1. **Gunicorn + systemd**
   - サービスファイル: `deployment/factory-shipping.service`
   - 設定ファイル: `deployment/gunicorn_config.py`

2. **リバースプロキシ**
   - Apache: `deployment/apache-vhost.conf`
   - Nginx: `deployment/nginx-site.conf`

3. **起動コマンド**
```bash
sudo systemctl start factory-shipping
sudo systemctl status factory-shipping
```

詳細は `docs/DEPLOYMENT.md` を参照。

---

## 🧪 テスト（今後実装予定）

### ユニットテスト

```bash
# pytest をインストール
pip install pytest pytest-flask

# テスト実行
pytest tests/
```

### テストファイル構成（推奨）

```
tests/
├── __init__.py
├── conftest.py              # pytest 設定
├── test_models.py           # モデルのテスト
├── test_auth.py             # 認証機能のテスト
├── test_intake.py           # 入荷機能のテスト
└── test_shipping.py         # 出荷機能のテスト
```

---

## 🔄 将来の拡張計画

### 共通ライブラリ化

現在の構成では、将来的に他のシステム（旧システム `/var/www/html/king-req/` など）と統合しやすいように設計されています。

**共通化の手順:**

1. **共通モジュールの切り出し**
```
/var/www/html/factory-systems/
├── common/                    # 共通ライブラリ
│   ├── __init__.py
│   ├── models.py              # 共通モデル（User, Store など）
│   ├── extensions.py          # 共通拡張機能
│   └── utils.py               # ユーティリティ
│
├── intake-shipping/           # 新・出荷システム
├── king-req/                  # 旧システム
└── shared-config/             # 共通設定
```

2. **インポートパスの変更**
```python
# 変更前
from factory_shipping.models import User

# 変更後
from common.models import User
```

3. **共通データベースの利用**
   - テーブルプレフィックスで分離
   - 例: `fs_users`, `kr_users`

### API 化

REST API を提供し、他のシステムから利用できるようにする。

**エンドポイント例:**
```
GET    /fi/api/v1/intake/items          # 入荷データ一覧
POST   /fi/api/v1/intake/items          # 入荷データ作成
GET    /fi/api/v1/shipping/scan         # スキャン情報取得
POST   /fi/api/v1/shipping/scan         # スキャン実行
GET    /fi/api/v1/status/unshipped      # 未出荷一覧
```

### フロントエンド強化

- Vue.js / React による SPA 化
- リアルタイム更新（WebSocket）
- モバイル対応の強化

---

## 📊 パフォーマンス最適化

### データベース

- インデックスの最適化
  - `item_code`, `store_id`, `is_shipped`, `scheduled_date` にインデックス
- クエリの最適化
  - N+1 問題の回避（`joinedload`, `selectinload`）
- コネクションプーリング
  - `pool_size=10`, `pool_recycle=3600`

### キャッシュ

- Flask-Caching の導入（検討中）
- Redis によるセッション管理（検討中）

### 静的ファイル

- CDN の利用（Bootstrap, jQuery など）
- Nginx/Apache から直接配信

---

## 🐛 トラブルシューティング

### よくあるエラーと対処法

#### 1. "No module named 'factory_shipping'"
```bash
# 原因: venv が有効化されていない
# 対処:
source venv/bin/activate
```

#### 2. "Access denied for user"
```bash
# 原因: データベース接続情報が正しくない
# 対処:
vi .env  # DATABASE_URL を確認
mysql -u factory_user -p  # 接続テスト
```

#### 3. "502 Bad Gateway"
```bash
# 原因: Gunicorn が起動していない
# 対処:
sudo systemctl status factory-shipping
sudo systemctl start factory-shipping
```

#### 4. "Template not found"
```bash
# 原因: テンプレートパスが正しくない
# 対処:
# templates/ ディレクトリが正しい場所にあるか確認
ls templates/
```

---

## 📝 運用コマンド一覧

### 開発

```bash
# 開発サーバー起動
python run.py

# データベース初期化
python run.py init-db

# サンプルデータ投入
python run.py seed-db

# データベース削除（開発用）
python run.py drop-db
```

### マイグレーション

```bash
# Alembic 初期化
alembic init migrations

# マイグレーション作成
alembic revision --autogenerate -m "説明"

# マイグレーション適用
alembic upgrade head

# ロールバック
alembic downgrade -1
```

### 本番環境

#### factory-shippingサービスの管理

```bash
# サービス起動
sudo systemctl start factory-shipping

# サービス停止
sudo systemctl stop factory-shipping

# サービス再起動
sudo systemctl restart factory-shipping

# ステータス確認
sudo systemctl status factory-shipping

# ログ確認（リアルタイム）
sudo journalctl -u factory-shipping -f

# エラーログ確認
sudo tail -f /var/log/factory-shipping/error.log

# アクセスログ確認
sudo tail -f /var/log/factory-shipping/access.log

# 自動起動の有効化確認
sudo systemctl is-enabled factory-shipping

# 自動起動を有効化
sudo systemctl enable factory-shipping
```

#### Nginxの管理

```bash
# 設定ファイルのテスト
sudo nginx -t

# 設定をリロード（ダウンタイムなし）
sudo systemctl reload nginx

# 完全再起動
sudo systemctl restart nginx

# ステータス確認
sudo systemctl status nginx

# エラーログ確認
sudo tail -f /var/log/nginx/error.log

# アクセスログ確認
sudo tail -f /var/log/nginx/access.log
```

#### 再起動後の動作確認

```bash
# ソケットファイルの確認
ls -la /var/www/html/factory-intake-shipping/gunicorn.sock

# 動作確認（302リダイレクトが返れば正常）
curl -k -I https://factory.kingdrysystem.com/fi/intake/list

# サービスプロセスの確認
ps aux | grep gunicorn | grep factory
```

#### トラブルシューティング（再起動時）

```bash
# ソケットファイルの権限エラーが発生した場合
sudo chmod 666 /var/www/html/factory-intake-shipping/gunicorn.sock

# サービスが起動しない場合
sudo journalctl -u factory-shipping --no-pager -n 50

# Nginxが502エラーを返す場合
# 1. Gunicornが起動しているか確認
sudo systemctl status factory-shipping

# 2. ソケットファイルの権限を確認
ls -la /var/www/html/factory-intake-shipping/gunicorn.sock

# 3. Nginxのエラーログを確認
sudo tail -20 /var/log/nginx/error.log
```

### バックアップ

```bash
# データベースバックアップ
mysqldump -u factory_user -p factory_shipping > backup_$(date +%Y%m%d).sql

# リストア
mysql -u factory_user -p factory_shipping < backup_20250129.sql
```

---

## 🔗 関連リソース

### 公式ドキュメント

- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Flask-Login Documentation](https://flask-login.readthedocs.io/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Gunicorn Documentation](https://docs.gunicorn.org/)

### プロジェクト内ドキュメント

- `README.md` - セットアップ手順
- `docs/DEPLOYMENT.md` - デプロイメントガイド
- `.env.example` - 環境変数テンプレート

---

## 👥 開発チーム

### 主要な責任者

- **システム管理者**: プロジェクト全体の管理
- **バックエンド開発**: Python/Flask 開発
- **フロントエンド開発**: HTML/CSS/JavaScript
- **データベース管理**: MySQL 運用・最適化

---

## 📅 変更履歴

### v1.0.0 (2025-01-29)

- 初期リリース
- 基本的な入荷・出荷管理機能を実装
- 認証機能実装
- systemd サービス対応

---

## 💡 開発のヒント

### 新しい機能を追加する際のチェックリスト

- [ ] モデルの定義（必要な場合）
- [ ] マイグレーションの作成と適用
- [ ] ビュー関数の実装
- [ ] テンプレートの作成
- [ ] ブループリントの登録
- [ ] URL ルーティングの確認
- [ ] 権限チェック（`@login_required`）
- [ ] エラーハンドリング
- [ ] ログ出力
- [ ] テストの作成（今後）
- [ ] ドキュメントの更新

### コードレビューのポイント

1. **セキュリティ**: SQL インジェクション、XSS、CSRF
2. **パフォーマンス**: N+1 問題、インデックス
3. **可読性**: コメント、変数名、関数名
4. **エラーハンドリング**: 例外処理、ユーザーへのフィードバック
5. **一貫性**: コーディング規約に準拠しているか

---

## 🎓 学習リソース

### Python/Flask 初心者向け

- [Flask Mega-Tutorial](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world)
- [Real Python - Flask Tutorials](https://realpython.com/tutorials/flask/)

### データベース設計

- [SQLAlchemy ORM Tutorial](https://docs.sqlalchemy.org/en/20/orm/tutorial.html)
- [データベース設計入門](https://qiita.com/nishina555/items/a79ece1b54faf7240fac)

---

このドキュメントは、プロジェクトの成長に合わせて更新してください。
