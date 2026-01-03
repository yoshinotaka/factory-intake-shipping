-- ジャーナルデータテーブルの作成
-- 日次でCSVからインポートされるジャーナルデータを格納

CREATE TABLE IF NOT EXISTS journal_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL COMMENT '日付',
    store_no VARCHAR(10) NOT NULL COMMENT '店舗番号',
    slip_no VARCHAR(20) NOT NULL COMMENT '伝票番号',
    customer_name VARCHAR(100) COMMENT '顧客名',
    phone VARCHAR(20) COMMENT '電話番号',
    slip_content TEXT COMMENT '伝票内容',
    imported_at DATETIME NOT NULL COMMENT 'インポート日時',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '作成日時',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新日時',

    -- インデックス
    INDEX idx_date (date),
    INDEX idx_store_no (store_no),
    INDEX idx_slip_no (slip_no),
    INDEX idx_customer_name (customer_name),
    INDEX idx_imported_at (imported_at),

    -- 複合インデックス（同じデータの重複チェック用）
    UNIQUE INDEX idx_unique_entry (date, store_no, slip_no, customer_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ジャーナルデータ';
