-- is_shipped カラムを削除
-- status_id のみで状態管理を行うため、is_shipped カラムは不要になりました

USE factory_shipping;

-- 1. is_shipped インデックスを削除
ALTER TABLE intake_items
DROP INDEX ix_intake_items_is_shipped;

-- 2. is_shipped カラムを削除
ALTER TABLE intake_items
DROP COLUMN is_shipped;

-- 完了メッセージ
SELECT 'is_shipped カラムの削除が完了しました' AS message;
