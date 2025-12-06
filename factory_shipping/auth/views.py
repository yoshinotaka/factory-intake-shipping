"""
認証機能 - ビュー

ログイン、ログアウト、ユーザー管理
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from factory_shipping.extensions import db
from factory_shipping.models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """ログイン"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('このアカウントは無効化されています', 'error')
                return redirect(url_for('auth.login'))

            login_user(user, remember=remember)
            flash(f'ようこそ、{user.username} さん', 'success')

            # next パラメータがあればそちらにリダイレクト
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.index'))
        else:
            flash('ユーザー名またはパスワードが正しくありません', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """ログアウト"""
    logout_user()
    flash('ログアウトしました', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    """プロフィール"""
    return render_template('auth/profile.html')


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """パスワード変更"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('現在のパスワードが正しくありません', 'error')
        elif new_password != confirm_password:
            flash('新しいパスワードが一致しません', 'error')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('パスワードを変更しました', 'success')
            return redirect(url_for('auth.profile'))

    return render_template('auth/change_password.html')
