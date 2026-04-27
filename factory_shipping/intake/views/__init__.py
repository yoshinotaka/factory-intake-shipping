"""
入荷機能 - Blueprint 統合モジュール

intake_bp を一元管理し、各分割モジュールからルート関数をインポート。
循環インポートを防ぐため、Blueprint インスタンスはここだけで生成する。
"""

from flask import Blueprint

# Blueprint インスタンスを作成（唯一のインスタンス）
intake_bp = Blueprint('intake', __name__, url_prefix='/fi/intake')

# 各分割モジュールを import（ルート関数の登録を実行）
from factory_shipping.intake.views import dashboard
from factory_shipping.intake.views import list_views
from factory_shipping.intake.views import export
from factory_shipping.intake.views import upload
from factory_shipping.intake.views import item_actions
from factory_shipping.intake.views import api  # JSON API（king-req連携用）

# helpers は内部関数のみなので import 不要（必要に応じて各モジュールが直接 import）
