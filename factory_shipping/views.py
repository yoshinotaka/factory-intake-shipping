"""
新・出荷システム - メインビュー

ルートパスやダッシュボードなどの共通ビューを定義
"""

from flask import Blueprint, render_template, request, jsonify, session
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


@main_bp.route('/features')
@login_required
def features():
    """機能一覧ページ"""
    return render_template('features.html')


@main_bp.route('/set-operator', methods=['POST'])
@login_required
def set_operator():
    """
    セッションに担当者を設定する

    Request JSON:
        operator_id (int): 担当者ID（0の場合は未設定にする）

    Returns:
        JSON: 成功/失敗メッセージ
    """
    try:
        data = request.get_json()
        operator_id = data.get('operator_id', 0)

        if operator_id == 0 or operator_id is None:
            # 担当者を未設定にする
            session.pop('operator_id', None)
            return jsonify({
                'success': True,
                'message': '担当者を未設定にしました',
                'operator_id': None
            })
        else:
            # 担当者IDをセッションに保存
            from factory_shipping.models import FactoryOperator
            operator = FactoryOperator.query.get(operator_id)

            if not operator:
                return jsonify({
                    'success': False,
                    'message': '担当者が見つかりません'
                }), 404

            if not operator.is_active:
                return jsonify({
                    'success': False,
                    'message': 'この担当者は無効化されています'
                }), 400

            session['operator_id'] = operator_id

            return jsonify({
                'success': True,
                'message': f'{operator.operator_name} を担当者に設定しました',
                'operator_id': operator_id,
                'operator_name': operator.operator_name
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500
