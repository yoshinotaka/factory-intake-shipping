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
from factory_shipping.utils import now_jst, today_jst
from pathlib import Path
from dotenv import load_dotenv

# .env ファイルを読み込む（プロジェクトルートを明示的に指定）
project_root = Path(__file__).parent.absolute()
env_file = project_root / '.env'
load_dotenv(dotenv_path=env_file)

from factory_shipping import create_app
from factory_shipping.extensions import db, socketio
from factory_shipping.models import User, Store, JournalData
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
            dt = now_jst()

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


def import_journal(target_date=None):
    """
    ジャーナルCSVファイルを取り込む

    Args:
        target_date (str, optional): 対象日付 (YYYY-MM-DD形式)
                                     指定しない場合は今日の日付を使用

    例:
        python run.py import-journal --date 2025-12-22
        python run.py import-journal  # 今日の日付

    cron 設定例（毎日 23:00 実行）:
        0 23 * * * cd /var/www/html/factory-intake-shipping && /var/www/html/factory-intake-shipping/venv/bin/python run.py import-journal >> /var/log/factory-shipping/import-journal.log 2>&1
    """
    import csv
    import codecs

    with app.app_context():
        # 対象日付を決定
        if target_date:
            try:
                dt = datetime.strptime(target_date, '%Y-%m-%d')
            except ValueError:
                print(f"エラー: 日付の形式が正しくありません: {target_date}")
                print("正しい形式: YYYY-MM-DD (例: 2025-12-22)")
                sys.exit(1)
        else:
            dt = now_jst()

        # ファイル名を生成
        date_str = dt.strftime('%Y%m%d')
        csv_dir = Path('/var/www/html/king-req/journal_data_csv')

        # 2種類のファイル名パターンを試す
        csv_files = [
            csv_dir / f'journal_data_{date_str}.csv',
            csv_dir / f'customer_data_from_journal_{date_str}.csv'
        ]

        print("=" * 60)
        print("  ジャーナルCSV 取り込み処理")
        print("=" * 60)
        print(f"  対象日付: {dt.strftime('%Y-%m-%d')}")
        print("=" * 60)
        print()

        # ファイル存在チェック
        csv_file = None
        for f in csv_files:
            if f.exists():
                csv_file = f
                break

        if not csv_file:
            print(f"エラー: CSV ファイルが見つかりません")
            print(f"試したパス:")
            for f in csv_files:
                print(f"  - {f}")
            sys.exit(1)

        print(f"  CSV ファイル: {csv_file}")
        print()

        try:
            # CSV 取り込み実行
            total_rows = 0
            created = 0
            skipped = 0
            errors = 0
            imported_at = now_jst()

            with codecs.open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    total_rows += 1

                    try:
                        # 日付をパース
                        try:
                            row_date = datetime.strptime(row['date'], '%Y-%m-%d').date()
                        except ValueError:
                            print(f"警告: 日付の形式が不正です (行{total_rows}): {row['date']}")
                            errors += 1
                            continue

                        # 既存レコードをチェック（重複防止）
                        existing = JournalData.query.filter_by(
                            date=row_date,
                            store_no=row['store_no'],
                            slip_no=row['slip_no'],
                            customer_name=row['customer_name']
                        ).first()

                        if existing:
                            skipped += 1
                            continue

                        # 新規レコード作成
                        journal = JournalData(
                            date=row_date,
                            store_no=row['store_no'],
                            slip_no=row['slip_no'],
                            customer_name=row['customer_name'],
                            phone=row.get('phone', ''),
                            slip_content=row.get('slip_content', ''),
                            imported_at=imported_at
                        )

                        db.session.add(journal)
                        created += 1

                        # 100件ごとにコミット
                        if created % 100 == 0:
                            db.session.commit()
                            print(f"  処理中... {total_rows} 行 (新規: {created}, スキップ: {skipped})")

                    except Exception as e:
                        errors += 1
                        print(f"エラー (行{total_rows}): {e}")
                        continue

                # 最終コミット
                db.session.commit()

            # 結果表示
            print()
            print("=" * 60)
            print("  取り込み結果")
            print("=" * 60)
            print(f"  総行数:     {total_rows} 行")
            print(f"  新規作成:   {created} 件")
            print(f"  スキップ:   {skipped} 件（重複）")
            print(f"  エラー:     {errors} 件")
            print("=" * 60)

            if errors > 0:
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


def import_returns(argv):
    """
    返却日指定 CSV を取り込み、返却された品目の intake_items.returned_at を設定する

    例:
        python run.py import-returns                     # 直近7日分（昨日まで。毎朝の cron はこれ）
        python run.py import-returns --days 14
        python run.py import-returns --date 2026-09-20   # 1日分
        python run.py import-returns --from 2021-01-05 --to 2026-09-20   # 過去分の一括反映
        python run.py import-returns --all               # 手元にある返却 CSV をすべて
        python run.py import-returns --date 2026-09-20 --dry-run          # DB を書き換えずに件数だけ見る

    何度流しても結果は同じ（新しい返却日時のときだけ上書きする）。
    詳細は factory_shipping/intake/returns.py を参照。
    """
    import argparse
    import logging
    from datetime import timedelta
    from factory_shipping.intake.returns import (
        import_return_csvs, list_return_csv_dates, recent_dates,
    )

    parser = argparse.ArgumentParser(prog='run.py import-returns')
    parser.add_argument('--date', help='返却日 (YYYY-MM-DD)')
    parser.add_argument('--from', dest='from_date', help='返却日の開始 (YYYY-MM-DD)')
    parser.add_argument('--to', dest='to_date', help='返却日の終了 (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=7, help='昨日から何日さかのぼるか（既定 7）')
    parser.add_argument('--all', action='store_true', help='手元にある返却 CSV をすべて取り込む')
    parser.add_argument('--dry-run', action='store_true', help='DB を書き換えずに件数だけ出す')
    args = parser.parse_args(argv)

    # 一括反映では数百万行の SQL が出てしまうので、SQL のログは止める
    logging.getLogger('sqlalchemy.engine.Engine').disabled = True
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(message)s')

    def parse(value):
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            parser.error(f'日付の形式が正しくありません: {value}（YYYY-MM-DD）')

    with app.app_context():
        if args.all:
            dates = list_return_csv_dates()
        elif args.date:
            dates = [parse(args.date)]
        elif args.from_date or args.to_date:
            if not (args.from_date and args.to_date):
                parser.error('--from と --to は両方指定してください')
            start, end = parse(args.from_date), parse(args.to_date)
            dates = [start + timedelta(days=n) for n in range((end - start).days + 1)]
        else:
            dates = recent_dates(args.days)

        if not dates:
            print('対象の返却日がありません')
            return

        print("=" * 60)
        print("  返却日指定 CSV 取り込み" + ("（dry-run: DB は書き換えない）" if args.dry_run else ""))
        print(f"  返却日: {dates[0].isoformat()} 〜 {dates[-1].isoformat()}（{len(dates)} 日）")
        print("=" * 60)

        try:
            by_year = import_return_csvs(dates, dry_run=args.dry_run)
        except Exception as e:
            print(f"エラー: 返却 CSV の取り込み中に予期しない問題が発生しました: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        print()
        print("  返却年  ファイル  無し  行数     一致(タグ有/空)       不一致(タグ有/空)  範囲外    取消  更新     既反映")
        for key in sorted(k for k in by_year if k != 'total') + ['total']:
            s = by_year[key]
            print(f"  {key:<6} {s['files']:>8} {s['missing']:>5} {s['rows']:>8}"
                  f"  {s['matched_tagged']:>9}/{s['matched_untagged']:<9}"
                  f"  {s['unmatched_tagged']:>7}/{s['unmatched_untagged']:<9}"
                  f"  {s['out_of_range']:>8} {s['cancelled']:>5}"
                  f"  {s['items_updated']:>7} {s['items_unchanged']:>7}")
        total = by_year['total']
        print()
        print("  範囲外 = 預り日が intake_items の最古の預り日より前（突き合わせ対象外）")
        if total['errors']:
            print(f"  読めない行: {total['errors']} 行（ログを確認してください）")
        print("取り込みが完了しました。" if not args.dry_run else "dry-run のため DB は変更していません。")


def run_historical(command, argv):
    """
    過去分（預り日 2021-01-04〜2025-09-30）の取り込みと埋め戻し。詳細は factory_shipping/intake/historical.py

    例:
        python run.py import-historical --date 2022-06-01 --dry-run      # 1 日分（件数だけ）
        python run.py import-historical --from 2022-06-01 --to 2022-06-30
        python run.py import-historical --all                            # 手元の CSV すべて（2025-09-30 まで）
        python run.py fill-returned-from-intake --all                    # 返却 CSV の反映（import-returns --all）のあとに流す
        python run.py backfill-customer-code --from 2025-10-01 --to 2026-09-21   # 既存品目に顧客コード（hanjow_*.csv から）

    どれも何度流しても結果は同じ。
    """
    import argparse
    import logging
    from datetime import timedelta
    from factory_shipping.intake import historical

    parser = argparse.ArgumentParser(prog=f'run.py {command}')
    parser.add_argument('--date', help='預り日 (YYYY-MM-DD)')
    parser.add_argument('--from', dest='from_date', help='預り日の開始 (YYYY-MM-DD)')
    parser.add_argument('--to', dest='to_date', help='預り日の終了 (YYYY-MM-DD)')
    parser.add_argument('--all', action='store_true', help='対象の CSV をすべて')
    parser.add_argument('--dry-run', action='store_true', help='DB を書き換えずに件数だけ出す')
    args = parser.parse_args(argv)

    logging.getLogger('sqlalchemy.engine.Engine').disabled = True
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(message)s')

    def parse(value):
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            parser.error(f'日付の形式が正しくありません: {value}（YYYY-MM-DD）')

    if args.date:
        dates = [parse(args.date)]
    elif args.from_date or args.to_date:
        if not (args.from_date and args.to_date):
            parser.error('--from と --to は両方指定してください')
        start, end = parse(args.from_date), parse(args.to_date)
        dates = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    elif args.all:
        if command == 'backfill-customer-code':
            dates = sorted(datetime.strptime(p.stem[len('hanjow_'):], '%Y%m%d').date()
                           for p in historical.HANJOW_CSV_DIR.glob('hanjow_*.csv')
                           if p.stem[len('hanjow_'):].isdigit())
        else:
            dates = historical.list_intake_csv_dates()
    else:
        parser.error('--date / --from と --to / --all のどれかを指定してください')

    if command == 'import-historical':
        run, title = historical.import_intake_csvs, '過去分の預り日 CSV 取り込み'
        columns = [('files', 'ファイル'), ('missing', '無し'), ('rows', '行数'), ('cancelled', '取消'),
                   ('created', '新規'), ('existing', '既存'), ('errors', '読めない')]
    elif command == 'fill-returned-from-intake':
        run, title = historical.fill_returned_from_intake_csvs, '預り日 CSV の返却日時列で returned_at を補う'
        columns = [('files', 'ファイル'), ('with_value', '返却日時あり'), ('filled', '埋めた'),
                   ('already', '返却CSVで反映済'), ('not_found', '品目なし')]
    else:
        run, title = historical.backfill_customer_codes, '既存品目に顧客コードを入れる（hanjow_*.csv・預り日 CSV）'
        columns = [('files', 'ファイル'), ('missing', '無し'), ('rows', '行数'),
                   ('items_with_code', 'コード判明'), ('filled', '埋めた'), ('errors', '読めない')]

    print("=" * 60)
    print(f"  {title}" + ("（dry-run: DB は書き換えない）" if args.dry_run else ""))
    print(f"  預り日: {dates[0].isoformat()} 〜 {dates[-1].isoformat()}（{len(dates)} 日）")
    print("=" * 60)

    started = datetime.now()
    with app.app_context():
        try:
            by_year = run(dates, dry_run=args.dry_run)
        except Exception as e:
            print(f"エラー: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print()
    print('  年     ' + ''.join(f'{label:>12}' for _, label in columns))
    for key in sorted(k for k in by_year if k != 'total') + ['total']:
        print(f'  {key:<6} ' + ''.join(f'{by_year[key][name]:>12}' for name, _ in columns))
    print(f"\n  所要時間: {(datetime.now() - started).total_seconds():.0f} 秒")
    print("完了しました。" if not args.dry_run else "dry-run のため DB は変更していません。")


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
        elif command == 'import-journal':
            # --date オプションの処理
            target_date = None
            if len(sys.argv) > 2 and sys.argv[2] == '--date' and len(sys.argv) > 3:
                target_date = sys.argv[3]
            import_journal(target_date)
        elif command == 'import-returns':
            import_returns(sys.argv[2:])
        elif command in ('import-historical', 'fill-returned-from-intake', 'backfill-customer-code'):
            run_historical(command, sys.argv[2:])
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
            print("  import-journal       - ジャーナル CSV 取り込み（今日の日付）")
            print("  import-journal --date YYYY-MM-DD - 指定日付の CSV を取り込み")
            print("  import-returns       - 返却日指定 CSV 取り込み（直近7日分）")
            print("  import-returns --date YYYY-MM-DD / --from D --to D / --all [--dry-run]")
            print("  import-historical          - 過去分（2021-01〜2025-09）の預り日 CSV を取り込む")
            print("  fill-returned-from-intake  - 預り日 CSV の返却日時列で returned_at を補う（import-returns の後）")
            print("  backfill-customer-code     - 既存品目に顧客コードを入れる（hanjow_*.csv から）")
            print("    共通: --date YYYY-MM-DD / --from D --to D / --all [--dry-run]")
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
        print("  WebSocket: 有効")
        print("=" * 50)
        print()

        socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
