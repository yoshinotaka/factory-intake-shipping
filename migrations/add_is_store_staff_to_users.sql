-- 店舗スタッフフラグをusersテーブルに追加
-- 実行日: 2025-12-22

ALTER TABLE users
ADD COLUMN is_store_staff BOOLEAN NOT NULL DEFAULT FALSE;

-- インデックスを追加（検索を高速化）
CREATE INDEX idx_users_is_store_staff ON users(is_store_staff);
