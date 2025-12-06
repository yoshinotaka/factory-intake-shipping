# デプロイメントガイド

新・出荷システムを本番環境にデプロイする際の詳細手順

## 前提条件

- サーバーへの SSH アクセス
- sudo 権限
- Python 3.9+ がインストール済み
- MySQL/MariaDB がインストール済み
- Apache または Nginx がインストール済み

---

## 完全デプロイ手順（チェックリスト形式）

### □ ステップ 1: システムパッケージの準備

```bash
# システムを最新化
sudo yum update -y

# 必要なパッケージをインストール
sudo yum install -y python3 python3-pip python3-devel gcc mysql-devel

# Apache の場合
sudo yum install -y httpd httpd-devel mod_ssl

# Nginx の場合
sudo yum install -y nginx
```

### □ ステップ 2: プロジェクトの配置

```bash
# プロジェクトディレクトリに移動
cd /var/www/html/factory-intake-shipping

# 所有者を確認・変更
sudo chown -R ec2-user:ec2-user /var/www/html/factory-intake-shipping
```

### □ ステップ 3: 仮想環境のセットアップ

```bash
# セットアップスクリプトを実行
bash setup_venv.sh python3.10
```

### □ ステップ 4: 環境変数の設定

```bash
# .env ファイルを作成
cp .env.example .env

# .env を本番環境用に編集
vi .env
```

**重要な設定項目:**
```bash
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=[ランダムな64文字の文字列]
DATABASE_URL=mysql+pymysql://[本番DBユーザー]:[パスワード]@localhost:3306/factory_shipping?charset=utf8mb4
```

### □ ステップ 5: データベースのセットアップ

```bash
# MySQL にログイン
mysql -u root -p

# データベースとユーザーを作成
CREATE DATABASE factory_shipping CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'factory_user'@'localhost' IDENTIFIED BY '[強固なパスワード]';
GRANT ALL PRIVILEGES ON factory_shipping.* TO 'factory_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# テーブルを作成
source venv/bin/activate
python run.py init-db

# 初期データ投入（必要に応じて）
python run.py seed-db
```

### □ ステップ 6: ログディレクトリの準備

```bash
# ログディレクトリを作成
sudo mkdir -p /var/log/factory-shipping

# 所有者を設定
sudo chown ec2-user:ec2-user /var/log/factory-shipping

# ログローテーション設定
sudo tee /etc/logrotate.d/factory-shipping > /dev/null <<EOF
/var/log/factory-shipping/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 ec2-user ec2-user
    sharedscripts
    postrotate
        systemctl reload factory-shipping > /dev/null 2>&1 || true
    endscript
}
EOF
```

### □ ステップ 7: systemd サービスの登録

```bash
# サービスファイルを配置
sudo cp deployment/factory-shipping.service /etc/systemd/system/

# サービスファイルを編集（User, Group など）
sudo vi /etc/systemd/system/factory-shipping.service

# systemd をリロード
sudo systemctl daemon-reload

# サービスを有効化
sudo systemctl enable factory-shipping

# サービスを起動
sudo systemctl start factory-shipping

# ステータス確認
sudo systemctl status factory-shipping

# ログ確認
sudo journalctl -u factory-shipping -f
```

### □ ステップ 8: Web サーバーの設定

#### Apache の場合

```bash
# 設定ファイルをコピー
sudo cp deployment/apache-vhost.conf /etc/httpd/conf.d/factory-shipping.conf

# 設定を編集（ServerName など）
sudo vi /etc/httpd/conf.d/factory-shipping.conf

# 必要なモジュールを有効化
sudo yum install -y mod_proxy_html

# 設定テスト
sudo httpd -t

# Apache を再起動
sudo systemctl restart httpd

# Apache を自動起動に設定
sudo systemctl enable httpd
```

#### Nginx の場合

```bash
# 設定ファイルをコピー
sudo cp deployment/nginx-site.conf /etc/nginx/conf.d/factory-shipping.conf

# 設定を編集（server_name など）
sudo vi /etc/nginx/conf.d/factory-shipping.conf

# 設定テスト
sudo nginx -t

# Nginx を再起動
sudo systemctl restart nginx

# Nginx を自動起動に設定
sudo systemctl enable nginx
```

### □ ステップ 9: ファイアウォールの設定

```bash
# HTTP/HTTPS を許可
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload

# 設定確認
sudo firewall-cmd --list-all
```

### □ ステップ 10: SELinux の設定（CentOS/RHEL の場合）

```bash
# SELinux の状態確認
getenforce

# httpd がネットワーク接続できるように設定
sudo setsebool -P httpd_can_network_connect 1

# Unix ソケットへのアクセスを許可
sudo chcon -t httpd_sys_rw_content_t /var/www/html/factory-intake-shipping/gunicorn.sock
```

### □ ステップ 11: 動作確認

```bash
# Gunicorn が起動しているか
sudo systemctl status factory-shipping

# Unix ソケットが作成されているか
ls -l /var/www/html/factory-intake-shipping/gunicorn.sock

# Web サーバーが起動しているか
sudo systemctl status httpd  # または nginx

# ブラウザでアクセス
# http://your-server.com/fi/
```

### □ ステップ 12: SSL/TLS 証明書の設定（オプション）

```bash
# Let's Encrypt の certbot をインストール
sudo yum install -y certbot python3-certbot-apache

# 証明書を取得（Apache の場合）
sudo certbot --apache -d your-domain.com

# Nginx の場合
sudo yum install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 自動更新のテスト
sudo certbot renew --dry-run
```

---

## デプロイ後の確認事項

### 機能テスト

1. ログイン機能
   - [ ] ログインできる
   - [ ] ログアウトできる
   - [ ] パスワード変更ができる

2. 入荷機能
   - [ ] 入荷データ一覧が表示される
   - [ ] CSV アップロード画面が表示される

3. 出荷機能
   - [ ] 出荷スキャン画面が表示される
   - [ ] 出荷履歴が表示される

4. ステータス機能
   - [ ] 未出荷一覧が表示される
   - [ ] 遅れ品一覧が表示される

### パフォーマンステスト

```bash
# Apache Bench でテスト（例）
ab -n 1000 -c 10 http://your-server.com/fi/
```

### セキュリティチェック

- [ ] HTTPS が有効になっている
- [ ] SECRET_KEY が本番用の値になっている
- [ ] デバッグモードが無効になっている（FLASK_DEBUG=False）
- [ ] 不要なポートが閉じている
- [ ] ファイアウォールが設定されている

---

## 更新・メンテナンス

### アプリケーションの更新

```bash
# コードを更新（Git の場合）
cd /var/www/html/factory-intake-shipping
git pull origin main

# 依存パッケージを更新（必要な場合）
source venv/bin/activate
pip install -r requirements.txt

# データベースマイグレーション（必要な場合）
alembic upgrade head

# Gunicorn を再起動
sudo systemctl restart factory-shipping
```

### データベースバックアップ

```bash
# バックアップスクリプトを作成
sudo tee /usr/local/bin/backup-factory-shipping.sh > /dev/null <<'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/factory-shipping"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
mysqldump -u factory_user -p'[パスワード]' factory_shipping | gzip > $BACKUP_DIR/factory_shipping_$DATE.sql.gz
find $BACKUP_DIR -type f -mtime +30 -delete
EOF

# 実行権限を付与
sudo chmod +x /usr/local/bin/backup-factory-shipping.sh

# cron に登録（毎日 2:00 に実行）
sudo crontab -e
# 以下を追加
# 0 2 * * * /usr/local/bin/backup-factory-shipping.sh
```

---

## トラブルシューティング

### Gunicorn が起動しない

```bash
# ログを確認
sudo journalctl -u factory-shipping -n 50

# 手動で起動してエラーを確認
cd /var/www/html/factory-intake-shipping
source venv/bin/activate
gunicorn -c deployment/gunicorn_config.py 'factory_shipping:create_app()'
```

### 502 Bad Gateway エラー

```bash
# Gunicorn のステータス確認
sudo systemctl status factory-shipping

# Unix ソケットの確認
ls -l /var/www/html/factory-intake-shipping/gunicorn.sock

# SELinux の確認
sudo ausearch -m avc -ts recent
```

### データベース接続エラー

```bash
# .env の DATABASE_URL を確認
cat .env | grep DATABASE_URL

# MySQL に直接接続してテスト
mysql -u factory_user -p -h localhost factory_shipping
```

---

## ロールバック手順

問題が発生した場合のロールバック手順

```bash
# 1. サービスを停止
sudo systemctl stop factory-shipping

# 2. コードを以前のバージョンに戻す（Git の場合）
git checkout [前のコミットハッシュ]

# 3. データベースをリストア（必要な場合）
mysql -u factory_user -p factory_shipping < /var/backups/factory-shipping/backup.sql

# 4. サービスを再起動
sudo systemctl start factory-shipping

# 5. 動作確認
sudo systemctl status factory-shipping
```

---

## パフォーマンスチューニング

### Gunicorn ワーカー数の調整

```bash
# CPU コア数を確認
nproc

# 推奨ワーカー数: (コア数 × 2) + 1
# .env ファイルで設定
GUNICORN_WORKERS=9
```

### MySQL のチューニング

```bash
# my.cnf を編集
sudo vi /etc/my.cnf

# 追加設定例
[mysqld]
max_connections = 200
innodb_buffer_pool_size = 1G
query_cache_size = 64M
```

---

## 監視とアラート

### 基本的な監視項目

- サービスの稼働状態（systemd）
- ディスク使用量
- メモリ使用量
- CPU 使用率
- エラーログ

### 簡易監視スクリプト

```bash
# /usr/local/bin/monitor-factory-shipping.sh
#!/bin/bash

# サービスの状態確認
if ! systemctl is-active --quiet factory-shipping; then
    echo "WARNING: factory-shipping service is not running" | mail -s "Factory Shipping Alert" admin@example.com
fi

# ディスク使用量確認（80%以上で警告）
DISK_USAGE=$(df -h /var | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "WARNING: Disk usage is ${DISK_USAGE}%" | mail -s "Disk Usage Alert" admin@example.com
fi
```

---

## まとめ

このガイドに従ってデプロイを行えば、新・出荷システムを本番環境で安全に運用できます。
問題が発生した場合は、トラブルシューティングセクションを参照してください。
