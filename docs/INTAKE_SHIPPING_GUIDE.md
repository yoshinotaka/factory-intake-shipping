# 入荷・出荷機能 運用ガイド

新・出荷システムの入荷データ取り込みとバーコード出荷処理に関する運用ガイド

---

## 📋 目次

- [機能概要](#機能概要)
- [CSV取り込み処理](#csv取り込み処理)
- [入荷一覧画面](#入荷一覧画面)
- [バーコード出荷処理](#バーコード出荷処理)
- [運用フロー](#運用フロー)
- [トラブルシューティング](#トラブルシューティング)

---

## 機能概要

### 1. CSV取り込み処理

旧システム（`/var/www/html/king-req/`）で生成される hanjow CSV ファイルを読み込み、
新システムのデータベースに入荷データとして取り込みます。

**CSV ファイルパス:**
```
/var/www/html/king-req/downloads_hanjow/hanjow_YYYYMMDD.csv
```

**取り込みタイミング:**
- 毎日 22:30 頃に旧システムが CSV を生成
- その後、cron で自動取り込み（推奨: 22:40）

### 2. 入荷一覧画面

取り込まれた入荷データを一覧表示し、検索・絞り込みができます。

**URL:**
```
http://your-server.com/fi/intake/list
```

**主な機能:**
- ページング表示（デフォルト50件/ページ）
- 店舗・日付・出荷ステータスでの絞り込み
- 預かり日が古い順にソート（未出荷の古いものを優先処理）
- バーコード入力による即座の出荷処理

### 3. バーコード出荷処理

入荷一覧画面でバーコードを入力することで、その場で出荷処理を実行します。

**バーコード形式:**
- 9桁の数値（NW-7）
- 例: `024642123`

**バーコード構成:**
```
0 2 4 | 6 | 4 2 1 2 | 3
├─┬─┘   │   └──┬──┘   │
  │     │      │      └─ チェックデジット（9桁目）
  │     │      └──────── タグ番号本体（5〜8桁目） → "4-212"
  │     └─────────────── チェックデジット（4桁目）
  └───────────────────── 店舗コード（1〜3桁目） → "024"
```

---

## CSV取り込み処理

### 手動実行

#### 今日の日付の CSV を取り込む

```bash
cd /var/www/html/factory-intake-shipping
source venv/bin/activate
python run.py import-hanjow
```

#### 特定の日付の CSV を取り込む

```bash
python run.py import-hanjow --date 2025-11-11
```

### 自動実行（cron 設定）

```bash
# crontab を編集
crontab -e

# 毎日 22:40 に実行（旧システムのCSV生成後）
40 22 * * * cd /var/www/html/factory-intake-shipping && /var/www/html/factory-intake-shipping/venv/bin/python run.py import-hanjow >> /var/log/factory-shipping/import-hanjow.log 2>&1
```

**ログ出力先:**
```
/var/log/factory-shipping/import-hanjow.log
```

### CSV の列構成（重要）

CSV ファイルの実際の列名に応じて、以下のファイルを修正してください。

**修正ファイル:**
```
factory_shipping/intake/services.py:_create_intake_item_from_csv_row()
```

**現在の想定列名（仮）:**
```python
store_code = row.get('店舗コード') or row.get('store_code')
store_name = row.get('店舗名') or row.get('store_name')
tag_number = row.get('タグ番号') or row.get('tag_number')
intake_date = row.get('預かり日') or row.get('intake_date')
customer_name = row.get('顧客名') or row.get('customer_name')
product_name = row.get('商品名') or row.get('product_name')
amount = row.get('金額') or row.get('amount')
```

### 重複チェック

以下の組み合わせで既存データをチェックし、重複の場合はスキップします。

```
店舗コード + 預かり日 + タグ番号 + 伝票番号
```

**注意**: 伝票番号（slip_number）がNULLの場合も適切に処理されます。

---

## 入荷一覧画面

### アクセス方法

```
http://your-server.com/fi/intake/list
```

### 検索条件

| 項目 | 説明 |
|------|------|
| 店舗 | 店舗コードで絞り込み |
| 預かり日（From / To） | 預かり日の範囲で絞り込み |
| 出荷状態 | 「未出荷のみ」または「全て」 |
| 表示件数 | 1ページあたりの表示件数（25/50/100/200） |

### 表示順序

**重要:** 預かり日が古い順（昇順）で表示されます。

これにより、長期間未出荷のものを優先的に処理できます。

### 表示項目

- 店舗コード・店舗名
- 預かり日
- タグ番号
- 顧客名
- 商品名
- 金額
- 出荷状態（未出荷 / 出荷済み）
- 出荷日時

---

## バーコード出荷処理

### 操作手順

1. **入荷一覧画面にアクセス**
   ```
   http://your-server.com/fi/intake/list
   ```

2. **バーコード入力欄にフォーカス**
   - ページ上部の「バーコードスキャン」セクション
   - 自動的にフォーカスされます

3. **HIDバーコードリーダーでスキャン**
   - 9桁のバーコードを読み取り
   - 自動的に Enter が送信されます

4. **結果を確認**
   - 成功: 緑色のメッセージが表示
   - エラー: 黄色または赤色のメッセージが表示

### 成功メッセージの例

```
出荷完了： 店舗 024 / タグ 4-212 / 顧客 山田太郎 様 / 商品 コート
```

### エラーメッセージの例

**該当データなし:**
```
該当する入荷データが見つかりません（店舗: 024 / タグ: 4-212）
```

**既に出荷済み:**
```
このタグは既に出荷済みです（店舗: 024 / タグ: 4-212）
```

**バーコード形式エラー:**
```
バーコードの形式が正しくありません: バーコードは9桁である必要があります
```

**店舗が見つからない:**
```
該当する店舗が見つかりません（店舗コード: 999）
```

### 処理内容

バーコードスキャン時に以下の処理が実行されます。

1. **バーコード解析**
   - 9桁のバーコードから店舗コード（1〜3桁目）とタグ番号（5〜8桁目）を抽出

2. **店舗検索**
   - 店舗コードで Store テーブルを検索

3. **入荷データ検索**
   - 店舗ID、タグ番号、未出荷フラグで IntakeItem を検索

4. **出荷処理（トランザクション）**
   - IntakeItem の `is_shipped` を `True` に更新
   - IntakeItem の `shipped_at` に現在時刻を設定
   - ShipmentLog に出荷ログを作成
   - コミット

5. **結果表示**
   - flash メッセージで結果を表示
   - 一覧画面をリロード

---

## 運用フロー

### 日次運用

```
22:30  旧システムが hanjow_YYYYMMDD.csv を生成
         ↓
22:40  cron が CSV 取り込みを実行
         ↓
翌日   入荷一覧画面で未出荷データを確認
         ↓
       バーコードスキャンで出荷処理
         ↓
       出荷済みデータは灰色で表示
```

### 週次・月次運用

1. **未出荷データの確認**
   - 入荷一覧画面で「預かり日（From）」を設定
   - 古い日付のデータを確認

2. **遅れ品の対応**
   - 預かり日が古いものから順に表示されるため、優先処理しやすい

3. **データのバックアップ**
   - 定期的にデータベースをバックアップ

---

## トラブルシューティング

### CSV 取り込みが失敗する

**症状:**
- `import-hanjow` コマンドがエラーで終了

**確認項目:**

1. **CSV ファイルの存在確認**
   ```bash
   ls -l /var/www/html/king-req/downloads_hanjow/hanjow_*.csv
   ```

2. **ファイルの読み取り権限**
   ```bash
   # ec2-user が読み取れるか確認
   cat /var/www/html/king-req/downloads_hanjow/hanjow_20251111.csv | head
   ```

3. **CSV の文字コード**
   ```bash
   file /var/www/html/king-req/downloads_hanjow/hanjow_20251111.csv
   # UTF-8 であることを確認
   ```

4. **CSV の列名**
   - `factory_shipping/intake/services.py:_create_intake_item_from_csv_row()` の列名が実際の CSV と一致しているか確認

5. **ログの確認**
   ```bash
   tail -f /var/log/factory-shipping/import-hanjow.log
   ```

### バーコードスキャンが反応しない

**症状:**
- バーコードを読み取っても何も起こらない

**確認項目:**

1. **バーコードリーダーの設定**
   - HIDモードになっているか
   - Enter キーが自動送信されるか

2. **入力欄のフォーカス**
   - ページロード時に自動フォーカスされているか
   - 手動でクリックして確認

3. **ブラウザの JavaScript が有効か**
   - F12 開発者ツールでエラーを確認

### 該当データが見つからない

**症状:**
- バーコードをスキャンしても「該当する入荷データが見つかりません」

**確認項目:**

1. **CSV 取り込みが完了しているか**
   ```sql
   SELECT * FROM intake_items
   WHERE store_code = '024' AND tag_number = '4-212'
   LIMIT 10;
   ```

2. **タグ番号の形式**
   - データベースには "4-212" 形式で保存されているか
   - バーコード解析が正しく動作しているか

3. **店舗コードの確認**
   ```sql
   SELECT * FROM stores WHERE store_code = '024';
   ```

### ページング表示がおかしい

**症状:**
- ページ数が正しくない、データが表示されない

**確認項目:**

1. **検索条件の確認**
   - 日付範囲が正しいか
   - 出荷ステータスフィルタが適切か

2. **データ件数の確認**
   ```sql
   SELECT COUNT(*) FROM intake_items WHERE is_shipped = 0;
   ```

---

## データベーススキーマ

### IntakeItem テーブル

| カラム名 | 型 | 説明 |
|---------|---|------|
| id | INTEGER | 主キー |
| store_id | INTEGER | 店舗ID（FK） |
| store_code | VARCHAR(10) | 店舗コード |
| store_name | VARCHAR(100) | 店舗名 |
| tag_number | VARCHAR(20) | タグ番号（例: "4-212"） |
| product_name | VARCHAR(200) | 商品名 |
| customer_name | VARCHAR(100) | 顧客名 |
| amount | INTEGER | 金額（円） |
| intake_date | DATE | 預かり日 |
| is_shipped | BOOLEAN | 出荷済みフラグ |
| shipped_at | DATETIME | 出荷日時 |
| created_at | DATETIME | 作成日時 |
| updated_at | DATETIME | 更新日時 |

### ShipmentLog テーブル

| カラム名 | 型 | 説明 |
|---------|---|------|
| id | INTEGER | 主キー |
| intake_item_id | INTEGER | 入荷データID（FK） |
| store_id | INTEGER | 店舗ID（FK） |
| scanned_code | VARCHAR(100) | スキャンされたバーコード |
| scanned_at | DATETIME | スキャン日時 |
| scanned_by_user_id | INTEGER | スキャン実行ユーザー（FK） |
| status | VARCHAR(20) | ステータス（'completed', 'error' など） |
| created_at | DATETIME | 作成日時 |

---

## まとめ

この機能により、以下が実現できます。

1. **自動データ取り込み**
   - 旧システムの CSV を毎日自動取り込み
   - 重複チェックでデータの整合性を維持

2. **効率的な出荷処理**
   - バーコードスキャンで即座に出荷完了
   - 画面遷移不要で連続スキャン可能

3. **未出荷データの可視化**
   - 預かり日が古い順にソート
   - 長期未出荷品を優先処理

4. **履歴管理**
   - すべての出荷処理を ShipmentLog に記録
   - 誰がいつスキャンしたかを追跡可能

運用に関する質問や問題があれば、システム管理者までお問い合わせください。
