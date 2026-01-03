"""
入荷機能 - サービス層

CSV取り込みなどのビジネスロジック
"""

import csv
import logging
from datetime import datetime, date
from typing import Dict, Optional
from pathlib import Path

from factory_shipping.extensions import db
from factory_shipping.models import Store, IntakeItem, ItemStatus
from factory_shipping.utils import now_jst

# ロガー設定
logger = logging.getLogger(__name__)


def import_hanjow_csv(file_path: str) -> Dict[str, int]:
    """
    hanjow CSV ファイルを読み込み、IntakeItem に取り込む

    重複チェック:
        store_code + intake_date + tag_number + slip_number の組み合わせで既存レコードをチェック。
        重複の場合はスキップする。

    Args:
        file_path (str): CSV ファイルのパス

    Returns:
        dict: 取り込み結果
            {
                'created': 新規作成件数,
                'skipped': スキップ件数,
                'errors': エラー件数,
                'total_rows': 総行数
            }

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        Exception: その他のエラー
    """
    # ファイル存在チェック
    if not Path(file_path).exists():
        raise FileNotFoundError(f"CSV ファイルが見つかりません: {file_path}")

    stats = {
        'created': 0,
        'skipped': 0,
        'errors': 0,
        'total_rows': 0
    }

    logger.info(f"CSV 取り込み開始: {file_path}")

    # エンコーディングの自動検出（複数のエンコーディングを試行）
    encodings = ['utf-8', 'shift_jis', 'cp932', 'euc-jp', 'iso-2022-jp', 'latin-1', 'windows-1252']
    file_encoding = None

    # エンコーディングを試行（より多くのサンプルを読み込んで検証）
    # まず厳密にチェック、失敗した場合は柔軟にチェック
    for encoding in encodings:
        try:
            # ファイルを開いてより多くのバイトを読み込んでエンコーディングを確認
            with open(file_path, 'rb') as test_file:
                test_bytes = test_file.read(8192)  # より多くのバイトを読み込む
            
            # まず厳密にチェック
            try:
                decoded = test_bytes.decode(encoding, errors='strict')
                file_encoding = encoding
                logger.info(f"エンコーディング検出（厳密）: {encoding}")
                break
            except (UnicodeDecodeError, UnicodeError):
                # 厳密にチェックできなかった場合、柔軟にチェック
                # エラーが少ない場合はそのエンコーディングを使用
                decoded = test_bytes.decode(encoding, errors='replace')
                # 置換文字（\ufffd）の数をカウント
                replacement_count = decoded.count('\ufffd')
                # 置換文字が少ない（5%未満）場合はそのエンコーディングを使用
                if replacement_count < len(decoded) * 0.05:
                    file_encoding = encoding
                    logger.info(f"エンコーディング検出（柔軟）: {encoding} (置換文字: {replacement_count}個)")
                    break
                continue
        except (UnicodeDecodeError, UnicodeError, LookupError):
            continue
        except Exception as e:
            logger.warning(f"エンコーディング {encoding} の試行中にエラー: {e}")
            continue

    if file_encoding is None:
        raise ValueError("CSVファイルのエンコーディングを検出できませんでした。UTF-8、Shift-JIS、CP932、EUC-JP、ISO-2022-JP、Latin-1、Windows-1252のいずれかで保存してください。")

    try:
        # エンコーディングエラーが発生した場合、エラーを無視または置換して読み込む
        with open(file_path, 'r', encoding=file_encoding, errors='replace') as f:
            # CSV ファイルの構造:
            # 1-7行目: メタ情報（スキップ）
            # 8行目: ヘッダー行
            # 9行目以降: データ行
            
            # 最初の7行をスキップ
            for _ in range(7):
                try:
                    next(f)
                except StopIteration:
                    break
            
            # CSV リーダーを作成（ヘッダー行から）
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=9):  # ヘッダーが8行目なので9から
                stats['total_rows'] += 1

                try:
                    # CSV から IntakeItem を作成
                    result = _create_intake_item_from_csv_row(row)

                    if result == 'created':
                        stats['created'] += 1
                    elif result == 'skipped':
                        stats['skipped'] += 1

                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"行 {row_num} の処理中にエラー: {e}")
                    logger.debug(f"問題の行データ: {row}")

        # 処理完了後にコミット
        db.session.commit()
        logger.info(f"CSV 取り込み完了: 作成={stats['created']}, スキップ={stats['skipped']}, エラー={stats['errors']}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"CSV 取り込み中に予期しないエラーが発生: {e}")
        raise

    return stats


def _create_intake_item_from_csv_row(row: Dict[str, str]) -> str:
    """
    CSV の1行から IntakeItem を作成する

    TODO: 実際の CSV の列名に合わせて調整してください。
    以下は仮の列名で実装しています。

    想定される列名（例）:
        - '店舗コード' または 'store_code'
        - '店舗名' または 'store_name'
        - 'タグ番号' または 'tag_number'
        - '預かり日' または 'intake_date'
        - '顧客名' または 'customer_name'
        - '商品名' または 'product_name'
        - '金額' または 'amount'

    Args:
        row (dict): CSV の1行（辞書形式）

    Returns:
        str: 'created' または 'skipped'

    Raises:
        ValueError: 必須フィールドが不足している場合
    """
    # 実際のCSVの列名に合わせて取得
    # CSV列名: "店舗","伝票No","タグ","入荷","出荷","顧客ｺｰﾄﾞ","顧客名","商品ｺｰﾄﾞ","商品名","単価","売価","未・外","預り日","仕上日","返却日時","画像","サイ
    store_name_full = (row.get('店舗') or row.get('店舗名') or row.get('store_name') or '').strip()
    slip_number = (row.get('伝票No') or row.get('伝票番号') or row.get('slip_number') or '').strip()
    tag_number = (row.get('タグ') or row.get('タグ番号') or row.get('tag_number') or '').strip()
    intake_date_str = (row.get('預り日') or row.get('預かり日') or row.get('intake_date') or '').strip()
    customer_name = (row.get('顧客名') or row.get('customer_name') or '').strip()
    product_name = (row.get('商品名') or row.get('product_name') or '').strip()
    amount_str = (row.get('売価') or row.get('金額') or row.get('amount') or '').strip()
    
    # 店舗名から店舗コードを抽出（例: "0002:オザム日の出店" → "0002"）
    store_code = ''
    store_name = ''
    if store_name_full:
        if ':' in store_name_full:
            parts = store_name_full.split(':', 1)
            store_code = parts[0].strip()
            store_name = parts[1].strip() if len(parts) > 1 else store_name_full
        else:
            # コロンがない場合は、先頭の数字を店舗コードとして扱う
            import re
            match = re.match(r'^(\d+)', store_name_full)
            if match:
                store_code = match.group(1)
                store_name = store_name_full
            else:
                store_code = store_name_full[:10]  # フォールバック
                store_name = store_name_full

    # 必須フィールドチェック
    if not store_code:
        raise ValueError(f"店舗コードが空です（店舗名: {store_name_full}）")
    if not intake_date_str:
        raise ValueError("預かり日が空です")

    # 日付パース
    intake_date = _parse_date(intake_date_str)

    # 金額パース（数値に変換）
    amount = _parse_amount(amount_str) if amount_str else None

    # 店舗マスタから店舗を取得（存在しない場合は作成）
    store = _get_or_create_store(store_code, store_name)

    # 重複チェック: store_code + intake_date + tag_number + slip_number
    existing = IntakeItem.query.filter_by(
        store_code=store_code,
        intake_date=intake_date,
        tag_number=tag_number,
        slip_number=slip_number if slip_number else None
    ).first()

    if existing:
        logger.debug(f"重複データをスキップ: {store_code}/{slip_number}/{tag_number}/{intake_date}")
        return 'skipped'

    # 入荷状態を取得（初期状態）
    received_status = ItemStatus.query.filter_by(status_code='received').first()

    # 新規作成
    intake_item = IntakeItem(
        store_id=store.id,
        store_code=store_code,
        store_name=store_name or store.store_name,
        slip_number=slip_number if slip_number else None,
        tag_number=tag_number,
        intake_date=intake_date,
        customer_name=customer_name,
        product_name=product_name,
        amount=amount,
        status_id=received_status.id if received_status else None,  # 初期状態を設定
        imported_at=now_jst(),  # CSV取り込み日時を記録
        # 後方互換性のため旧フィールドにもコピー
        item_code=tag_number,
        item_name=product_name,
    )

    db.session.add(intake_item)
    logger.debug(f"新規作成: {store_code}/{tag_number}/{intake_date}")

    return 'created'


def _get_or_create_store(store_code: str, store_name: Optional[str] = None) -> Store:
    """
    店舗コードから店舗を取得、存在しない場合は作成する

    Args:
        store_code (str): 店舗コード
        store_name (str, optional): 店舗名

    Returns:
        Store: 店舗オブジェクト
    """
    store = Store.query.filter_by(store_code=store_code).first()

    if not store:
        # 店舗が存在しない場合は新規作成
        store = Store(
            store_code=store_code,
            store_name=store_name or f"店舗{store_code}",
            is_active=True
        )
        db.session.add(store)
        db.session.flush()  # ID を取得するため
        logger.info(f"新しい店舗を作成: {store_code} - {store.store_name}")

    return store


def _parse_date(date_str: str) -> date:
    """
    日付文字列をパースする

    対応フォーマット:
        - YYYY-MM-DD
        - YYYY/MM/DD
        - YYYYMMDD

    Args:
        date_str (str): 日付文字列

    Returns:
        date: 日付オブジェクト

    Raises:
        ValueError: パースできない形式の場合
    """
    # ハイフン区切り
    if '-' in date_str:
        return datetime.strptime(date_str, '%Y-%m-%d').date()

    # スラッシュ区切り
    if '/' in date_str:
        return datetime.strptime(date_str, '%Y/%m/%d').date()

    # 区切りなし（8桁）
    if len(date_str) == 8 and date_str.isdigit():
        return datetime.strptime(date_str, '%Y%m%d').date()

    raise ValueError(f"日付のパースに失敗: {date_str}")


def _parse_amount(amount_str: str) -> Optional[int]:
    """
    金額文字列をパースする

    カンマ、円記号、空白を除去して数値に変換

    Args:
        amount_str (str): 金額文字列（例: "1,234円", "1234", "￥1,234"）

    Returns:
        int: 金額（円単位）、パースできない場合は None
    """
    if not amount_str:
        return None

    # カンマ、円記号、￥、空白を除去
    cleaned = amount_str.replace(',', '').replace('円', '').replace('￥', '').replace(' ', '')

    try:
        return int(cleaned)
    except ValueError:
        logger.warning(f"金額のパースに失敗: {amount_str}")
        return None
