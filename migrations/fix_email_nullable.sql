-- emailカラムをNULL許可に変更
-- 実行日: 2025-12-22

-- まず、email列のユニーク制約を削除
ALTER TABLE users DROP INDEX ix_users_email;

-- emailカラムをNULL許可に変更
ALTER TABLE users MODIFY COLUMN email VARCHAR(120) NULL;

-- ユニーク制約を再追加（NULLの場合は複数許可）
CREATE UNIQUE INDEX ix_users_email ON users(email);
