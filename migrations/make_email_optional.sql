-- メールアドレスを必須から任意に変更
-- ユーザー作成時にメールアドレスを入力しなくても良いようにする

USE factory_shipping;

-- 1. email カラムを NULL 許可に変更
ALTER TABLE users
MODIFY COLUMN email VARCHAR(120) NULL;

-- 2. 既存の空文字列を NULL に変換（一意制約の問題を回避）
UPDATE users
SET email = NULL
WHERE email = '';

-- 完了メッセージ
SELECT 'メールアドレスを任意項目に変更しました' AS message;





