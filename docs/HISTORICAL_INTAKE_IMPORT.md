# 過去分（預り日 2021-01〜2025-09）の入荷データ取り込み 手順書

作成日: 2026-09-22
依頼: kinglinesystem `REQ-20260921-historical-intake`（king-req `handoff/`）
コード: `factory_shipping/intake/historical.py`、`run.py import-historical` ほか

## 1. 何をするか

- 預り日指定 CSV（`uriage_daityo_download_csv_<YYYY>/uriage_daityo_oazukaribi_shitei<YYYY-MM-DD>.csv`）の
  2021-01-04〜2025-09-30（1,612 ファイル・約 150 万行）を `intake_items` に取り込む。
- 返却 CSV の過去分をもう一度反映し、返却 CSV に無い品目は預り日 CSV の「返却日時」列で補う。
- 既存の品目（2025-10-01 以降）に顧客コードを入れる。

## 2. 決めたこと

| 項目 | 内容 |
|---|---|
| 取消の行 | 取消列が `-` 以外の行は取り込まない（毎晩の取り込み元 `hanjow_*.csv` は取消を表示しない設定で、もともと入っていない） |
| 重複キー | 毎晩の取り込みと同じ（店舗・預り日・タグ・伝票No・商品名・line_seq）。何度流しても同じ |
| 状態 | `status_id` = 入荷。API は、返却の記録が無い過去分を `no_return_record` / 返却記録なし で返す |
| 業務の範囲 | 預り日 2025-10-01 より前（`models.BUSINESS_MIN_INTAKE_DATE`）は、工場の業務画面・スキャン・状態変更・請求の検索に出さない（`IntakeItem.in_business_scope()`） |
| 返却日時の優先順 | 返却 CSV > 預り日 CSV の「返却日時」列（まだ空の品目だけ埋める） |
| 顧客コード | `customer_code`。過去分は取り込み時、既存は `hanjow_*.csv` から埋め戻し、以後は毎晩の取り込みで入る |

## 3. 本番の手順（2026-09-24 木・全店定休日）

```bash
cd /var/www/html/factory-intake-shipping
P=venv/bin/python

# 0. バックアップ
./scripts/backup_mysql.sh

# 1. 列と索引（コードより先に。LOCK=NONE で止まらない）
mysql -u factory_user -p factory_shipping < migrations/add_customer_code_and_history_indexes.sql

# 2. コードを反映して再起動（業務画面の除外・API・毎晩の取り込みの顧客コード）
sudo systemctl restart factory-shipping

# 3. 1 日分 → 受け入れ確認 1（0021・2022-06-01 が 237 件）
$P run.py import-historical --date 2022-06-01
# 4. 1 か月分
$P run.py import-historical --from 2022-06-01 --to 2022-06-30
# 5. 全期間（リハーサルで 5 分）
$P run.py import-historical --all

# 6. 返却 CSV の過去分を再反映（リハーサルで約 20 分）
$P run.py import-returns --all
# 7. 預り日 CSV の返却日時列で補う（6 の後）
$P run.py fill-returned-from-intake --all
# 8. 既存品目の顧客コード
$P run.py backfill-customer-code --all
```

どのコマンドも `--dry-run` で件数だけ見られる。途中で止まっても、同じコマンドを流し直せばよい。

## 4. 確認

- kinglinesystem の受け入れ確認 §6 の 1〜5（依頼書）
- 工場の入荷一覧・タグ検索・ダッシュボードに 2025-09 以前の品目が出ないこと
- `/customers/history`（期間なし）が速いこと（索引 `idx_intake_items_customer_name_date` / `_customer_code_date`）

## 5. 戻し方

- 取り込んだ過去分だけを消す: `DELETE FROM intake_items WHERE intake_date < '2025-10-01';`
  （`shipment_logs` / `intake_request_links` が参照していないことを先に確認）
- 返却日時・顧客コードは既存の値を上書きしていない（空の品目だけ埋めた）ので、戻す必要は無い
- すべて戻すときはバックアップから復元
