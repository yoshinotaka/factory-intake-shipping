-- 商品状態管理機能を追加
-- 商品の状態を管理するマスタテーブルと履歴機能を実装

USE factory_shipping;

-- 1. 商品状態マスタテーブルを作成
CREATE TABLE IF NOT EXISTS item_statuses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    status_code VARCHAR(50) NOT NULL UNIQUE COMMENT '状態コード（例: received, shipped）',
    status_name VARCHAR(100) NOT NULL COMMENT '状態名（例: 入荷、出荷済）',
    description VARCHAR(200) NULL COMMENT '説明',
    display_order INT NOT NULL DEFAULT 0 COMMENT '表示順序',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '有効/無効',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status_code (status_code),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品状態マスタ';

-- 2. intake_items テーブルに status_id カラムを追加
ALTER TABLE intake_items
ADD COLUMN status_id INT NULL AFTER scheduled_date;

ALTER TABLE intake_items
ADD INDEX idx_intake_items_status_id (status_id);

ALTER TABLE intake_items
ADD CONSTRAINT fk_intake_items_status_id
    FOREIGN KEY (status_id) REFERENCES item_statuses(id);

-- 3. shipment_logs テーブルに new_status_id カラムを追加
ALTER TABLE shipment_logs
ADD COLUMN new_status_id INT NULL AFTER scanned_code;

ALTER TABLE shipment_logs
ADD INDEX idx_shipment_logs_new_status_id (new_status_id);

ALTER TABLE shipment_logs
ADD CONSTRAINT fk_shipment_logs_new_status_id
    FOREIGN KEY (new_status_id) REFERENCES item_statuses(id);

-- 4. scanned_code を NULL 許可に変更（手動で状態変更する場合に対応）
ALTER TABLE shipment_logs
MODIFY COLUMN scanned_code VARCHAR(100) NULL;

-- 5. 初期状態データを投入
INSERT INTO item_statuses (status_code, status_name, description, display_order, is_active) VALUES
('received', '入荷', '商品が入荷された状態', 10, 1),
('shipped', '出荷済', '商品が出荷された状態', 20, 1),
('returned', '再戻', '商品が返品された状態', 30, 1),
('trouble_in_progress', 'トラブル対応中', 'トラブル対応が進行中の状態', 40, 1),
('trouble_resolved', 'トラブル対応済', 'トラブルが解決された状態', 50, 1),
('rewashing', '再洗中', '商品を再度洗浄している状態', 60, 1);

-- 6. 既存データの status_id を設定（出荷済みの商品）
UPDATE intake_items
SET status_id = (SELECT id FROM item_statuses WHERE status_code = 'shipped')
WHERE is_shipped = TRUE AND status_id IS NULL;

-- 7. 既存データの status_id を設定（未出荷の商品）
UPDATE intake_items
SET status_id = (SELECT id FROM item_statuses WHERE status_code = 'received')
WHERE is_shipped = FALSE AND status_id IS NULL;

-- 8. 既存の shipment_logs の new_status_id を設定
UPDATE shipment_logs
SET new_status_id = (SELECT id FROM item_statuses WHERE status_code = 'shipped')
WHERE status = 'completed' AND new_status_id IS NULL;
