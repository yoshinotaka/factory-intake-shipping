"""顧客利用状況分析 API (intake_items 外部公開)

社内別システム (https://kingdrysystem.com) からのみアクセスを許可する読み取り専用 API。

主な防御層:
  1. HTTPS 必須 (nginx 側で強制)
  2. Origin/Referer ホワイトリスト (https://kingdrysystem.com のみ)
  3. API キー認証 (Authorization: Bearer <key>) — constant-time 比較
  4. レート制限 (IP + キー単位、スライディングウィンドウ)
  5. 監査ログ (全リクエスト記録)
  6. GET のみ・ページネーション上限
  7. CORS (browser fetch 用、Origin ホワイトリスト一致のみ ACAO 返却)
"""

from flask import Blueprint

analytics_api_bp = Blueprint(
    'analytics_api',
    __name__,
    url_prefix='/fi/api/v1/analytics',
)

# ルート関数を登録 (循環インポート回避)
from factory_shipping.analytics_api import security  # noqa: E402,F401
from factory_shipping.analytics_api import views  # noqa: E402,F401
