-- intake_items: 顧客コードの列と、過去分（2021-01〜2025-09）の取り込みに備えた索引 (2026-09-22)
--
-- 背景: kinglinesystem の依頼 REQ-20260921-historical-intake。
--   約 150 万行を足して 7 倍になるため、会員利用履歴（/customers/history）の顧客名・顧客コードでの
--   検索と、取り込み・スキャンの店舗＋タグでの検索に索引を足す。
--   customer_name の検索は索引が無く、25 万行の時点でも 1 回 約 0.1 秒の全件走査だった。
--
-- ⚠️ コードより先に適用すること（models.IntakeItem.customer_code を読むコードが先に出ると 1054 で 500）。
-- LOCK=NONE: 追加中も読み書きできる（止まらない）。
--
-- 適用:
--   mysql -u factory_user -p factory_shipping < migrations/add_customer_code_and_history_indexes.sql
--
-- ロールバック:
--   ALTER TABLE intake_items DROP INDEX idx_intake_items_customer_code_date,
--     DROP INDEX idx_intake_items_customer_name_date, DROP INDEX idx_intake_items_store_tag_date,
--     DROP INDEX idx_intake_items_date_tag;
--   ALTER TABLE intake_items DROP COLUMN customer_code;

ALTER TABLE intake_items
  ADD COLUMN customer_code VARCHAR(20) NULL COMMENT '顧客ｺｰﾄﾞ(12桁)' AFTER customer_name,
  ALGORITHM=INSTANT;

ALTER TABLE intake_items
  ADD INDEX idx_intake_items_customer_name_date (customer_name, intake_date),
  ADD INDEX idx_intake_items_customer_code_date (customer_code, intake_date),
  ADD INDEX idx_intake_items_store_tag_date (store_code, tag_number, intake_date),
  -- 入荷一覧の件数（預り日 2025-10-01 以降・タグあり）を、預り日の範囲だけ読んで数える。
  -- これが無いと store_tag_date を丸ごと読む計画が選ばれ、一覧が 1.7 秒になる（リハーサルで確認）
  ADD INDEX idx_intake_items_date_tag (intake_date, tag_number),
  ALGORITHM=INPLACE, LOCK=NONE;
