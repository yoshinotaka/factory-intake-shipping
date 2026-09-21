"""
入荷機能 - 返却（お客様への引き渡し）の取り込み

半蔵（ASTEMPO）の売上台帳を「返却日」で検索した CSV を読み、載っている品目の
intake_items.returned_at に返却日時を入れる。

CSV:
    uriage_daityo_henkyakubi_shitei<YYYY-MM-DD>.csv（日付 = 返却日）
    kingdrysystem の ASTP200_uriage_daityo_DL.py が毎日 02:30 に前日分を取得し、
    04:30 の rsync で RETURN_CSV_DIR に届く。前年以前は
    RETURN_CSV_DIR/uriage_daityo_download_csv_<YYYY>/ の下にある。
    1〜7行目はタイトルと検索条件、8行目がヘッダー（預り日 CSV に「取消」列を足したもの）。

突き合わせ:
    タグのある行: (店舗, 伝票No, 預り日, タグ)。加えて、伝票No の無い旧データ
        （2025-11 の取り込み分）とは (店舗, 預り日, タグ) で突き合わせる。
        同じ店舗・同じ預り日でタグが複数の伝票にまたがることは無い（確認済み）。
    タグが空の行（会員登録料・ﾏﾃﾞ 早期引取です 等の品物ではない行）:
        (店舗, 伝票No, 預り日, 商品名)。同じ商品名が複数行あればすべて返却済にする。
    伝票No だけでは店舗をまたいで重複し、同じ店舗でも番号が再利用されるため、
    必ず店舗と預り日を含めること。

冪等性:
    returned_at は「今の値より新しい返却日時のときだけ」書き換える。
    同じ品物が別の日に 2 回返却されることがあり（返却の取り消しとやり直し等）、
    新しい返却日時が残る。何度流しても、どの順で流しても結果は同じになる。
    預り日 CSV の取り込み（services.import_hanjow_csv）は既存行を更新しないので、
    再取り込みで返却済が消えることはない。

更新しないもの:
    status_id / shipped_at / updated_at / shipment_logs。返却済かどうかは
    returned_at だけで表し、Analytics API が表示用の状態に変換する。
    updated_at を触らないのは、管理画面の「更新日」絞り込みが毎日の返却で
    埋まらないようにするため。
"""

import csv
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, text

from factory_shipping.extensions import db
from factory_shipping.intake.services import _parse_date
from factory_shipping.models import IntakeItem
from factory_shipping.utils import today_jst

logger = logging.getLogger(__name__)

RETURN_CSV_DIR = Path('/var/www/html/kingdrysystem_back/LINE/uriage_daityo_download_csv')
RETURN_CSV_PREFIX = 'uriage_daityo_henkyakubi_shitei'
# 2021-12-2_3_back.csv のような手作業の控えファイルを拾わないよう、日付だけの名前に限る
RETURN_CSV_NAME = re.compile(r'^uriage_daityo_henkyakubi_shitei(\d{4}-\d{2}-\d{2})\.csv$')

# 取消列がこの値の行だけを返却として扱う
NOT_CANCELLED = '-'

# IN 句 1 回あたりの伝票No の数
_SLIP_CHUNK = 500


@dataclass(frozen=True)
class ReturnRow:
    """返却 CSV の 1 行（突き合わせに使う列だけ）"""
    row_num: int
    store_code: str
    slip_number: Optional[str]
    tag_number: str
    product_name: str
    intake_date: date
    returned_at: datetime

    def describe(self) -> str:
        what = self.tag_number or f'(タグ空) {self.product_name}'
        return (f'店舗={self.store_code} 伝票={self.slip_number or "-"} '
                f'預り日={self.intake_date.isoformat()} {what} '
                f'返却={self.returned_at:%Y-%m-%d %H:%M}')


def find_return_csv(return_date: date) -> Optional[Path]:
    """返却日の CSV を探す。今年分は直下、前年以前は年別ディレクトリの下にある。"""
    name = f'{RETURN_CSV_PREFIX}{return_date.isoformat()}.csv'
    for directory in (RETURN_CSV_DIR, RETURN_CSV_DIR / f'uriage_daityo_download_csv_{return_date.year}'):
        path = directory / name
        if path.exists():
            return path
    return None


def list_return_csv_dates() -> List[date]:
    """手元にある返却 CSV の返却日を古い順に返す。"""
    found = set()
    for directory in [RETURN_CSV_DIR, *sorted(RETURN_CSV_DIR.glob('uriage_daityo_download_csv_*'))]:
        if not directory.is_dir():
            continue
        for path in directory.glob(f'{RETURN_CSV_PREFIX}*.csv'):
            m = RETURN_CSV_NAME.match(path.name)
            if m:
                found.add(datetime.strptime(m.group(1), '%Y-%m-%d').date())
    return sorted(found)


def _store_code(store_full: str) -> str:
    """"0021:○○店" → "0021"（services._create_intake_item_from_csv_row と同じ規則）"""
    if ':' in store_full:
        return store_full.split(':', 1)[0].strip()
    m = re.match(r'^(\d+)', store_full)
    return m.group(1) if m else store_full[:10]


def _parse_returned_at(value: str) -> datetime:
    """"2026/09/20 17：32" → datetime。時刻の区切りは全角コロン。"""
    return datetime.strptime(value.strip().replace('：', ':'), '%Y/%m/%d %H:%M')


def read_return_csv(file_path: Path, stats: Counter) -> List[ReturnRow]:
    """返却 CSV を読み、返却として扱う行を返す。取消行・読めない行は stats に数えてログに残す。"""
    rows: List[ReturnRow] = []
    with open(file_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        for _ in range(7):
            if not f.readline():
                break
        # ヘッダーには "タグ" が 2 回ある。DictReader は後ろの列を採るが、
        # 預り日 CSV の取り込みも同じ DictReader なので、同じ列で突き合わせられる。
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=9):
            stats['rows'] += 1
            try:
                store_code = _store_code((row.get('店舗') or '').strip())
                slip_number = (row.get('伝票No') or '').strip() or None
                tag_number = (row.get('タグ') or '').strip()
                product_name = (row.get('商品名') or '').strip()
                intake_date = _parse_date((row.get('預り日') or '').strip())
                returned_at = _parse_returned_at(row.get('返却日時') or '')
                cancel = (row.get('取消') or '').strip()
            except Exception as e:
                stats['errors'] += 1
                logger.warning(f'{file_path.name} 行 {row_num}: 読めない行をスキップ ({e}): {row}')
                continue

            parsed = ReturnRow(row_num, store_code, slip_number, tag_number,
                               product_name, intake_date, returned_at)
            if cancel != NOT_CANCELLED:
                stats['cancelled'] += 1
                logger.warning(f'{file_path.name} 行 {row_num}: 取消={cancel!r} のため返却済にしない: '
                               f'{parsed.describe()}')
                continue
            rows.append(parsed)
    return rows


def _load_candidates(rows: List[ReturnRow]):
    """rows と突き合う可能性のある intake_items を読み、キーごとの id と現在の returned_at を返す。"""
    tagged: Dict[Tuple, List[int]] = defaultdict(list)
    untagged: Dict[Tuple, List[int]] = defaultdict(list)
    no_slip: Dict[Tuple, List[int]] = defaultdict(list)
    current: Dict[int, Optional[datetime]] = {}

    cols = (IntakeItem.id, IntakeItem.store_code, IntakeItem.slip_number, IntakeItem.intake_date,
            IntakeItem.tag_number, IntakeItem.product_name, IntakeItem.returned_at)

    slips = sorted({r.slip_number for r in rows if r.slip_number})
    for i in range(0, len(slips), _SLIP_CHUNK):
        chunk = slips[i:i + _SLIP_CHUNK]
        for it in db.session.query(*cols).filter(IntakeItem.slip_number.in_(chunk)):
            current[it.id] = it.returned_at
            if it.tag_number:
                tagged[(it.store_code, it.slip_number, it.intake_date, it.tag_number)].append(it.id)
            else:
                untagged[(it.store_code, it.slip_number, it.intake_date,
                          (it.product_name or '').strip())].append(it.id)

    # 伝票No の無い旧データ（タグで突き合わせる）
    dates = sorted({r.intake_date for r in rows if r.tag_number})
    if dates:
        for it in db.session.query(*cols).filter(IntakeItem.slip_number.is_(None),
                                                 IntakeItem.intake_date.in_(dates),
                                                 IntakeItem.tag_number != ''):
            current[it.id] = it.returned_at
            no_slip[(it.store_code, it.intake_date, it.tag_number)].append(it.id)

    return tagged, untagged, no_slip, current


def _match(row: ReturnRow, tagged, untagged, no_slip) -> List[int]:
    if row.tag_number:
        # 伝票No の無い行は、同じ品物が伝票No ありでも重複して入っていることがある
        # （2025-11-28/29 の取り込み）。同じ品物なので両方とも返却済にする。
        return (tagged.get((row.store_code, row.slip_number, row.intake_date, row.tag_number), [])
                + no_slip.get((row.store_code, row.intake_date, row.tag_number), []))
    return untagged.get((row.store_code, row.slip_number, row.intake_date, row.product_name), [])


def earliest_intake_date() -> Optional[date]:
    """intake_items にある最古の預り日。これより前の預り日の行は突き合わせようがない。"""
    return db.session.query(func.min(IntakeItem.intake_date)).scalar()


def apply_return_rows(rows: Iterable[ReturnRow], stats: Counter, *, source: str = '',
                      min_intake_date: Optional[date] = None, dry_run: bool = False) -> None:
    """返却行を intake_items に反映する（コミットは呼び出し側）。

    stats に数える項目:
        out_of_range      預り日が intake_items の範囲より前（突き合わせ対象外）
        matched_tagged / matched_untagged     突き合った行
        unmatched_tagged / unmatched_untagged 範囲内なのに突き合わなかった行（ログに出す）
        multi_hit         1 行が 2 品目以上に突き合った行（重複取り込みの残骸など）
        items_updated     returned_at を入れた・新しくした品目数
        items_unchanged   既に同じか新しい returned_at だった品目数
    """
    rows = list(rows)
    if min_intake_date is not None:
        in_range = [r for r in rows if r.intake_date >= min_intake_date]
        stats['out_of_range'] += len(rows) - len(in_range)
        rows = in_range
    if not rows:
        return

    tagged, untagged, no_slip, current = _load_candidates(rows)

    newest: Dict[int, datetime] = {}
    for row in rows:
        kind = 'tagged' if row.tag_number else 'untagged'
        ids = _match(row, tagged, untagged, no_slip)
        if not ids:
            stats[f'unmatched_{kind}'] += 1
            logger.info(f'{source} 行 {row.row_num}: intake_items に無い: {row.describe()}')
            continue
        stats[f'matched_{kind}'] += 1
        if len(ids) > 1:
            stats['multi_hit'] += 1
        for item_id in ids:
            if item_id not in newest or row.returned_at > newest[item_id]:
                newest[item_id] = row.returned_at

    params = []
    for item_id, returned_at in newest.items():
        now = current.get(item_id)
        if now is None or now < returned_at:
            params.append({'item_id': item_id, 'returned_at': returned_at})
        else:
            stats['items_unchanged'] += 1
    stats['items_updated'] += len(params)

    if params and not dry_run:
        # ORM / Core の update() だと updated_at の onupdate が走るので、素の SQL で書く。
        # WHERE の条件は、並行して流れた別の取り込みより古い日時で上書きしないための保険。
        db.session.execute(
            text('UPDATE intake_items SET returned_at = :returned_at '
                 'WHERE id = :item_id AND (returned_at IS NULL OR returned_at < :returned_at)'),
            params,
        )


def import_return_csv(return_date: date, *, min_intake_date: Optional[date] = None,
                      dry_run: bool = False) -> Counter:
    """1 日分の返却 CSV を取り込んでコミットする。ファイルが無い日は missing=1 を返す（エラーにしない）。"""
    stats: Counter = Counter()
    path = find_return_csv(return_date)
    if path is None:
        stats['missing'] = 1
        logger.info(f'{return_date.isoformat()}: 返却 CSV なし（定休日など）')
        return stats

    stats['files'] = 1
    try:
        rows = read_return_csv(path, stats)
        apply_return_rows(rows, stats, source=path.name,
                          min_intake_date=min_intake_date, dry_run=dry_run)
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    logger.info(f'{path.name}: 行={stats["rows"]} '
                f'一致(タグ有/空)={stats["matched_tagged"]}/{stats["matched_untagged"]} '
                f'不一致(タグ有/空)={stats["unmatched_tagged"]}/{stats["unmatched_untagged"]} '
                f'範囲外={stats["out_of_range"]} 取消={stats["cancelled"]} '
                f'更新={stats["items_updated"]} 既反映={stats["items_unchanged"]}'
                + (' [dry-run]' if dry_run else ''))
    return stats


def import_return_csvs(dates: Iterable[date], *, dry_run: bool = False) -> Dict[str, Counter]:
    """複数日の返却 CSV を古い順に取り込む。返却年ごとの集計を返す（キー 'total' は全体）。"""
    min_intake_date = earliest_intake_date()
    by_year: Dict[str, Counter] = defaultdict(Counter)
    for d in sorted(set(dates)):
        stats = import_return_csv(d, min_intake_date=min_intake_date, dry_run=dry_run)
        by_year[str(d.year)].update(stats)
        by_year['total'].update(stats)
    return dict(by_year)


def recent_dates(days: int, today: Optional[date] = None) -> List[date]:
    """昨日から days 日さかのぼった返却日（古い順）。今日の分は翌朝まで届かない。"""
    today = today or today_jst()
    return [today - timedelta(days=n) for n in range(days, 0, -1)]
