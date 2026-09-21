-- intake_items テーブルに line_seq カラムを追加
--
-- 目的:
--   タグ番号が空欄の付帯行（会員登録料 / ﾏﾃﾞ早期引取です / 了解済み / LINE使用の記録 等）が
--   同一伝票内に2行以上あると、旧重複キー (store_code, intake_date, tag_number, slip_number)
--   で衝突し、1行に潰れて脱落する不具合の対策。
--   line_seq = 同一 (店,日付,伝票,タグ) のCSV出現順（1,2,3…）。
--   重複排除キーに line_seq を加えることで、空タグ行を 1:1 で保存する。
--
-- 参照: INTAKE_ITEMS_KAIIN_DROP_BUGFIX.md（案A）
-- 適用前に intake_items のバックアップを取得すること（手順は README / 手順書参照）。

USE factory_shipping;

-- 1) カラム追加（既存行はすべて 1。旧ロジックの「先勝ち生存者」= CSV出現順1番目と一致するため整合）
ALTER TABLE intake_items
ADD COLUMN line_seq INT NOT NULL DEFAULT 1 AFTER tag_number;

-- 2) 検索性能のためのインデックス（重複チェックの filter_by に line_seq を含むため）
CREATE INDEX idx_intake_items_line_seq ON intake_items(line_seq);

-- 注意:
--   DBレベルの UNIQUE 制約は付与しない。
--   slip_number / tag_number が NULL・空文字になり得るため、MySQL の UNIQUE は
--   NULL を重複とみなさず誤動作する。重複排除はアプリ層
--   (factory_shipping/intake/services.py) で line_seq を含めて担保する。
