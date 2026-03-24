#!/usr/bin/env python3
"""
入荷・ジャーナルデータ取得失敗時の自動リトライ＆通知スクリプト

毎日 23:15 に cron で実行される想定。

処理フロー:
  0. 直近ビジネスデー（昨日）の店舗別取得状況を確認し、未取得店舗があればメール+LINE通知
  1. 過去 RETRY_DAYS 日間のビジネスデーを確認
  2. IntakeItem が 0件 の日付で CSV ファイルが存在すれば hanjow CSV をリトライ
  3. JournalData が 0件 の日付でジャーナルDL→変換→インポートをリトライ
  4. リトライ成功した日付があればリカバリ通知メール+LINEを送信
  5. リトライ後も 3日以上連続失敗が続いていれば警告メール+LINEを送信

ビジネスデー定義: 日曜日・jpholiday 祝日を除く日（月〜土）

ログ: /var/log/factory-shipping/retry-and-notify.log
"""

import sys
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

# Flask アプリを利用するためパスを設定
PROJECT_DIR = '/var/www/html/factory-intake-shipping'
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# .env 読み込み
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, '.env'))
except ImportError:
    pass

import jpholiday

# Flask アプリとモデルをインポート
from factory_shipping import create_app
from factory_shipping.models import IntakeItem, JournalData, Store
from factory_shipping.utils import send_email

# LINE WORKS クライアント（king-req の agent ライブラリを使用）
KING_REQ_DIR = '/var/www/html/king-req'
sys.path.insert(0, KING_REQ_DIR)

# king-req の .env を追加読み込み（LINE WORKS 認証情報）
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(KING_REQ_DIR, '.env'))
except Exception:
    pass

try:
    from agent.lineworks_client import push_message as lw_push
    LW_AVAILABLE = True
except Exception as _lw_e:
    LW_AVAILABLE = False
    _lw_import_error = str(_lw_e)

# ========== 設定 ==========
RETRY_DAYS = 14              # 最大何日前まで遡ってリトライするか
ALERT_CONSECUTIVE_DAYS = 3   # 何日連続失敗でアラートを送るか
# 店舗別取得状況を確認する遡及日数（過去何日分の実績から「期待される店舗」を判断するか）
STORE_MASTER_DAYS = 30

HANJOW_CSV_DIR = Path('/var/www/html/king-req/downloads_hanjow')
AUTO_IMPORT_SCRIPT = os.path.join(PROJECT_DIR, 'scripts/auto_import_hanjow.sh')

KING_REQ_PYTHON = '/var/www/html/king-req/venv-king/bin/python3'
VENV_PYTHON = os.path.join(PROJECT_DIR, 'venv/bin/python')

ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'yoshino.taka5450@gmail.com')
LOG_FILE = '/var/log/factory-shipping/retry-and-notify.log'

STATUS_URL = 'https://factory.kingdrysystem.com/fi/monitoring/import-status'
# ==========================


def log(msg: str):
    """タイムスタンプ付きでログ出力（ファイル・標準出力の両方）"""
    from datetime import datetime
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception as e:
        print(f"[log] ログファイル書き込みエラー: {e}")


def lw_notify(text: str):
    """LINE WORKS へ通知を送る。未設定・エラーの場合はログのみ。"""
    if not LW_AVAILABLE:
        log(f"[LINE] スキップ（クライアント未初期化: {_lw_import_error}）")
        return
    try:
        ok = lw_push(text)
        if ok:
            log("[LINE] 送信完了")
        else:
            log("[LINE] 送信失敗（push_message が False を返しました）")
    except Exception as e:
        log(f"[LINE] 送信エラー: {e}")


def get_last_business_day() -> date:
    """直近ビジネスデー（昨日から遡る）を返す"""
    today = date.today()
    for i in range(1, 14):
        d = today - timedelta(days=i)
        if is_business_day(d):
            return d
    return today - timedelta(days=1)


def get_failing_stores(app) -> dict:
    """
    直近ビジネスデーの店舗別取得状況を確認し、未取得店舗を返す。

    Returns:
        {
            'date': date,
            'intake': [{'code': str, 'name': str}, ...],   # 未取得入荷店舗
            'journal': [str, ...],                          # 未取得仕訳店舗番号
        }
    """
    target = get_last_business_day()
    since = date.today() - timedelta(days=STORE_MASTER_DAYS)

    with app.app_context():
        # ---- 入荷データ（IntakeItem）----
        # Store テーブルのアクティブ店舗を期待セットとして使用
        all_stores = Store.query.filter_by(is_active=True).all()
        # 対象日に取得済みの store_code セット
        intake_done = {
            r[0] for r in
            IntakeItem.query
                .with_entities(IntakeItem.store_code)
                .filter(IntakeItem.intake_date == target)
                .distinct().all()
        }
        failing_intake = [
            {'code': s.store_code, 'name': s.store_name}
            for s in all_stores
            if s.store_code not in intake_done
        ]

        # ---- 仕訳データ（JournalData）----
        # 過去 STORE_MASTER_DAYS 日間に登場した store_no を期待セットとする
        expected_journal = {
            r[0] for r in
            JournalData.query
                .with_entities(JournalData.store_no)
                .filter(JournalData.date >= since)
                .distinct().all()
        }
        journal_done = {
            r[0] for r in
            JournalData.query
                .with_entities(JournalData.store_no)
                .filter(JournalData.date == target)
                .distinct().all()
        }
        failing_journal = sorted(expected_journal - journal_done)

    return {
        'date': target,
        'intake': failing_intake,
        'journal': failing_journal,
    }


def send_store_failure_notify(failing: dict):
    """未取得店舗をメール + LINE WORKS で通知する"""
    target_str = failing['date'].strftime('%Y-%m-%d')
    failing_intake = failing['intake']
    failing_journal = failing['journal']

    subject = f"【警告】夜間バッチ: 未取得店舗あり ({target_str})"

    lines = [
        f"夜間バッチ処理で取得できなかった店舗があります。",
        f"対象日: {target_str}",
        "",
    ]

    if failing_intake:
        lines.append(f"■ 入荷データ（hanjow CSV）未取得店舗 ({len(failing_intake)}店舗):")
        for s in failing_intake:
            lines.append(f"  - {s['code']}: {s['name']}")
    else:
        lines.append("■ 入荷データ（hanjow CSV）: 全店舗取得済み ○")

    lines.append("")

    if failing_journal:
        lines.append(f"■ 仕訳データ（ジャーナル）未取得店舗番号 ({len(failing_journal)}店舗):")
        for sno in failing_journal:
            lines.append(f"  - {sno}")
    else:
        lines.append("■ 仕訳データ（ジャーナル）: 全店舗取得済み ○")

    lines += [
        "",
        f"確認URL: {STATUS_URL}",
        "",
        "このメールは自動送信されています。",
    ]

    body = "\n".join(lines)

    # メール送信
    ok = send_email(ALERT_EMAIL, subject, body)
    if ok:
        log(f"[mail] 未取得店舗通知メール送信完了 → {ALERT_EMAIL}")
    else:
        log("[mail] 未取得店舗通知メール送信失敗")

    # LINE WORKS 送信
    lw_lines = [subject, ""]
    if failing_intake:
        lw_lines.append(f"■ 入荷データ 未取得 ({len(failing_intake)}店舗):")
        for s in failing_intake:
            lw_lines.append(f"  {s['code']}: {s['name']}")
    if failing_journal:
        lw_lines.append(f"■ 仕訳データ 未取得 ({len(failing_journal)}店舗番号):")
        for sno in failing_journal:
            lw_lines.append(f"  {sno}")
    lw_lines += ["", f"確認: {STATUS_URL}"]
    lw_notify("\n".join(lw_lines))


def is_business_day(d: date) -> bool:
    """日曜日・祝日を除くビジネスデーかどうかを判定する"""
    if d.weekday() == 6:  # 日曜日
        return False
    if jpholiday.is_holiday(d):
        return False
    return True


def get_missing_hanjow_dates(app) -> list:
    """
    過去 RETRY_DAYS 日間のビジネスデーのうち、
    IntakeItem が 0件 の日付リストを返す（古い順）
    """
    today = date.today()
    missing = []
    with app.app_context():
        for i in range(RETRY_DAYS, 0, -1):  # 古い日から順に
            target = today - timedelta(days=i)
            if not is_business_day(target):
                continue
            count = IntakeItem.query.filter(
                IntakeItem.intake_date == target
            ).count()
            if count == 0:
                missing.append(target)
    return missing


def get_missing_journal_dates(app) -> list:
    """
    過去 RETRY_DAYS 日間のビジネスデーのうち、
    JournalData が 0件 の日付リストを返す（古い順）
    """
    today = date.today()
    missing = []
    with app.app_context():
        for i in range(RETRY_DAYS, 0, -1):  # 古い日から順に
            target = today - timedelta(days=i)
            if not is_business_day(target):
                continue
            count = JournalData.query.filter(
                JournalData.date == target
            ).count()
            if count == 0:
                missing.append(target)
    return missing


def retry_hanjow(target_date: date) -> bool:
    """
    指定日付の hanjow CSV インポートをリトライする。
    CSV ファイルが存在する場合のみ実行。

    Returns:
        True: インポート成功 / False: スキップまたは失敗
    """
    date_str = target_date.strftime('%Y-%m-%d')
    csv_file = HANJOW_CSV_DIR / f'hanjow_{target_date.strftime("%Y%m%d")}.csv'

    if not csv_file.exists():
        log(f"  [hanjow] CSVファイルなし: {date_str} → スキップ")
        return False

    log(f"  [hanjow] リトライ実行: {date_str}")
    try:
        result = subprocess.run(
            [AUTO_IMPORT_SCRIPT, date_str],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            log(f"  [hanjow] リトライ成功: {date_str}")
            return True
        else:
            log(f"  [hanjow] リトライ失敗: {date_str} (終了コード: {result.returncode})")
            if result.stderr:
                log(f"  [hanjow] エラー出力: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        log(f"  [hanjow] リトライタイムアウト: {date_str}")
        return False
    except Exception as e:
        log(f"  [hanjow] リトライ例外: {date_str} - {e}")
        return False


def retry_journal(target_date: date) -> bool:
    """
    指定日付のジャーナルデータをダウンロード→変換→インポートしてリトライする。

    Returns:
        True: インポート成功 / False: 失敗
    """
    date_str = target_date.strftime('%Y-%m-%d')
    log(f"  [journal] リトライ実行: {date_str}")

    # Step 1: ダウンロード
    try:
        r1 = subprocess.run(
            [KING_REQ_PYTHON, os.path.join(KING_REQ_DIR, 'hanjow_journal_downloader.py'),
             '--date', date_str],
            cwd=KING_REQ_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )
        if r1.returncode != 0:
            log(f"  [journal] ダウンロード失敗: {date_str}")
            return False
    except subprocess.TimeoutExpired:
        log(f"  [journal] ダウンロードタイムアウト: {date_str}")
        return False
    except Exception as e:
        log(f"  [journal] ダウンロード例外: {date_str} - {e}")
        return False

    # Step 2: .txt → CSV 変換
    try:
        r2 = subprocess.run(
            [KING_REQ_PYTHON, os.path.join(KING_REQ_DIR, 'extract_journal_data.py'), date_str],
            cwd=KING_REQ_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        if r2.returncode != 0:
            log(f"  [journal] CSV変換失敗: {date_str}")
            return False
    except subprocess.TimeoutExpired:
        log(f"  [journal] CSV変換タイムアウト: {date_str}")
        return False
    except Exception as e:
        log(f"  [journal] CSV変換例外: {date_str} - {e}")
        return False

    # Step 3: DB インポート
    try:
        r3 = subprocess.run(
            [VENV_PYTHON, os.path.join(PROJECT_DIR, 'run.py'),
             'import-journal', '--date', date_str],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )
        if r3.returncode == 0:
            log(f"  [journal] リトライ成功: {date_str}")
            return True
        else:
            log(f"  [journal] DBインポート失敗: {date_str} (終了コード: {r3.returncode})")
            return False
    except subprocess.TimeoutExpired:
        log(f"  [journal] DBインポートタイムアウト: {date_str}")
        return False
    except Exception as e:
        log(f"  [journal] DBインポート例外: {date_str} - {e}")
        return False


def count_consecutive_failures(app, model_class, date_field) -> tuple:
    """
    昨日から遡って連続失敗ビジネスデー数を返す。
    非ビジネスデー（日曜・祝日）はスキップ（カウントしない）。

    Returns:
        (連続失敗日数: int, 最終成功日: date | None)
    """
    today = date.today()
    count = 0
    last_success = None
    with app.app_context():
        for i in range(1, 60):  # 最大60日前まで確認
            target = today - timedelta(days=i)
            if not is_business_day(target):
                continue
            n = model_class.query.filter(date_field == target).count()
            if n == 0:
                count += 1
            else:
                last_success = target
                break
    return count, last_success


def send_failure_alert(hanjow_failures: int, hanjow_last_success,
                       journal_failures: int, journal_last_success):
    """連続失敗の警告メールを送信する"""
    max_failures = max(hanjow_failures, journal_failures)
    subject = f"【警告】入荷データ取得失敗 {max_failures}日連続 (factory-intake-shipping)"

    lines = [
        f"入荷管理システムのデータ取得が連続で失敗しています。",
        f"",
        f"■ hanjow CSVデータ（入荷台帳）",
    ]
    if hanjow_failures >= ALERT_CONSECUTIVE_DAYS:
        last = hanjow_last_success.strftime('%Y-%m-%d') if hanjow_last_success else "不明"
        lines.append(f"  状態: {hanjow_failures}日連続失敗")
        lines.append(f"  最終成功日: {last}")
    else:
        lines.append(f"  状態: 正常（直近の連続失敗なし）")

    lines += [
        f"",
        f"■ ジャーナルデータ",
    ]
    if journal_failures >= ALERT_CONSECUTIVE_DAYS:
        last = journal_last_success.strftime('%Y-%m-%d') if journal_last_success else "不明"
        lines.append(f"  状態: {journal_failures}日連続失敗")
        lines.append(f"  最終成功日: {last}")
    else:
        lines.append(f"  状態: 正常（直近の連続失敗なし）")

    lines += [
        f"",
        f"確認URL: {STATUS_URL}",
        f"",
        f"このメールは自動送信されています。",
        f"毎日23:30のバッチ処理から送信（リトライ後も失敗が継続している場合）。",
    ]

    body = "\n".join(lines)
    ok = send_email(ALERT_EMAIL, subject, body)
    if ok:
        log(f"[mail] 警告メール送信完了 → {ALERT_EMAIL}")
    else:
        log(f"[mail] 警告メール送信失敗")

    # LINE WORKS 通知
    lw_summary = [subject]
    if hanjow_failures >= ALERT_CONSECUTIVE_DAYS:
        last = hanjow_last_success.strftime('%Y-%m-%d') if hanjow_last_success else "不明"
        lw_summary.append(f"入荷台帳: {hanjow_failures}日連続失敗（最終成功: {last}）")
    if journal_failures >= ALERT_CONSECUTIVE_DAYS:
        last = journal_last_success.strftime('%Y-%m-%d') if journal_last_success else "不明"
        lw_summary.append(f"仕訳データ: {journal_failures}日連続失敗（最終成功: {last}）")
    lw_summary.append(f"確認: {STATUS_URL}")
    lw_notify("\n".join(lw_summary))


def send_recovery_notification(recovered_hanjow: list, recovered_journal: list):
    """リカバリ成功の通知メールを送信する"""
    subject = "【復旧】入荷データ取得が再開しました (factory-intake-shipping)"

    lines = ["リトライによりデータ取得が復旧しました。", ""]

    if recovered_hanjow:
        dates_str = ", ".join(d.strftime('%Y-%m-%d') for d in recovered_hanjow)
        lines.append(f"■ hanjow CSVデータ（入荷台帳）: {len(recovered_hanjow)}日分を取得")
        lines.append(f"  対象日: {dates_str}")
        lines.append("")

    if recovered_journal:
        dates_str = ", ".join(d.strftime('%Y-%m-%d') for d in recovered_journal)
        lines.append(f"■ ジャーナルデータ: {len(recovered_journal)}日分を取得")
        lines.append(f"  対象日: {dates_str}")
        lines.append("")

    lines += [
        f"確認URL: {STATUS_URL}",
        f"",
        f"このメールは自動送信されています。",
    ]

    body = "\n".join(lines)
    ok = send_email(ALERT_EMAIL, subject, body)
    if ok:
        log(f"[mail] 復旧通知メール送信完了 → {ALERT_EMAIL}")
    else:
        log(f"[mail] 復旧通知メール送信失敗")

    # LINE WORKS 通知
    lw_summary = [subject]
    if recovered_hanjow:
        dates_str = ", ".join(d.strftime('%Y-%m-%d') for d in recovered_hanjow)
        lw_summary.append(f"入荷台帳: {len(recovered_hanjow)}日分復旧 ({dates_str})")
    if recovered_journal:
        dates_str = ", ".join(d.strftime('%Y-%m-%d') for d in recovered_journal)
        lw_summary.append(f"仕訳データ: {len(recovered_journal)}日分復旧 ({dates_str})")
    lw_summary.append(f"確認: {STATUS_URL}")
    lw_notify("\n".join(lw_summary))


def main():
    log("=" * 50)
    log("入荷データ自動リトライ＆通知 開始")
    log("=" * 50)

    if LW_AVAILABLE:
        log("[LINE] LINE WORKS クライアント: 初期化済み")
    else:
        log(f"[LINE] LINE WORKS クライアント: 利用不可（{_lw_import_error}）")

    app = create_app()

    # ---- 0. 直近ビジネスデーの店舗別取得状況チェック ----
    log("[step0] 直近ビジネスデーの店舗別取得状況を確認中...")
    try:
        failing = get_failing_stores(app)
        target_str = failing['date'].strftime('%Y-%m-%d')
        log(f"  対象日: {target_str}")
        log(f"  入荷データ 未取得店舗: {len(failing['intake'])}店舗")
        for s in failing['intake']:
            log(f"    - {s['code']}: {s['name']}")
        log(f"  仕訳データ 未取得店舗番号: {len(failing['journal'])}店舗")
        for sno in failing['journal']:
            log(f"    - {sno}")

        if failing['intake'] or failing['journal']:
            log("[step0] 未取得店舗あり → メール+LINE通知送信...")
            send_store_failure_notify(failing)
        else:
            log("[step0] 全店舗取得済み（通知スキップ）")
    except Exception as e:
        log(f"[step0] 店舗別チェックでエラー: {e}")

    # ---- 1. リトライ前の欠損日を取得 ----
    log("[step1] 欠損日を確認中...")
    missing_hanjow = get_missing_hanjow_dates(app)
    missing_journal = get_missing_journal_dates(app)

    log(f"  hanjow 欠損ビジネスデー: {len(missing_hanjow)}日")
    for d in missing_hanjow:
        log(f"    - {d.strftime('%Y-%m-%d')}")

    log(f"  journal 欠損ビジネスデー: {len(missing_journal)}日")
    for d in missing_journal:
        log(f"    - {d.strftime('%Y-%m-%d')}")

    # ---- 2. hanjow CSV リトライ ----
    log("[step2] hanjow CSVリトライ開始...")
    recovered_hanjow = []
    for d in missing_hanjow:
        if retry_hanjow(d):
            recovered_hanjow.append(d)

    # ---- 3. ジャーナルデータ リトライ ----
    log("[step3] ジャーナルデータリトライ開始...")
    recovered_journal = []
    for d in missing_journal:
        if retry_journal(d):
            recovered_journal.append(d)

    log(f"  hanjow リトライ成功: {len(recovered_hanjow)}日 / 試行: {len(missing_hanjow)}日")
    log(f"  journal リトライ成功: {len(recovered_journal)}日 / 試行: {len(missing_journal)}日")

    # ---- 4. リカバリ通知 ----
    if recovered_hanjow or recovered_journal:
        log("[step4] リカバリ通知メール+LINE送信...")
        send_recovery_notification(recovered_hanjow, recovered_journal)
    else:
        log("[step4] リカバリなし（通知スキップ）")

    # ---- 5. 連続失敗チェック（リトライ後のDB状態で再確認） ----
    log("[step5] 連続失敗日数を確認中...")
    hanjow_failures, hanjow_last_success = count_consecutive_failures(
        app, IntakeItem, IntakeItem.intake_date
    )
    journal_failures, journal_last_success = count_consecutive_failures(
        app, JournalData, JournalData.date
    )

    log(f"  hanjow 連続失敗: {hanjow_failures}日（最終成功: {hanjow_last_success}）")
    log(f"  journal 連続失敗: {journal_failures}日（最終成功: {journal_last_success}）")

    # ---- 6. 警告メール送信 ----
    if hanjow_failures >= ALERT_CONSECUTIVE_DAYS or journal_failures >= ALERT_CONSECUTIVE_DAYS:
        log("[step6] 警告メール+LINE送信...")
        send_failure_alert(hanjow_failures, hanjow_last_success,
                           journal_failures, journal_last_success)
    else:
        log("[step6] 連続失敗なし（警告スキップ）")

    log("=" * 50)
    log("入荷データ自動リトライ＆通知 完了")
    log("=" * 50)


if __name__ == '__main__':
    main()
