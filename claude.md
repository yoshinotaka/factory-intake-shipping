# 新・出荷システム - Claude作業メモ

## プロジェクト概要

**プロジェクト名**: 新・出荷システム (Factory Intake & Shipping System)
**パス**: `/var/www/html/factory-intake-shipping`
**フレームワーク**: Flask + SQLAlchemy
**データベース**: MySQL (factory_shipping)
**Webサーバー**: Apache + Gunicorn (Unix socket)

---

## 現在の状況 (2025-11-29 16:00時点)

### システムステータス

- **サービス状態**: ✅ 正常稼働中 (factory-shipping.service)
- **起動時刻**: 2025-11-29 13:00:38 JST
- **稼働時間**: 約3時間
- **Gunicornワーカー**: 4プロセス稼働中
- **Unixソケット**: `/var/www/html/factory-intake-shipping/gunicorn.sock` (パーミッション 666)

### データベース統計

```
データベース: factory_shipping
テーブル数: 5個
- users (ユーザー管理)
- stores (店舗マスタ)
- intake_items (入荷商品)
- shipment_logs (出荷ログ)
- delayed_items (遅れ品管理)

入荷商品データ:
- 総登録数: 415件
- 出荷済み: 10件
- 未出荷: 405件
```

### 環境設定

```bash
環境: development (開発モード)
デバッグ: True
タイムゾーン: Asia/Tokyo
ログレベル: INFO
最大アップロードサイズ: 16MB
許可ファイル形式: csv, xlsx, xls
```

---

## プロジェクト構成

### ディレクトリ構造

```
/var/www/html/factory-intake-shipping/
├── venv/                          # Python仮想環境
├── factory_shipping/              # アプリケーション本体
│   ├── __init__.py               # Flaskアプリファクトリ
│   ├── extensions.py             # Flask拡張 (db, login_manager等)
│   ├── models.py                 # データモデル
│   ├── views.py                  # メインビュー
│   ├── intake/                   # 入荷機能モジュール
│   │   ├── __init__.py
│   │   ├── views.py
│   │   └── services.py
│   ├── shipping/                 # 出荷機能モジュール
│   │   ├── __init__.py
│   │   ├── views.py
│   │   └── utils.py
│   ├── status/                   # ステータス確認モジュール
│   │   ├── __init__.py
│   │   └── views.py
│   └── auth/                     # 認証モジュール
│       ├── __init__.py
│       └── views.py
├── templates/                    # Jinja2テンプレート
├── static/                       # 静的ファイル (CSS, JS)
├── uploads/                      # アップロードファイル保存先
├── deployment/                   # デプロイ設定
│   ├── factory-shipping.service  # systemdサービス定義
│   ├── gunicorn_config.py
│   ├── apache-vhost.conf
│   └── nginx-site.conf
├── run.py                        # エントリポイント
├── config.py                     # 設定ファイル
├── .env                          # 環境変数
└── requirements.txt              # Python依存パッケージ
```

### 主要機能

1. **入荷管理** (`/fi/intake/`)
   - CSV一括取り込み機能
   - hanjow CSVファイル自動取り込み (cron対応)
   - 入荷データ一覧表示

2. **出荷管理** (`/fi/shipping/`)
   - バーコードスキャン出荷登録
   - 出荷履歴管理

3. **ステータス確認** (`/fi/status/`)
   - 未出荷一覧
   - 遅れ品管理 (scheduled_date超過)
   - 店舗別集計

4. **認証** (`/fi/auth/`)
   - ログイン/ログアウト
   - ユーザー管理

---

## 技術スタック

### バックエンド

- **Python**: 3.10+ (venv)
- **Flask**: Webフレームワーク
- **SQLAlchemy**: ORM
- **Flask-Login**: 認証管理
- **PyMySQL**: MySQLドライバ
- **Gunicorn**: WSGIサーバー

### フロントエンド

- **Jinja2**: テンプレートエンジン
- **Bootstrap**: CSSフレームワーク (推測)
- **JavaScript**: バーコードスキャナー連携

### インフラ

- **OS**: Amazon Linux 2023
- **Webサーバー**: Apache 2.4 (mod_proxy)
- **DB**: MySQL (localhost:3306)
- **プロセス管理**: systemd

---

## 運用情報

### サービス管理コマンド

```bash
# サービス起動/停止/再起動
sudo systemctl start factory-shipping
sudo systemctl stop factory-shipping
sudo systemctl restart factory-shipping

# ステータス確認
sudo systemctl status factory-shipping

# ログ確認
sudo journalctl -u factory-shipping -f
tail -f /var/log/factory-shipping/access.log
tail -f /var/log/factory-shipping/error.log
```

### データベース操作

```bash
# venv有効化
source venv/bin/activate

# テーブル作成
python run.py init-db

# サンプルデータ投入
python run.py seed-db

# hanjow CSV取り込み (今日の日付)
python run.py import-hanjow

# hanjow CSV取り込み (日付指定)
python run.py import-hanjow --date 2025-11-29
```

### cron設定 (hanjow自動取り込み)

```bash
# 毎日22:30に前日分のCSVを自動取り込み
30 22 * * * cd /var/www/html/factory-intake-shipping && /var/www/html/factory-intake-shipping/venv/bin/python run.py import-hanjow >> /var/log/factory-shipping/import-hanjow.log 2>&1
```

---

## 認証情報

### デフォルトユーザー

```
管理者:
  ユーザー名: admin
  パスワード: admin123
  権限: 管理者

テストユーザー:
  ユーザー名: testuser
  パスワード: test123
  権限: 一般ユーザー
```

**重要**: 本番環境では必ずパスワードを変更してください

---

## データモデル

### 主要テーブル

#### users (ユーザー)
- id (PK)
- username (ユニーク)
- email
- password_hash
- is_admin (管理者フラグ)
- created_at, updated_at

#### stores (店舗マスタ)
- id (PK)
- store_code (ユニーク)
- store_name
- is_active
- created_at, updated_at

#### intake_items (入荷商品)
- id (PK)
- store_id (FK → stores)
- store_code
- store_name
- tag_number (伝票番号、ユニーク制約)
- product_name
- customer_name
- amount (金額)
- intake_date (入荷日)
- scheduled_date (出荷予定日)
- is_shipped (出荷済みフラグ)
- shipped_at (出荷日時)
- item_code, item_name, quantity
- notes
- created_at, updated_at

#### shipment_logs (出荷ログ)
- id (PK)
- intake_item_id (FK → intake_items)
- shipped_by (出荷担当者)
- shipped_at
- notes

#### delayed_items (遅れ品)
- id (PK)
- intake_item_id (FK → intake_items)
- days_delayed (遅延日数)
- checked_at (確認日時)

---

## 外部連携

### hanjow CSVファイル連携（自動取り込み）

**CSVファイル配置場所**:
`/var/www/html/king-req/downloads_hanjow/hanjow_YYYYMMDD.csv`

**ファイル命名規則**:
`hanjow_20251129.csv` (YYYYMMDD形式)

**自動取り込み設定**:
- **実行時刻**: 毎日 22:35（CSVは22:30配置想定）
- **cron設定**: ユーザーcrontab (`crontab -l` で確認)
- **cron内容**: `35 22 * * * /var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh >> /var/log/factory-shipping/auto-import.log 2>&1`
- **ログ**: `/var/log/factory-shipping/auto-import.log`

**取り込み処理**:
- 自動実行: cron経由で `scripts/auto_import_hanjow.sh` を実行
- 手動実行: `scripts/auto_import_hanjow.sh YYYY-MM-DD`
- 一括取り込み: `scripts/bulk_import_hanjow.sh START_DATE END_DATE`

**重複チェックロジック**:
- 店舗コード (`store_code`) + 預かり日 (`intake_date`) + タグ番号 (`tag_number`)
- 重複データは自動スキップ
- 遡って取得したデータでも安全に差分のみ取り込み

**取り込み日時記録**:
- `imported_at` カラムにCSV取り込み日時を記録
- 監査・トラブルシューティングに活用

---

## 今後の拡張予定

### 共通ライブラリ化の検討

将来的に旧システム (king-req) との統合を見据えた設計:

```
/var/www/html/factory-systems/
├── common/                    # 共通ライブラリ
│   ├── models.py             # 共通データモデル
│   ├── extensions.py         # 共通Flask拡張
│   └── utils.py
├── intake-shipping/          # 新・出荷システム
├── king-req/                 # 旧システム
└── shared-config/            # 共通設定
```

### API化構想

- REST API提供 (`/api/v1/intake`, `/api/v1/shipping`)
- 他システムからの呼び出し対応
- トークン認証導入

---

## トラブルシューティング

### よくある問題

#### 1. サービスが起動しない

```bash
# ログ確認
sudo journalctl -u factory-shipping -n 50

# ソケットファイル確認
ls -l /var/www/html/factory-intake-shipping/gunicorn.sock

# パーミッション修正
sudo chown ec2-user:ec2-user /var/www/html/factory-intake-shipping
chmod 755 /var/www/html/factory-intake-shipping
```

#### 2. 502 Bad Gateway

```bash
# Gunicornが起動しているか確認
sudo systemctl status factory-shipping

# Apacheのエラーログ確認
sudo tail -f /var/log/httpd/error_log

# SELinux設定
sudo setsebool -P httpd_can_network_connect 1
```

#### 3. データベース接続エラー

```bash
# .env の DATABASE_URL確認
cat .env | grep DATABASE_URL

# MySQL接続テスト
mysql -u factory_user -pfactory_password -e "USE factory_shipping; SHOW TABLES;"
```

---

## 開発メモ

### 現在の課題

なし (システム正常稼働中)

### 次のタスク

- [ ] 本番環境への切り替え (FLASK_ENV=production)
- [ ] SECRET_KEY 変更 (本番用)
- [ ] デフォルトパスワード変更
- [ ] バックアップ運用確立
- [x] cron設定を本番環境に適用（ユーザーcrontabに設定済み）

### 変更履歴

- 2025-11-29 16:00: 初期構築完了、サービス起動確認
- 2025-11-29 16:00: データベーステーブル作成、サンプルデータ投入
- 2025-11-29 16:00: hanjow CSV取り込み機能実装
- 2025-11-29 16:30: **自動取り込み機能実装完了**
  - `imported_at` カラム追加（取り込み日時記録）
  - 重複チェックロジック実装（差分のみ取り込み）
  - 自動取り込みスクリプト作成 (`scripts/auto_import_hanjow.sh`)
  - 一括取り込みスクリプト作成 (`scripts/bulk_import_hanjow.sh`)
  - ユーザーcrontabに自動取り込み設定（毎日22:35実行）
  - ドキュメント整備 (`docs/AUTO_IMPORT.md`)

---

## 参考リンク

- アプリケーションURL: `http://localhost/fi/` (Apache経由)
- 開発サーバーURL: `http://localhost:5000/fi/` (直接起動時)
- ログディレクトリ: `/var/log/factory-shipping/`
- アップロードディレクトリ: `/var/www/html/factory-intake-shipping/uploads/`

---

**最終更新**: 2025-11-29 16:00 JST
**作成者**: Claude
**バージョン**: 1.0.0
