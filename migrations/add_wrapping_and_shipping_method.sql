-- 包装と出荷便のカラムを追加
ALTER TABLE intake_items
ADD COLUMN wrapping VARCHAR(100) NULL COMMENT '包装',
ADD COLUMN shipping_method VARCHAR(100) NULL COMMENT '出荷便';
