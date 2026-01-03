# 工場入荷・出荷管理システム プロジェクトマニュアル

## 📋 目次

1. [プロジェクト概要](#プロジェクト概要)
2. [システム構成](#システム構成)
3. [主要機能](#主要機能)
4. [技術スタック](#技術スタック)
5. [ディレクトリ構成](#ディレクトリ構成)
6. [セットアップ手順](#セットアップ手順)
7. [運用方法](#運用方法)
8. [データフロー](#データフロー)
9. [API・エンドポイント](#apiエンドポイント)
10. [データベーススキーマ](#データベーススキーマ)
11. [トラブルシューティング](#トラブルシューティング)
12. [関連ドキュメント](#関連ドキュメント)

---

## プロジェクト概要

### システム名
**新・出荷システム（Factory Intake & Shipping System）**

### 目的
工場での入荷・出荷管理を効率化するためのWebアプリケーション。旧システム（king-req）から生成されるCSVデータを取り込み、バーコードスキャンによる出荷処理を実現します。

### 主な特徴
- ✅ **自動データ取り込み**: 毎日自動でCSVファイルを取り込み
- ✅ **バーコード出荷**: HIDバーコードリーダーによる高速出荷処理
- ✅ **重複防止**: 自動重複チェック機能
- ✅ **履歴管理**: すべての出荷処理を記録
- ✅ **モニタリング**: ログ閲覧・ステータス確認機能
- ✅ **管理者機能**: ユーザー管理・データ管理

### 開発・運用環境
- **本番URL**: https://factory.kingdrysystem.com/fi/
- **GitHubリポジトリ**: https://github.com/yoshinotaka/factory-intake-shipping
- **サーバーパス**: `/var/www/html/factory-intake-shipping`

---

## システム構成

### アーキテクチャ

```
┌─────────────────┐
│   Web Browser   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Apache/Nginx   │ (リバースプロキシ)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Gunicorn     │ (WSGI サーバー)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Flask App      │ (factory_shipping)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     MySQL       │ (データベース)
└─────────────────┘
```

### 外部システム連携

```
┌──────────────────┐
│  king-req システム│
│  (旧システム)     │
└────────┬─────────┘
         │ CSV生成 (22:30)
         ▼
┌──────────────────┐
│  CSV ファイル     │
│  downloads_hanjow │
└────────┬─────────┘
         │ 自動取り込み (22:35)
         ▼
┌──────────────────┐
│  新・出荷システム │
└──────────────────┘
```

---

## 主要機能

### 1. 入荷管理機能

#### 1.1 CSV取り込み
- **自動取り込み**: 毎日22:35に自動実行（cron）
- **手動取り込み**: Web UIから日付指定またはファイルアップロード
- **一括取り込み**: 複数日分をまとめて取り込み
- **重複チェック**: 店舗コード + 預かり日 + タグ番号 + 伝票番号で重複を防止

#### 1.2 入荷データ一覧
- **URL**: `/fi/intake/list`
- **機能**:
  - ページング表示（25/50/100/200件/ページ）
  - 店舗・日付範囲・出荷ステータスでの絞り込み
  - 預かり日が古い順にソート（未出荷優先）
  - バーコード入力による即座の出荷処理

#### 1.3 入荷ステータス確認
- **URL**: `/fi/intake/import-status`
- **機能**:
  - 店舗別・日付別の取り込み状況を一覧表示
  - 未取得データをクリックしてCSVダウンロード・取り込み

### 2. 出荷管理機能

#### 2.1 バーコード出荷
- **URL**: `/fi/shipping/scan`
- **機能**:
  - HIDバーコードリーダーによる高速スキャン
  - 9桁バーコードから店舗コードとタグ番号を自動抽出
  - 即座に出荷処理を実行
  - 成功/エラーメッセージをリアルタイム表示

#### 2.2 出荷履歴
- **URL**: `/fi/shipping/history`
- **機能**:
  - 出荷処理の履歴を一覧表示
  - 担当者・日時・状態を記録

### 3. ステータス確認機能

#### 3.1 未出荷一覧
- **URL**: `/fi/status/unshipped`
- **機能**: 未出荷商品の一覧表示

#### 3.2 遅れ品管理
- **URL**: `/fi/status/delayed`
- **機能**: 予定日を過ぎた商品の管理

### 4. モニタリング機能

#### 4.1 ログ閲覧
- **URL**: `/fi/monitoring/`
- **機能**:
  - CSVダウンロードログ
  - CSV取り込みログ
  - アプリケーションログ
  - アクセスログ

### 5. 管理者機能

#### 5.1 ユーザー管理
- **URL**: `/fi/admin/users`
- **機能**: ユーザーの追加・編集・削除

#### 5.2 店舗管理
- **URL**: `/fi/admin/stores`
- **機能**: 店舗マスタの管理

#### 5.3 担当者管理
- **URL**: `/fi/admin/operators`
- **機能**: 工場担当者の管理

#### 5.4 出荷ログ管理
- **URL**: `/fi/admin/shipment-logs`
- **機能**: 出荷ログの確認・編集

---

## 技術スタック

### バックエンド
- **言語**: Python 3.9+ (推奨: Python 3.10+)
- **フレームワーク**: Flask 3.0+
- **ORM**: SQLAlchemy 2.0+
- **データベース**: MySQL 5.7+ / MariaDB 10.3+
- **WSGIサーバー**: Gunicorn 21.2+
- **マイグレーション**: Alembic 1.13+
- **WebSocket**: Flask-SocketIO (eventlet)

### フロントエンド
- **テンプレートエンジン**: Jinja2
- **CSSフレームワーク**: Bootstrap 5
- **JavaScript**: バニラJS（jQuery不使用）

### インフラ
- **Webサーバー**: Apache 2.4+ (mod_proxy) または Nginx 1.18+
- **プロセス管理**: systemd
- **ログ管理**: systemd journal + ファイルログ

### 開発ツール
- **バージョン管理**: Git
- **環境変数管理**: python-dotenv
- **仮想環境**: venv

---

## ディレクトリ構成

```
/var/www/html/factory-intake-shipping/
├── venv/                          # Python仮想環境
├── run.py                         # エントリポイント
├── config.py                      # 設定ファイル
├── .env                           # 環境変数（本番環境用）
├── .env.example                   # 環境変数テンプレート
├── requirements.txt               # Python依存パッケージ
├── setup_venv.sh                  # venvセットアップスクリプト
├── deploy.sh                      # デプロイスクリプト
│
├── factory_shipping/              # アプリケーション本体
│   ├── __init__.py                # アプリケーションファクトリ
│   ├── extensions.py              # Flask拡張機能（DB, Login等）
│   ├── models.py                  # データモデル
│   ├── views.py                   # メインビュー
│   ├── utils.py                   # ユーティリティ関数
│   │
│   ├── intake/                    # 入荷機能
│   │   ├── __init__.py
│   │   ├── views.py               # 入荷関連ビュー
│   │   └── services.py            # CSV取り込み処理
│   │
│   ├── shipping/                  # 出荷機能
│   │   ├── __init__.py
│   │   ├── views.py               # 出荷関連ビュー
│   │   └── utils.py               # バーコード解析等
│   │
│   ├── status/                    # ステータス確認
│   │   ├── __init__.py
│   │   └── views.py
│   │
│   ├── auth/                      # 認証機能
│   │   ├── __init__.py
│   │   └── views.py
│   │
│   ├── monitoring/                # モニタリング
│   │   ├── __init__.py
│   │   └── views.py
│   │
│   └── admin/                     # 管理者機能
│       ├── __init__.py
│       ├── views.py
│       └── decorators.py          # 管理者権限チェック
│
├── templates/                     # Jinja2テンプレート
│   ├── base.html                  # ベーステンプレート
│   ├── index.html                 # トップページ
│   ├── auth/                      # 認証関連
│   ├── intake/                    # 入荷関連
│   ├── shipping/                  # 出荷関連
│   ├── status/                    # ステータス関連
│   ├── monitoring/                # モニタリング
│   ├── admin/                     # 管理者画面
│   └── errors/                    # エラーページ
│
├── static/                        # 静的ファイル
│   ├── css/                       # スタイルシート
│   └── js/                        # JavaScript
│
├── migrations/                    # Alembicマイグレーション
│
├── deployment/                    # デプロイ設定
│   ├── factory-shipping.service   # systemdサービス定義
│   ├── gunicorn_config.py         # Gunicorn設定
│   ├── apache-vhost.conf          # Apache設定例
│   ├── nginx-site.conf            # Nginx設定例
│   └── factory-shipping.cron      # cron設定
│
├── scripts/                       # 運用スクリプト
│   ├── auto_import_hanjow.sh      # 自動取り込みスクリプト
│   └── bulk_import_hanjow.sh      # 一括取り込みスクリプト
│
├── uploads/                       # アップロードファイル（自動生成）
│
├── docs/                          # ドキュメント
│   ├── PROJECT_MANUAL.md          # このファイル
│   ├── DEPLOYMENT.md              # デプロイガイド
│   ├── INTAKE_SHIPPING_GUIDE.md  # 運用ガイド
│   ├── AUTO_IMPORT.md             # 自動取り込み詳細
│   └── INTAKE_LIST_SPEC.md        # 入荷一覧仕様
│
└── gunicorn.sock                  # Unixソケット（自動生成）
```

---

## セットアップ手順

### 前提条件
- Python 3.9+ がインストール済み
- MySQL/MariaDB がインストール済み
- Apache または Nginx がインストール済み
- sudo権限

### 1. 仮想環境のセットアップ

```bash
cd /var/www/html/factory-intake-shipping
bash setup_venv.sh python3.10
```

### 2. 環境変数の設定

```bash
cp .env.example .env
vi .env
```

**必須設定項目**:
```bash
FLASK_ENV=production
SECRET_KEY=[ランダムな64文字の文字列]
DATABASE_URL=mysql+pymysql://[ユーザー名]:[パスワード]@[ホスト]:[ポート]/[DB名]?charset=utf8mb4
```

**SECRET_KEY生成方法**:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. データベースの準備

```bash
# MySQLにログイン
mysql -u root -p

# データベースとユーザーを作成
CREATE DATABASE factory_shipping CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'factory_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON factory_shipping.* TO 'factory_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# テーブルを作成
source venv/bin/activate
python run.py init-db

# サンプルデータ投入（オプション）
python run.py seed-db
```

### 4. systemdサービスの登録

```bash
sudo cp deployment/factory-shipping.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable factory-shipping
sudo systemctl start factory-shipping
```

### 5. Webサーバーの設定

**Apacheの場合**:
```bash
sudo cp deployment/apache-vhost.conf /etc/httpd/conf.d/factory-shipping.conf
sudo vi /etc/httpd/conf.d/factory-shipping.conf
sudo systemctl restart httpd
```

**Nginxの場合**:
```bash
sudo cp deployment/nginx-site.conf /etc/nginx/conf.d/factory-shipping.conf
sudo vi /etc/nginx/conf.d/factory-shipping.conf
sudo systemctl restart nginx
```

### 6. cron設定（自動取り込み）

```bash
sudo cp deployment/factory-shipping.cron /etc/cron.d/factory-shipping
sudo chmod 644 /etc/cron.d/factory-shipping
```

詳細は [README.md](../README.md) の「セットアップ手順」セクションを参照してください。

---

## 運用方法

### 日常運用

#### 1. CSV自動取り込み
- **実行時刻**: 毎日22:35（自動）
- **ログ確認**: `/var/log/factory-shipping/auto-import.log`

#### 2. 手動取り込み（必要時）
- **Web UI**: https://factory.kingdrysystem.com/fi/intake/upload
- **コマンドライン**: `python run.py import-hanjow --date YYYY-MM-DD`

#### 3. 出荷処理
- 入荷一覧画面（`/fi/intake/list`）でバーコードスキャン
- HIDバーコードリーダーで9桁バーコードを読み取り

### 定期メンテナンス

#### データベースバックアップ
```bash
mysqldump -u factory_user -p factory_shipping > backup_$(date +%Y%m%d_%H%M%S).sql
```

#### ログローテーション
- ログは自動的にローテーションされます（logrotate設定）

#### コード更新
```bash
cd /var/www/html/factory-intake-shipping
./deploy.sh
```

### 運用コマンド

```bash
# サービスの起動・停止・再起動
sudo systemctl start factory-shipping
sudo systemctl stop factory-shipping
sudo systemctl restart factory-shipping

# ステータス確認
sudo systemctl status factory-shipping

# ログ確認
sudo journalctl -u factory-shipping -f
tail -f /var/log/factory-shipping/auto-import.log
```

詳細は [docs/INTAKE_SHIPPING_GUIDE.md](INTAKE_SHIPPING_GUIDE.md) を参照してください。

---

## データフロー

### CSV取り込みフロー

```
1. king-reqシステムがCSVを生成 (22:30)
   ↓
2. CSVファイル保存
   /var/www/html/king-req/downloads_hanjow/hanjow_YYYYMMDD.csv
   ↓
3. 自動取り込みスクリプト実行 (22:35)
   scripts/auto_import_hanjow.sh
   ↓
4. CSV読み込み・パース
   factory_shipping/intake/services.py
   ↓
5. 重複チェック
   (store_code + intake_date + tag_number + slip_number)
   ↓
6. データベースに保存
   intake_items テーブル
```

### 出荷処理フロー

```
1. バーコードスキャン
   9桁バーコード: 024642123
   ↓
2. バーコード解析
   店舗コード: 024
   タグ番号: 4-212
   ↓
3. データ検索
   IntakeItem テーブルから該当データを検索
   ↓
4. 出荷処理（トランザクション）
   - IntakeItem.status_id を更新
   - IntakeItem.shipped_at を設定
   - ShipmentLog に記録
   ↓
5. 結果表示
   成功/エラーメッセージを表示
```

---

## API・エンドポイント

### 認証関連
- `GET /fi/auth/login` - ログイン画面
- `POST /fi/auth/login` - ログイン処理
- `GET /fi/auth/logout` - ログアウト

### 入荷関連
- `GET /fi/intake/list` - 入荷データ一覧
- `GET /fi/intake/upload` - CSVアップロード画面
- `POST /fi/intake/upload` - CSVアップロード処理
- `POST /fi/intake/import-by-date` - 日付指定取り込み
- `GET /fi/intake/import-status` - 取り込みステータス
- `POST /fi/intake/fetch-csv/<date_str>` - CSVダウンロード・取り込み

### 出荷関連
- `GET /fi/shipping/scan` - 出荷スキャン画面
- `POST /fi/shipping/scan` - バーコードスキャン処理
- `GET /fi/shipping/history` - 出荷履歴

### ステータス関連
- `GET /fi/status/unshipped` - 未出荷一覧
- `GET /fi/status/delayed` - 遅れ品一覧

### モニタリング
- `GET /fi/monitoring/` - モニタリング一覧
- `GET /fi/monitoring/log/<log_id>` - ログ閲覧

### 管理者機能
- `GET /fi/admin/users` - ユーザー管理
- `GET /fi/admin/stores` - 店舗管理
- `GET /fi/admin/operators` - 担当者管理
- `GET /fi/admin/shipment-logs` - 出荷ログ管理

---

## データベーススキーマ

### 主要テーブル

#### users
ユーザー情報

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| username | VARCHAR(64) | ユーザー名 |
| email | VARCHAR(120) | メールアドレス（NULL可） |
| password_hash | VARCHAR(255) | パスワードハッシュ |
| is_active | BOOLEAN | 有効/無効 |
| is_admin | BOOLEAN | 管理者フラグ |
| is_store_staff | BOOLEAN | 店舗スタッフフラグ |
| is_factory_staff | BOOLEAN | 工場スタッフフラグ |
| is_shift_staff | BOOLEAN | シフトスタッフフラグ |
| is_office_staff | BOOLEAN | オフィススタッフフラグ |
| created_at | DATETIME | 作成日時 |
| updated_at | DATETIME | 更新日時 |

#### stores
店舗マスタ

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| store_code | VARCHAR(10) | 店舗コード |
| store_name | VARCHAR(100) | 店舗名 |
| is_active | BOOLEAN | 有効/無効 |

#### intake_items
入荷データ（商品テーブル）

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| store_id | INTEGER | 店舗ID（FK） |
| store_code | VARCHAR(10) | 店舗コード |
| store_name | VARCHAR(100) | 店舗名 |
| tag_number | VARCHAR(20) | タグ番号 |
| slip_number | VARCHAR(20) | 伝票番号 |
| product_name | VARCHAR(200) | 商品名 |
| customer_name | VARCHAR(100) | 顧客名 |
| amount | INTEGER | 金額 |
| intake_date | DATE | 預かり日 |
| scheduled_date | DATE | 出荷予定日 |
| status_id | INTEGER | 状態ID（FK） |
| intake_status | VARCHAR(20) | 入荷状態 |
| imported_at | DATETIME | CSV取り込み日時 |
| shipped_at | DATETIME | 出荷日時 |

#### shipment_logs
出荷ログ（状態変更履歴）

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| intake_item_id | INTEGER | 入荷データID（FK） |
| store_id | INTEGER | 店舗ID（FK） |
| store_code | VARCHAR(20) | 店舗コード |
| tag_number | VARCHAR(20) | タグ番号 |
| scanned_by_user_id | INTEGER | スキャン実行ユーザー（FK） |
| operator_id | INTEGER | 担当者ID（FK） |
| scanned_at | DATETIME | スキャン日時 |
| scanned_code | VARCHAR(100) | バーコード |
| new_status_id | INTEGER | 変更後の状態ID（FK） |

#### item_statuses
商品状態マスタ

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| status_code | VARCHAR(50) | 状態コード |
| status_name | VARCHAR(100) | 状態名 |
| display_order | INTEGER | 表示順序 |
| is_active | BOOLEAN | 有効/無効 |

#### factory_operators
工場担当者マスタ

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| operator_code | VARCHAR(20) | 担当者コード |
| operator_name | VARCHAR(100) | 担当者名 |
| is_active | BOOLEAN | 有効/無効 |
| created_at | DATETIME | 作成日時 |
| updated_at | DATETIME | 更新日時 |

#### journal_data
ジャーナルデータ

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| date | DATE | 日付 |
| store_no | VARCHAR(10) | 店舗番号 |
| slip_no | VARCHAR(20) | 伝票番号 |
| customer_name | VARCHAR(100) | 顧客名 |
| phone | VARCHAR(20) | 電話番号 |
| slip_content | TEXT | 伝票内容 |
| imported_at | DATETIME | インポート日時 |
| created_at | DATETIME | 作成日時 |
| updated_at | DATETIME | 更新日時 |

詳細は [factory_shipping/models.py](../factory_shipping/models.py) を参照してください。

---

## トラブルシューティング

### よくある問題と解決方法

#### 1. サービスが起動しない

**症状**: `systemctl status factory-shipping` でエラー

**確認項目**:
```bash
# ログを確認
sudo journalctl -u factory-shipping -n 50

# 手動で起動してエラーを確認
cd /var/www/html/factory-intake-shipping
source venv/bin/activate
gunicorn -c deployment/gunicorn_config.py 'factory_shipping:create_app()'
```

**よくある原因**:
- `.env` ファイルの設定ミス
- データベース接続エラー
- 仮想環境が正しくセットアップされていない

#### 2. 502 Bad Gateway エラー

**症状**: ブラウザでアクセスすると502エラー

**確認項目**:
```bash
# Gunicornのステータス確認
sudo systemctl status factory-shipping

# Unixソケットの確認
ls -l /var/www/html/factory-intake-shipping/gunicorn.sock

# SELinuxの確認（CentOS/RHEL）
sudo ausearch -m avc -ts recent
```

**解決方法**:
```bash
# サービスを再起動
sudo systemctl restart factory-shipping

# SELinux設定（必要な場合）
sudo setsebool -P httpd_can_network_connect 1
```

#### 3. CSV取り込みが失敗する

**症状**: `import-hanjow` コマンドがエラーで終了

**確認項目**:
```bash
# CSVファイルの存在確認
ls -l /var/www/html/king-req/downloads_hanjow/hanjow_*.csv

# ファイルの読み取り権限
cat /var/www/html/king-req/downloads_hanjow/hanjow_20251111.csv | head

# ログの確認
tail -f /var/log/factory-shipping/auto-import.log
```

#### 4. バーコードスキャンが反応しない

**症状**: バーコードを読み取っても何も起こらない

**確認項目**:
- バーコードリーダーがHIDモードになっているか
- 入力欄にフォーカスがあるか
- ブラウザのJavaScriptが有効か（F12開発者ツールでエラー確認）

#### 5. データベース接続エラー

**症状**: データベースに接続できない

**確認項目**:
```bash
# .envのDATABASE_URLを確認
cat .env | grep DATABASE_URL

# MySQLに直接接続してテスト
mysql -u factory_user -p -h localhost factory_shipping
```

詳細は [README.md](../README.md) の「トラブルシューティング」セクションを参照してください。

---

## 関連ドキュメント

### 主要ドキュメント
- [README.md](../README.md) - プロジェクト概要・セットアップ手順
- [docs/DEPLOYMENT.md](DEPLOYMENT.md) - デプロイメントガイド
- [docs/INTAKE_SHIPPING_GUIDE.md](INTAKE_SHIPPING_GUIDE.md) - 運用ガイド
- [docs/AUTO_IMPORT.md](AUTO_IMPORT.md) - 自動取り込み機能詳細
- [IMPLEMENTATION_SUMMARY.md](../IMPLEMENTATION_SUMMARY.md) - 実装サマリー

### コードドキュメント
- [factory_shipping/models.py](../factory_shipping/models.py) - データモデル定義
- [factory_shipping/intake/services.py](../factory_shipping/intake/services.py) - CSV取り込み処理
- [factory_shipping/shipping/utils.py](../factory_shipping/shipping/utils.py) - バーコード解析

### 設定ファイル
- [config.py](../config.py) - アプリケーション設定
- [deployment/gunicorn_config.py](../deployment/gunicorn_config.py) - Gunicorn設定
- [deployment/factory-shipping.service](../deployment/factory-shipping.service) - systemdサービス定義

---

## 更新履歴

- **2025-12-30**: ドキュメント全体を整理し、ソースコードと一致させる
  - ユーザーモデルのroleフラグを追加（is_store_staff, is_factory_staff, is_shift_staff, is_office_staff）
  - JournalDataモデルとimport-journalコマンドの記載を追加
  - Flask-SocketIOの記載を追加
  - 重複チェックロジックの正確な記載（slip_numberを含む）
- **2025-12-14**: プロジェクトマニュアル作成、CSVダウンロード機能追加
- **2025-11-29**: 自動取り込み機能実装

---

## お問い合わせ

システムに関する質問や問題が発生した場合は、システム管理者までお問い合わせください。

---

**最終更新**: 2025-12-30
**バージョン**: 1.0.0








