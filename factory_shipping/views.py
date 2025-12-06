"""
新・出荷システム - メインビュー

ルートパスやダッシュボードなどの共通ビューを定義
"""

from flask import Blueprint, render_template
from flask_login import login_required

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """ダッシュボード（ホーム画面）"""
    return render_template('index.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """ダッシュボード"""
    return render_template('dashboard.html')
