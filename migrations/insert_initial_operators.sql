-- 初期担当者データを投入

USE factory_shipping;

-- 担当者データを投入（サンプル）
INSERT INTO factory_operators (operator_code, operator_name, is_active) VALUES
('OP001', '担当者A', TRUE),
('OP002', '担当者B', TRUE),
('OP003', '担当者C', TRUE),
('OP004', '担当者D', TRUE),
('OP005', '担当者E', TRUE)
ON DUPLICATE KEY UPDATE
    operator_name = VALUES(operator_name),
    is_active = VALUES(is_active);

-- 完了メッセージ
SELECT '初期担当者データの投入が完了しました' AS message;
SELECT * FROM factory_operators ORDER BY operator_code;
