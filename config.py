"""
新・出荷システム - 設定ファイル

環境変数を .env ファイルから読み込み、環境ごとの設定を管理します。
"""

import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# .env ファイルを読み込む（プロジェクトルートを明示的に指定）
project_root = Path(__file__).parent.absolute()
env_file = project_root / '.env'
if env_file.exists():
    load_dotenv(dotenv_path=env_file)


class BaseConfig:
    """基本設定（全環境共通）"""

    # プロジェクトルート
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    # Flask 基本設定
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # セッション設定
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = False  # 本番環境では True に
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_PATH = '/fi/'

    # データベース設定
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # SQL ログを表示する場合は True
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }

    # ファイルアップロード設定
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

    # タイムゾーン
    TIMEZONE = 'Asia/Tokyo'


class DevelopmentConfig(BaseConfig):
    """開発環境設定"""

    DEBUG = True
    TESTING = False

    # データベース接続（開発環境）
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://user:password@localhost/factory_shipping_dev?charset=utf8mb4'

    SQLALCHEMY_ECHO = True  # 開発時は SQL ログを表示


class ProductionConfig(BaseConfig):
    """本番環境設定"""

    DEBUG = False
    TESTING = False

    # 本番環境では必ず環境変数から取得
    # 注意: クラス定義時ではなく、実際に使用される時にチェック
    @property
    def SECRET_KEY(self):
        secret_key = os.environ.get('SECRET_KEY')
        if not secret_key:
            raise ValueError("本番環境では SECRET_KEY 環境変数が必須です")
        return secret_key

    # データベース接続（本番環境）
    @property
    def SQLALCHEMY_DATABASE_URI(self):
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise ValueError("本番環境では DATABASE_URL 環境変数が必須です")
        return database_url

    # セキュリティ強化
    SESSION_COOKIE_SECURE = True

    # エラーログ設定
    LOG_LEVEL = 'INFO'


class TestingConfig(BaseConfig):
    """テスト環境設定"""

    DEBUG = False
    TESTING = True

    # テスト用インメモリDB または 専用テストDB
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    # CSRF 保護を無効化（テスト時）
    WTF_CSRF_ENABLED = False


# 環境名から設定クラスへのマッピング
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env_name=None):
    """
    環境名に応じた設定オブジェクトを返す

    Args:
        env_name (str): 環境名 ('development', 'production', 'testing')
                       未指定の場合は環境変数 FLASK_ENV から取得

    Returns:
        設定クラスのインスタンス
    """
    if env_name is None:
        env_name = os.environ.get('FLASK_ENV', 'development')

    return config_by_name.get(env_name, DevelopmentConfig)
