-- intake_items テーブルに returned_at カラムを追加
--
-- 目的:
--   お客様に品物を返却した日時を持つ。値は半蔵（ASTEMPO）の売上台帳を
--   返却日で検索した CSV（uriage_daityo_henkyakubi_shitei<YYYY-MM-DD>.csv）の
--   「返却日時」列（JST）。取り込みは factory_shipping/intake/returns.py。
--
--   返却は status_id ではなくこの列で持つ。預り日 CSV の再取り込み・出荷スキャン・
--   管理画面の状態変更は status_id / shipped_at しか触らないため、返却済が
--   「入荷」に戻ることがない。Analytics API は returned_at が入っていれば
--   status_code='returned_to_customer' / status_name='返却済' を返す。
--
-- 参照: king-req/FACTORY_REQUEST_RETURNED_STATUS_2026-09-21.md
-- 順序: このDDLを先に当ててから、returned_at を含むコードを反映すること
--       （モデルに列があるのにDBに無いと、全列を読むクエリが 1054 で落ちる）。

USE factory_shipping;

-- 1) カラム追加（MariaDB 10.5: NULL 許可の列追加はテーブルを止めない）
ALTER TABLE intake_items
ADD COLUMN returned_at DATETIME NULL COMMENT '顧客への返却日時(JST)' AFTER shipped_at;

-- 2) 返却済の絞り込み・件数確認用
CREATE INDEX idx_intake_items_returned_at ON intake_items(returned_at);
