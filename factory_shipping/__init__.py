"""
新・出荷システム - Flask アプリケーションファクトリ

将来的に他のシステムと統合しやすいよう、
アプリケーションファクトリパターンを採用しています。
"""

from flask import Flask
from config import get_config
import os


def create_app(config_name=None):
    """
    Flask アプリケーションを作成する（アプリケーションファクトリパターン）

    Args:
        config_name (str): 設定名 ('development', 'production', 'testing')

    Returns:
        Flask: 設定済みの Flask アプリケーション
    """
    # プロジェクトルートを取得（config.pyがあるディレクトリ）
    project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    template_folder = os.path.join(project_root, 'templates')
    static_folder = os.path.join(project_root, 'static')
    
    app = Flask(
        __name__,
        template_folder=template_folder,
        static_folder=static_folder
    )

    # 設定の読み込み
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # 拡張機能の初期化
    from factory_shipping.extensions import init_extensions
    init_extensions(app)

    # ブループリント（各機能モジュール）の登録
    register_blueprints(app)

    # エラーハンドラの登録
    register_error_handlers(app)

    # アップロードフォルダの作成
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # コンテキストプロセッサ（テンプレート内でグローバル変数を使えるように）
    register_context_processors(app)

    return app


def register_blueprints(app):
    """ブループリント（各機能モジュール）を登録"""

    # 入荷機能
    from factory_shipping.intake.views import intake_bp
    app.register_blueprint(intake_bp, url_prefix='/fi/intake')

    # 出荷機能
    from factory_shipping.shipping.views import shipping_bp
    app.register_blueprint(shipping_bp, url_prefix='/fi/shipping')

    # ステータス確認機能
    from factory_shipping.status.views import status_bp
    app.register_blueprint(status_bp, url_prefix='/fi/status')

    # 認証機能
    from factory_shipping.auth.views import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/fi/auth')

    # ルートパス
    from factory_shipping.views import main_bp
    app.register_blueprint(main_bp, url_prefix='/fi')


def register_error_handlers(app):
    """エラーハンドラを登録"""

    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        from factory_shipping.extensions import db
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template
        return render_template('errors/403.html'), 403


def register_context_processors(app):
    """テンプレート内で使用可能なグローバル変数を登録"""

    @app.context_processor
    def inject_globals():
        return {
            'app_name': '新・出荷システム',
            'version': '1.0.0',
            'min': min,
            'max': max
        }
