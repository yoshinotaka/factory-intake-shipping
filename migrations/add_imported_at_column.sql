-- intake_items テーブルに imported_at カラムを追加
-- CSV取り込み日時を記録するためのカラム

USE factory_shipping;

-- カラムを追加
ALTER TABLE intake_items
ADD COLUMN imported_at DATETIME NULL AFTER notes;

-- インデックスを追加（検索性能向上のため）
CREATE INDEX idx_intake_items_imported_at ON intake_items(imported_at);

-- 既存データに対して created_at を imported_at にコピー（オプション）
-- UPDATE intake_items SET imported_at = created_at WHERE imported_at IS NULL;
