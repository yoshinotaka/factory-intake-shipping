# 新・出荷システム

工場入荷・出荷管理システム

## 📋 目次

- [概要](#概要)
- [システム要件](#システム要件)
- [ディレクトリ構成](#ディレクトリ構成)
- [セットアップ手順](#セットアップ手順)
- [開発環境での実行](#開発環境での実行)
- [本番環境へのデプロイ](#本番環境へのデプロイ)
- [将来の拡張性について](#将来の拡張性について)

---

## 概要

新・出荷システムは、工場での入荷・出荷管理を効率化するための Web アプリケーションです。

主な機能:
- **入荷管理**: CSV ファイルからの入荷データ取り込み
- **出荷スキャン**: バーコードスキャンによる出荷登録
- **未出荷一覧**: 未出荷商品の確認
- **遅れ品管理**: 予定日を過ぎた商品の管理

---

## システム要件

### OS
- Amazon Linux 2023 / CentOS 7+ / RHEL 7+
- Ubuntu 20.04+ / Debian 10+

### Python
- Python 3.9 以上（推奨: Python 3.10+）

### データベース
- MySQL 5.7+ / MariaDB 10.3+
- PostgreSQL 12+ (オプション)

### Web サーバー
- Apache 2.4+ (mod_proxy 有効)
- または Nginx 1.18+

---

## ディレクトリ構成

```
/var/www/html/factory-intake-shipping/
├── venv/                          # 仮想環境（セットアップ後に作成）
├── run.py                         # エントリポイント
├── config.py                      # 設定ファイル
├── .env                           # 環境変数（.env.example からコピー）
├── .env.example                   # 環境変数テンプレート
├── requirements.txt               # Python パッケージ依存関係
├── setup_venv.sh                  # venv セットアップスクリプト
│
├── factory_shipping/              # アプリケーション本体
│   ├── __init__.py                # アプリケーションファクトリ
│   ├── extensions.py              # Flask 拡張機能
│   ├── models.py                  # データモデル
│   ├── views.py                   # メインビュー
│   ├── intake/                    # 入荷機能
│   ├── shipping/                  # 出荷機能
│   ├── status/                    # ステータス確認
│   └── auth/                      # 認証機能
│
├── templates/                     # Jinja2 テンプレート
│   ├── base.html
│   ├── index.html
│   ├── auth/
│   ├── intake/
│   ├── shipping/
│   ├── status/
│   └── errors/
│
├── static/                        # 静的ファイル
│   ├── css/
│   └── js/
│
├── migrations/                    # Alembic マイグレーション
│
├── deployment/                    # デプロイ設定
│   ├── factory-shipping.service   # systemd サービス
│   ├── gunicorn_config.py         # Gunicorn 設定
│   ├── apache-vhost.conf          # Apache 設定例
│   └── nginx-site.conf            # Nginx 設定例
│
├── uploads/                       # アップロードファイル（自動生成）
└── docs/                          # ドキュメント
```

---

## セットアップ手順

### 1. 仮想環境のセットアップ

```bash
cd /var/www/html/factory-intake-shipping

# Python バージョンを指定して実行（例: python3.10）
bash setup_venv.sh python3.10

# または、デフォルトの python3 を使用
bash setup_venv.sh
```

### 2. 環境変数の設定

```bash
# .env.example をコピーして .env を作成
cp .env.example .env

# .env ファイルを編集
vi .env
```

最低限設定が必要な項目:
```bash
# 本番環境では必ず変更してください
SECRET_KEY=your-secret-key-here-change-in-production

# データベース接続情報
DATABASE_URL=mysql+pymysql://[ユーザー名]:[パスワード]@[ホスト]:[ポート]/[DB名]?charset=utf8mb4
```

SECRET_KEY の生成方法:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. データベースの準備

```bash
# MySQL にログイン
mysql -u root -p

# データベースとユーザーを作成
CREATE DATABASE factory_shipping CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'factory_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON factory_shipping.* TO 'factory_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 4. データベーステーブルの作成

```bash
# venv を有効化
source venv/bin/activate

# テーブルを作成
python run.py init-db

# サンプルデータを投入（オプション）
python run.py seed-db
```

### 5. Alembic の初期化（マイグレーション管理）

```bash
# Alembic を初期化
alembic init migrations

# alembic.ini を編集（DATABASE_URL を設定）
vi alembic.ini

# 初期マイグレーションを作成
alembic revision --autogenerate -m "Initial migration"

# マイグレーションを適用
alembic upgrade head
```

---

## 開発環境での実行

### 開発サーバーの起動

```bash
# venv を有効化
source venv/bin/activate

# 開発サーバーを起動
python run.py

# または Flask コマンドで起動
flask run --host=0.0.0.0 --port=5000
```

アクセス: http://localhost:5000/fi/

デフォルトログイン情報:
- ユーザー名: `admin`
- パスワード: `admin123`

---

## 本番環境へのデプロイ

### GitHubリポジトリ

このプロジェクトはGitHubで管理されています：
https://github.com/yoshinotaka/factory-intake-shipping

### デプロイ方法

#### 初回デプロイ

### 1. ログディレクトリの作成

```bash
sudo mkdir -p /var/log/factory-shipping
sudo chown ec2-user:ec2-user /var/log/factory-shipping
```

### 2. systemd サービスの登録

```bash
# サービスファイルをコピー
sudo cp deployment/factory-shipping.service /etc/systemd/system/

# サービスファイルを編集（必要に応じて User, Group などを変更）
sudo vi /etc/systemd/system/factory-shipping.service

# systemd をリロード
sudo systemctl daemon-reload

# サービスを有効化・起動
sudo systemctl enable factory-shipping
sudo systemctl start factory-shipping

# ステータス確認
sudo systemctl status factory-shipping
```

### 3. Apache の設定（Apache を使用する場合）

```bash
# 設定ファイルをコピー
sudo cp deployment/apache-vhost.conf /etc/httpd/conf.d/factory-shipping.conf

# 設定を編集
sudo vi /etc/httpd/conf.d/factory-shipping.conf

# 設定をテスト
sudo httpd -t

# Apache を再起動
sudo systemctl restart httpd
```

### 4. Nginx の設定（Nginx を使用する場合）

```bash
# 設定ファイルをコピー
sudo cp deployment/nginx-site.conf /etc/nginx/conf.d/factory-shipping.conf

# 設定を編集
sudo vi /etc/nginx/conf.d/factory-shipping.conf

# 設定をテスト
sudo nginx -t

# Nginx を再起動
sudo systemctl restart nginx
```

### 5. ファイアウォールの設定

```bash
# HTTP/HTTPS を許可
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 6. SELinux の設定（必要な場合）

```bash
# Unix ソケットへのアクセスを許可
sudo setsebool -P httpd_can_network_connect 1

# または SELinux を一時的に無効化（開発環境のみ）
sudo setenforce 0
```

---

### コード更新時のデプロイ

コードを変更した後は、以下のデプロイスクリプトを実行してください：

```bash
cd /var/www/html/factory-intake-shipping
./deploy.sh
```

このスクリプトは以下を自動的に実行します：
1. GitHubから最新のコードを取得（`git pull`）
2. 依存関係の更新（requirements.txtが変更された場合）
3. factory-shippingサービスの再起動
4. サービスの状態確認
5. エラーログの表示

**重要**: コード変更後は必ずこのスクリプトを実行してください。実行しないと、古いコードが動作し続けます。

#### 手動でのデプロイ

スクリプトを使わない場合は、以下のコマンドを順番に実行してください：

```bash
cd /var/www/html/factory-intake-shipping
git pull origin main
sudo systemctl restart factory-shipping
sudo systemctl status factory-shipping
```

---

## 運用コマンド

### サービスの管理

```bash
# サービスの起動
sudo systemctl start factory-shipping

# サービスの停止
sudo systemctl stop factory-shipping

# サービスの再起動
sudo systemctl restart factory-shipping

# サービスのステータス確認
sudo systemctl status factory-shipping

# ログの確認
sudo journalctl -u factory-shipping -f
```

### データベースのバックアップ

```bash
# バックアップ
mysqldump -u factory_user -p factory_shipping > backup_$(date +%Y%m%d_%H%M%S).sql

# リストア
mysql -u factory_user -p factory_shipping < backup_20250129_120000.sql
```

### hanjow CSV 自動取り込み

**自動取り込みの設定**:
```bash
# cron設定ファイルをインストール（推奨）
sudo cp deployment/factory-shipping.cron /etc/cron.d/factory-shipping
sudo chmod 644 /etc/cron.d/factory-shipping
sudo chown root:root /etc/cron.d/factory-shipping
```

**手動実行**:
```bash
# 特定日付のCSVを取り込み
scripts/auto_import_hanjow.sh 2025-11-29

# 複数日分を一括取り込み
scripts/bulk_import_hanjow.sh 2025-11-01 2025-11-29
```

**ログ確認**:
```bash
tail -f /var/log/factory-shipping/auto-import.log
```

詳細は [docs/AUTO_IMPORT.md](docs/AUTO_IMPORT.md) を参照してください。

---

## 将来の拡張性について

このプロジェクトは、将来的に旧システムや他のシステムと統合しやすいように設計されています。

### 共通ライブラリ化の方針

1. **共通モジュールの切り出し**
   - `factory_shipping/models.py` を `common/models.py` に移動
   - `factory_shipping/extensions.py` を `common/extensions.py` に移動

2. **モノレポ構成への移行**
   ```
   /var/www/html/factory-systems/
   ├── common/                    # 共通ライブラリ
   │   ├── models.py
   │   ├── extensions.py
   │   └── utils.py
   ├── intake-shipping/           # 新・出荷システム
   ├── king-req/                  # 旧システム
   └── shared-config/             # 共通設定
   ```

3. **共通データベースの利用**
   - 各システムが同じデータベースを参照
   - テーブルプレフィックスで分離（例: `is_users`, `kr_users`）

4. **API 化による連携**
   - REST API を提供し、他システムから呼び出し可能に
   - `/api/v1/intake`, `/api/v1/shipping` など

---

## トラブルシューティング

### よくあるエラー

**1. "No module named 'factory_shipping'"**
```bash
# venv を有効化していない
source venv/bin/activate
```

**2. "Access denied for user"**
```bash
# .env の DATABASE_URL が正しいか確認
# データベースユーザーの権限を確認
```

**3. "502 Bad Gateway"**
```bash
# Gunicorn が起動しているか確認
sudo systemctl status factory-shipping

# Unix ソケットが作成されているか確認
ls -l gunicorn.sock
```

**4. "Permission denied"**
```bash
# ファイル所有者を確認
ls -l /var/www/html/factory-intake-shipping

# 所有者を変更
sudo chown -R ec2-user:ec2-user /var/www/html/factory-intake-shipping
```

---

## ライセンス

社内システムのため非公開

## お問い合わせ

システム管理者までお問い合わせください。
