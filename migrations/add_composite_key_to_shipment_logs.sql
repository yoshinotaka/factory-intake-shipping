-- ShipmentLogテーブルに複合キーカラムと履歴番号を追加
-- 店舗コード + 預かり日 + タグ番号 + 履歴番号で履歴を管理

USE factory_shipping;

-- 1. 新しいカラムを追加
ALTER TABLE shipment_logs
ADD COLUMN store_code VARCHAR(20) NULL COMMENT '店舗コード' AFTER store_id,
ADD COLUMN intake_date DATE NULL COMMENT '預かり日' AFTER store_code,
ADD COLUMN tag_number VARCHAR(20) NULL COMMENT 'タグ番号' AFTER intake_date,
ADD COLUMN history_number INT NULL COMMENT '履歴番号（同じ商品の何回目の変更か）' AFTER tag_number;

-- 2. 既存データに対して、intake_itemから値をコピー
UPDATE shipment_logs sl
INNER JOIN intake_items ii ON sl.intake_item_id = ii.id
SET
    sl.store_code = ii.store_code,
    sl.intake_date = ii.intake_date,
    sl.tag_number = ii.tag_number;

-- 3. 既存データに対して履歴番号を計算して設定
-- 同じ店舗コード+預かり日+タグ番号の組み合わせごとに、scanned_at順に1から採番
SET @row_number = 0;
SET @prev_key = '';

UPDATE shipment_logs
JOIN (
    SELECT
        id,
        @row_number := IF(@prev_key = CONCAT(store_code, '|', intake_date, '|', tag_number),
                          @row_number + 1,
                          1) AS new_history_number,
        @prev_key := CONCAT(store_code, '|', intake_date, '|', tag_number) AS current_key
    FROM shipment_logs
    ORDER BY store_code, intake_date, tag_number, scanned_at
) AS numbered ON shipment_logs.id = numbered.id
SET shipment_logs.history_number = numbered.new_history_number;

-- 4. インデックスを追加（検索パフォーマンス向上のため）
CREATE INDEX idx_composite_key ON shipment_logs(store_code, intake_date, tag_number, history_number);

-- 完了メッセージ
SELECT '複合キーカラムと履歴番号の追加が完了しました' AS message;
