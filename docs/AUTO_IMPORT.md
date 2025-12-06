# hanjow CSV 自動取り込み機能

## 概要

指定フォルダに毎日22:30に配置される hanjow CSV ファイルを自動的に取り込むシステムです。

- **自動取り込み時刻**: 毎日 22:35（CSVファイルは22:30に配置される想定）
- **重複チェック**: 店舗コード + 預かり日 + タグ番号の組み合わせで重複を防止
- **差分取り込み**: 遡って取得したデータでも、既存データと混在していても差分のみを取り込み
- **取り込み日時記録**: `imported_at` カラムに取り込み日時を記録

---

## 機能

### 1. 自動取り込み

毎日22:35にcronが実行され、その日のhanjow CSVファイルを自動的に取り込みます。

**特徴**:
- CSVファイルが見つからない日は正常終了（エラーにならない）
- ファイルが空（0バイト）の場合もスキップ
- 重複データは自動的にスキップされる

### 2. 手動取り込み

特定の日付のCSVを手動で取り込むこともできます。

```bash
# 指定日付のCSVを取り込み
/var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh 2025-11-29

# 今日の日付のCSVを取り込み
/var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh
```

### 3. 一括取り込み

過去の複数日分をまとめて取り込むことができます。

```bash
# 2025-11-01 から 2025-11-29 までを一括取り込み
/var/www/html/factory-intake-shipping/scripts/bulk_import_hanjow.sh 2025-11-01 2025-11-29

# 過去7日分を一括取り込み
/var/www/html/factory-intake-shipping/scripts/bulk_import_hanjow.sh $(date -d '7 days ago' '+%Y-%m-%d') $(date '+%Y-%m-%d')
```

---

## データベーススキーマ変更

### 追加カラム: `imported_at`

`intake_items` テーブルに CSV 取り込み日時を記録するカラムを追加しました。

```sql
ALTER TABLE intake_items
ADD COLUMN imported_at DATETIME NULL;

CREATE INDEX idx_intake_items_imported_at ON intake_items(imported_at);
```

**用途**:
- いつ取り込まれたデータかを追跡
- 取り込み履歴の監査
- トラブルシューティング

---

## 重複チェックロジック

重複は以下の3つのフィールドの組み合わせで判定されます：

```python
existing = IntakeItem.query.filter_by(
    store_code=store_code,        # 店舗コード (例: "0002")
    intake_date=intake_date,      # 預かり日 (例: 2025-11-28)
    tag_number=tag_number         # タグ番号 (例: "00-898")
).first()

if existing:
    # 重複データをスキップ
    return 'skipped'
```

**メリット**:
- 同じデータが複数回取り込まれることを防ぐ
- 遡って取得したCSVと既存データが混在しても安全
- データベースの整合性を保つ

---

## cron設定

### 自動設定（推奨）

システムcronに設定する方法：

```bash
# cron設定ファイルをコピー
sudo cp /var/www/html/factory-intake-shipping/deployment/factory-shipping.cron /etc/cron.d/factory-shipping

# パーミッション設定
sudo chmod 644 /etc/cron.d/factory-shipping
sudo chown root:root /etc/cron.d/factory-shipping
```

**設定内容**:
```
35 22 * * * ec2-user /var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh >> /var/log/factory-shipping/auto-import.log 2>&1
```

### 手動設定

ユーザーcronに設定する方法：

```bash
# crontabを編集
crontab -e

# 以下の行を追加
35 22 * * * /var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh >> /var/log/factory-shipping/auto-import.log 2>&1
```

### cron設定の確認

```bash
# システムcron
cat /etc/cron.d/factory-shipping

# ユーザーcron
crontab -l
```

---

## ログ

### ログファイルの場所

```
/var/log/factory-shipping/
├── auto-import.log         # 自動取り込みログ
├── auto-import-error.log   # エラーログ
└── bulk-import.log         # 一括取り込みログ
```

### ログの確認

```bash
# 最新20行を表示
tail -20 /var/log/factory-shipping/auto-import.log

# リアルタイムで監視
tail -f /var/log/factory-shipping/auto-import.log

# エラーログを確認
tail -20 /var/log/factory-shipping/auto-import-error.log
```

### ログの例

**成功時**:
```
[2025-11-29 22:35:00] ========================================
[2025-11-29 22:35:00] hanjow CSV 自動取り込み開始
[2025-11-29 22:35:00] ========================================
[2025-11-29 22:35:00] 対象日付: 2025-11-29 (今日)
[2025-11-29 22:35:00] CSVファイル: /var/www/html/king-req/downloads_hanjow/hanjow_20251129.csv
[2025-11-29 22:35:00] ファイルサイズ: 138240 バイト
[2025-11-29 22:35:00] CSV取り込みを開始...
============================================================
  取り込み結果
============================================================
  総行数:     628 行
  新規作成:   628 件
  スキップ:   0 件（重複）
  エラー:     0 件
============================================================
取り込みが正常に完了しました。
[2025-11-29 22:35:03] CSV取り込みが正常に完了しました
[2025-11-29 22:35:03] ========================================
```

**CSVファイルが見つからない場合**:
```
[2025-11-29 22:35:00] ========================================
[2025-11-29 22:35:00] hanjow CSV 自動取り込み開始
[2025-11-29 22:35:00] ========================================
[2025-11-29 22:35:00] 対象日付: 2025-11-29 (今日)
[2025-11-29 22:35:00] CSVファイル: /var/www/html/king-req/downloads_hanjow/hanjow_20251129.csv
[2025-11-29 22:35:00] ERROR: CSVファイルが見つかりません: /var/www/html/king-req/downloads_hanjow/hanjow_20251129.csv
[2025-11-29 22:35:00] スキップします（取得できない日の可能性があります）
[2025-11-29 22:35:00] ========================================
```

---

## トラブルシューティング

### 問題1: cronが実行されない

**確認方法**:
```bash
# cron設定を確認
sudo cat /etc/cron.d/factory-shipping

# cronログを確認（システムによって異なる）
sudo tail -f /var/log/cron
# または
sudo journalctl -u cron -f
```

**対処法**:
```bash
# cron設定ファイルのパーミッションを確認
ls -l /etc/cron.d/factory-shipping
# 644 root:root であることを確認

# cronサービスを再起動
sudo systemctl restart crond
```

### 問題2: 取り込みに失敗する

**確認方法**:
```bash
# エラーログを確認
cat /var/log/factory-shipping/auto-import-error.log

# 手動で実行してエラーを確認
/var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh 2025-11-29
```

**よくある原因**:
1. **Python仮想環境が見つからない**
   ```bash
   # venvが存在するか確認
   ls -l /var/www/html/factory-intake-shipping/venv/bin/python
   ```

2. **データベース接続エラー**
   ```bash
   # .env の DATABASE_URL を確認
   cat /var/www/html/factory-intake-shipping/.env | grep DATABASE_URL
   ```

3. **CSVファイルのエンコーディング問題**
   - エンコーディングは自動検出されますが、特殊な文字コードの場合は失敗する可能性があります

### 問題3: 重複データが取り込まれる

**確認方法**:
```bash
# 重複データを確認
mysql -u factory_user -pfactory_password factory_shipping -e "
SELECT store_code, intake_date, tag_number, COUNT(*) as count
FROM intake_items
GROUP BY store_code, intake_date, tag_number
HAVING count > 1;
"
```

**対処法**:
重複チェックロジックは [services.py:212-220](factory_shipping/intake/services.py#L212-L220) で実装されています。通常は発生しませんが、もし発生した場合は手動で削除してください。

---

## データの確認

### 取り込まれたデータを確認

```bash
# 総データ数
mysql -u factory_user -pfactory_password factory_shipping -e "
SELECT COUNT(*) as total FROM intake_items;
"

# imported_at が記録されているデータ数
mysql -u factory_user -pfactory_password factory_shipping -e "
SELECT COUNT(*) as with_import_time FROM intake_items WHERE imported_at IS NOT NULL;
"

# 最新の取り込み日時
mysql -u factory_user -pfactory_password factory_shipping -e "
SELECT MAX(imported_at) as last_import FROM intake_items;
"

# 日付別の取り込み件数
mysql -u factory_user -pfactory_password factory_shipping -e "
SELECT DATE(imported_at) as import_date, COUNT(*) as count
FROM intake_items
WHERE imported_at IS NOT NULL
GROUP BY DATE(imported_at)
ORDER BY import_date DESC
LIMIT 10;
"
```

---

## まとめ

### 実装済み機能

✅ **読み込み日時記録**: `imported_at` カラムに取り込み日時を保存
✅ **重複チェック**: 店舗コード + 預かり日 + タグ番号で重複を防止
✅ **差分取り込み**: 既存データと新規データが混在しても差分のみ取り込み
✅ **自動取り込みスクリプト**: 毎日22:35に自動実行
✅ **一括取り込みスクリプト**: 複数日分をまとめて取り込み
✅ **cron設定**: システムcronまたはユーザーcronに対応
✅ **ログ記録**: 詳細なログを `/var/log/factory-shipping/` に保存

### 使い方

1. **cron設定** (初回のみ):
   ```bash
   sudo cp /var/www/html/factory-intake-shipping/deployment/factory-shipping.cron /etc/cron.d/factory-shipping
   sudo chmod 644 /etc/cron.d/factory-shipping
   sudo chown root:root /etc/cron.d/factory-shipping
   ```

2. **自動実行**: 毎日22:35に自動で取り込まれます

3. **手動実行** (必要に応じて):
   ```bash
   # 特定日付
   /var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh 2025-11-29

   # 複数日分
   /var/www/html/factory-intake-shipping/scripts/bulk_import_hanjow.sh 2025-11-01 2025-11-29
   ```

4. **ログ確認**:
   ```bash
   tail -f /var/log/factory-shipping/auto-import.log
   ```
