-- 担当者マスターテーブルを作成
-- 工場の従業員（担当者）を管理するためのマスターテーブル

USE factory_shipping;

-- 1. 担当者マスターテーブルを作成
CREATE TABLE IF NOT EXISTS factory_operators (
    id INT AUTO_INCREMENT PRIMARY KEY,
    operator_code VARCHAR(20) NOT NULL UNIQUE COMMENT '担当者コード（例: OP001）',
    operator_name VARCHAR(100) NOT NULL COMMENT '担当者名',
    is_active BOOLEAN DEFAULT TRUE COMMENT '有効/無効',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '作成日時',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新日時',
    INDEX idx_operator_code (operator_code),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='工場担当者マスター';

-- 2. shipment_logsテーブルにoperator_idカラムを追加
ALTER TABLE shipment_logs
ADD COLUMN operator_id INT NULL COMMENT '担当者ID（工場の従業員）' AFTER scanned_by_user_id,
ADD INDEX idx_operator_id (operator_id),
ADD CONSTRAINT fk_shipment_logs_operator
    FOREIGN KEY (operator_id)
    REFERENCES factory_operators(id)
    ON DELETE SET NULL;

-- 完了メッセージ
SELECT '担当者マスターテーブルとshipment_logsへのカラム追加が完了しました' AS message;
