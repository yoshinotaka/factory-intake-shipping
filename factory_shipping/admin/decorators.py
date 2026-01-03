"""
管理者機能 - デコレータ

管理者権限チェック用のデコレータを提供します。
"""

from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user


def admin_required(f):
    """
    管理者権限が必要な機能に付与するデコレータ

    使用例:
        @admin_required
        def admin_only_view():
            return "管理者のみアクセス可能"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('ログインが必要です', 'error')
            return redirect(url_for('auth.login'))

        if not current_user.is_admin:
            flash('管理者権限が必要です', 'error')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def store_staff_required(f):
    """
    店舗スタッフ権限が必要な機能に付与するデコレータ

    使用例:
        @store_staff_required
        def store_staff_only_view():
            return "店舗スタッフのみアクセス可能"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('ログインが必要です', 'error')
            return redirect(url_for('auth.login'))

        if not current_user.is_store_staff:
            flash('店舗スタッフ権限が必要です', 'error')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function
