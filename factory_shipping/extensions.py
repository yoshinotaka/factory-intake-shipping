"""
新・出荷システム - Flask 拡張機能

各種 Flask 拡張機能のインスタンスを管理します。
将来的に他のシステムと共通化する場合は、このファイルを共通ライブラリに移動できます。
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO

# SQLAlchemy インスタンス
db = SQLAlchemy()

# Flask-Login インスタンス
login_manager = LoginManager()

# Flask-SocketIO インスタンス
socketio = SocketIO()


def init_extensions(app):
    """
    Flask 拡張機能を初期化する

    Args:
        app (Flask): Flask アプリケーションインスタンス
    """
    # SQLAlchemy の初期化
    db.init_app(app)

    # Flask-Login の初期化
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'ログインが必要です'
    login_manager.login_message_category = 'info'

    # ユーザーローダーの設定
    @login_manager.user_loader
    def load_user(user_id):
        from factory_shipping.models import User
        return User.query.get(int(user_id))

    # Flask-SocketIO の初期化
    # path パラメータで Socket.IO のエンドポイントを指定
    socketio.init_app(app, cors_allowed_origins="*", async_mode='eventlet', path='/fi/socket.io')
