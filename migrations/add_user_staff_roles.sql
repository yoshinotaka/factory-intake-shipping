-- ユーザーテーブルに新しいスタッフロールカラムを追加
-- 工場スタッフ、シフト作成スタッフ、事務スタッフ

-- 工場スタッフ権限カラム
ALTER TABLE users ADD COLUMN is_factory_staff BOOLEAN NOT NULL DEFAULT FALSE;

-- シフト作成スタッフ権限カラム
ALTER TABLE users ADD COLUMN is_shift_staff BOOLEAN NOT NULL DEFAULT FALSE;

-- 事務スタッフ権限カラム
ALTER TABLE users ADD COLUMN is_office_staff BOOLEAN NOT NULL DEFAULT FALSE;

-- インデックスを追加（検索効率化）
CREATE INDEX idx_users_is_factory_staff ON users(is_factory_staff);
CREATE INDEX idx_users_is_shift_staff ON users(is_shift_staff);
CREATE INDEX idx_users_is_office_staff ON users(is_office_staff);
