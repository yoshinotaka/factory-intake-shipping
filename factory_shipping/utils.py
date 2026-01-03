"""
新・出荷システム - ユーティリティ関数

プロジェクト全体で使用する共通関数を定義します。
"""

from datetime import datetime

try:
    # Python 3.9+ では zoneinfo を使用
    from zoneinfo import ZoneInfo
    JST = ZoneInfo('Asia/Tokyo')
except ImportError:
    # Python 3.8 以下では pytz を使用（必要に応じてインストール）
    try:
        import pytz
        JST = pytz.timezone('Asia/Tokyo')
    except ImportError:
        # フォールバック: タイムゾーン情報なし（サーバーのローカル時間を使用）
        JST = None


def now_jst():
    """
    現在の日本時間（JST）を取得する
    
    Returns:
        datetime: 日本時間の現在時刻（タイムゾーン情報なし、naive datetime）
    """
    if JST:
        # タイムゾーン情報付きの現在時刻を取得
        dt_with_tz = datetime.now(JST)
        # タイムゾーン情報を削除してnaive datetimeに変換（データベース保存用）
        return dt_with_tz.replace(tzinfo=None)
    else:
        # フォールバック: サーバーのローカル時間を使用
        # サーバーがJSTに設定されていることを前提とする
        return datetime.now()


def today_jst():
    """
    今日の日本時間の日付を取得する

    Returns:
        date: 日本時間の今日の日付
    """
    return now_jst().date()


def get_next_history_number(store_code, intake_date, tag_number):
    """
    指定された店舗コード + 預かり日 + タグ番号の次の履歴番号を取得する

    Args:
        store_code (str): 店舗コード
        intake_date (date): 預かり日
        tag_number (str): タグ番号

    Returns:
        int: 次の履歴番号（1から始まる連番）
    """
    from factory_shipping.models import ShipmentLog
    from factory_shipping.extensions import db

    # 同じ店舗コード + 預かり日 + タグ番号の最大履歴番号を取得
    max_history = db.session.query(db.func.max(ShipmentLog.history_number)).filter(
        ShipmentLog.store_code == store_code,
        ShipmentLog.intake_date == intake_date,
        ShipmentLog.tag_number == tag_number
    ).scalar()

    # 最大値がNULLの場合は1、そうでなければ+1
    return 1 if max_history is None else max_history + 1


def normalize_tag_number_for_search(tag_number: str) -> list:
    """
    タグ番号を複数の形式に正規化して検索用のリストを返す
    
    例: "0-001" → ["0-001", "00-001", "0001", "00001"]
    
    Args:
        tag_number (str): タグ番号（例: "0-001"）
    
    Returns:
        list: 検索用のタグ番号リスト
    """
    if not tag_number:
        return []
    
    # ハイフンを除去して数字部分のみ取得
    digits_only = tag_number.replace('-', '').strip()
    
    if not digits_only or not digits_only.isdigit():
        # 数字でない場合は元の形式のみ
        return [tag_number]
    
    # 複数の形式を生成
    search_patterns = []
    
    # 1. 元の形式
    search_patterns.append(tag_number)
    
    # 2. ハイフンなし形式
    if '-' in tag_number:
        search_patterns.append(digits_only)
    
    # 3. 左側を2桁にパディングした形式（例: "0-001" → "00-001"）
    if '-' in tag_number:
        parts = tag_number.split('-')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            left_padded = parts[0].zfill(2)
            search_patterns.append(f"{left_padded}-{parts[1]}")
            # 右側の先頭0を除去した形式（例: "0-001" → "0-1"）
            right_no_leading_zero = parts[1].lstrip('0') or '0'
            search_patterns.append(f"{parts[0]}-{right_no_leading_zero}")
            search_patterns.append(f"{left_padded}-{right_no_leading_zero}")
    
    # 4. 4桁数字の場合の各種形式
    if len(digits_only) == 4:
        # 先頭に0を追加（例: "0001" → "00001"）
        search_patterns.append('0' + digits_only)
        # X-YYY形式に変換（例: "0001" → "0-001"）
        search_patterns.append(f"{digits_only[0]}-{digits_only[1:4]}")
        # 左側を2桁にパディングした形式（例: "0001" → "00-001"）
        search_patterns.append(f"{digits_only[0].zfill(2)}-{digits_only[1:4]}")
        # 右側の先頭0を除去（例: "0001" → "0-1"）
        right_part = digits_only[1:4].lstrip('0') or '0'
        search_patterns.append(f"{digits_only[0]}-{right_part}")
        search_patterns.append(f"{digits_only[0].zfill(2)}-{right_part}")
    
    # 重複を除去
    return list(set(search_patterns))










