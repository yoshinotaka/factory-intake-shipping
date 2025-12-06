#!/usr/bin/env python3
"""
新・出荷システム - エントリポイント

開発サーバーの起動やデータベース初期化などに使用します。
本番環境では Gunicorn を使用するため、このファイルは直接実行しません。

使い方:
    # 開発サーバー起動
    python run.py

    # デバッグモードで起動
    FLASK_DEBUG=1 python run.py

    # データベース初期化（テーブル作成）
    python run.py init-db

    # サンプルデータ投入
    python run.py seed-db
"""

import os
import sys
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv

# .env ファイルを読み込む
load_dotenv()

from factory_shipping import create_app
from factory_shipping.extensions import db
from factory_shipping.models import User, Store
from factory_shipping.intake.services import import_hanjow_csv

# アプリケーションインスタンスを作成
app = create_app()


def init_db():
    """データベースを初期化（テーブル作成）"""
    with app.app_context():
        print("データベースを初期化しています...")
        db.create_all()
        print("テーブルの作成が完了しました")


def seed_db():
    """サンプルデータを投入"""
    with app.app_context():
        print("サンプルデータを投入しています...")

        # 管理者ユーザーを作成
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('admin123')  # 本番環境では必ず変更すること
            db.session.add(admin)
            print("  - 管理者ユーザー (admin/admin123) を作成しました")

        # テストユーザーを作成
        test_user = User.query.filter_by(username='testuser').first()
        if not test_user:
            test_user = User(
                username='testuser',
                email='test@example.com',
                is_admin=False
            )
            test_user.set_password('test123')
            db.session.add(test_user)
            print("  - テストユーザー (testuser/test123) を作成しました")

        # サンプル店舗を作成
        stores_data = [
            ('S001', '東京本店'),
            ('S002', '大阪支店'),
            ('S003', '名古屋支店'),
        ]

        for store_code, store_name in stores_data:
            store = Store.query.filter_by(store_code=store_code).first()
            if not store:
                store = Store(store_code=store_code, store_name=store_name)
                db.session.add(store)
                print(f"  - 店舗 ({store_code}: {store_name}) を作成しました")

        db.session.commit()
        print("サンプルデータの投入が完了しました")


def drop_db():
    """データベースを削除（開発用）"""
    with app.app_context():
        print("警告: すべてのテーブルを削除します")
        response = input("続行しますか? (yes/no): ")
        if response.lower() == 'yes':
            db.drop_all()
            print("テーブルの削除が完了しました")
        else:
            print("キャンセルしました")


def list_users():
    """ユーザー一覧を表示"""
    with app.app_context():
        users = User.query.order_by(User.id).all()
        
        if not users:
            print("ユーザーが見つかりませんでした。")
            return
        
        print("=" * 80)
        print("  ユーザー一覧")
        print("=" * 80)
        print(f"{'ID':<5} {'ユーザー名':<20} {'メールアドレス':<30} {'管理者':<8} {'有効':<8} {'作成日時':<20}")
        print("-" * 80)
        
        for user in users:
            admin_status = "○" if user.is_admin else "-"
            active_status = "○" if user.is_active else "×"
            created_at_str = user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else "-"
            
            print(f"{user.id:<5} {user.username:<20} {user.email:<30} {admin_status:<8} {active_status:<8} {created_at_str:<20}")
        
        print("=" * 80)
        print(f"合計: {len(users)} ユーザー")
        print("=" * 80)


def import_hanjow(target_date=None):
    """
    hanjow CSV ファイルを取り込む

    Args:
        target_date (str, optional): 対象日付 (YYYY-MM-DD形式)
                                     指定しない場合は今日の日付を使用

    例:
        python run.py import-hanjow --date 2025-11-11
        python run.py import-hanjow  # 今日の日付

    cron 設定例（毎日 22:30 実行）:
        30 22 * * * cd /var/www/html/factory-intake-shipping && /var/www/html/factory-intake-shipping/venv/bin/python run.py import-hanjow >> /var/log/factory-shipping/import-hanjow.log 2>&1
    """
    with app.app_context():
        # 対象日付を決定
        if target_date:
            try:
                dt = datetime.strptime(target_date, '%Y-%m-%d')
            except ValueError:
                print(f"エラー: 日付の形式が正しくありません: {target_date}")
                print("正しい形式: YYYY-MM-DD (例: 2025-11-11)")
                sys.exit(1)
        else:
            dt = datetime.now()

        # ファイル名を生成
        date_str = dt.strftime('%Y%m%d')
        csv_dir = Path('/var/www/html/king-req/downloads_hanjow')
        csv_file = csv_dir / f'hanjow_{date_str}.csv'

        print("=" * 60)
        print("  hanjow CSV 取り込み処理")
        print("=" * 60)
        print(f"  対象日付: {dt.strftime('%Y-%m-%d')}")
        print(f"  CSV ファイル: {csv_file}")
        print("=" * 60)
        print()

        # ファイル存在チェック
        if not csv_file.exists():
            print(f"エラー: CSV ファイルが見つかりません")
            print(f"パス: {csv_file}")
            sys.exit(1)

        try:
            # CSV 取り込み実行
            result = import_hanjow_csv(str(csv_file))

            # 結果表示
            print()
            print("=" * 60)
            print("  取り込み結果")
            print("=" * 60)
            print(f"  総行数:     {result['total_rows']} 行")
            print(f"  新規作成:   {result['created']} 件")
            print(f"  スキップ:   {result['skipped']} 件（重複）")
            print(f"  エラー:     {result['errors']} 件")
            print("=" * 60)

            if result['errors'] > 0:
                print()
                print("警告: エラーが発生しました。ログを確認してください。")
                sys.exit(1)
            else:
                print()
                print("取り込みが正常に完了しました。")

        except Exception as e:
            print()
            print(f"エラー: CSV 取り込み中に予期しない問題が発生しました")
            print(f"詳細: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


@app.cli.command()
def init_db_command():
    """データベース初期化コマンド"""
    init_db()


@app.cli.command()
def seed_db_command():
    """サンプルデータ投入コマンド"""
    seed_db()


@app.cli.command()
def drop_db_command():
    """データベース削除コマンド（開発用）"""
    drop_db()


if __name__ == '__main__':
    # コマンドライン引数を確認
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'init-db':
            init_db()
        elif command == 'seed-db':
            seed_db()
        elif command == 'drop-db':
            drop_db()
        elif command == 'import-hanjow':
            # --date オプションの処理
            target_date = None
            if len(sys.argv) > 2 and sys.argv[2] == '--date' and len(sys.argv) > 3:
                target_date = sys.argv[3]
            import_hanjow(target_date)
        elif command == 'list-users':
            list_users()
        else:
            print(f"不明なコマンド: {command}")
            print()
            print("利用可能なコマンド:")
            print("  init-db              - データベース初期化")
            print("  seed-db              - サンプルデータ投入")
            print("  drop-db              - データベース削除")
            print("  list-users           - ユーザー一覧を表示")
            print("  import-hanjow        - hanjow CSV 取り込み（今日の日付）")
            print("  import-hanjow --date YYYY-MM-DD  - 指定日付の CSV を取り込み")
            sys.exit(1)
    else:
        # 開発サーバーを起動
        host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
        port = int(os.environ.get('FLASK_RUN_PORT', 5000))
        debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'yes']

        print("=" * 50)
        print("  新・出荷システム 開発サーバー")
        print("=" * 50)
        print(f"  URL: http://{host}:{port}/fi/")
        print(f"  環境: {os.environ.get('FLASK_ENV', 'development')}")
        print(f"  デバッグ: {debug}")
        print("=" * 50)
        print()

        app.run(host=host, port=port, debug=debug)
