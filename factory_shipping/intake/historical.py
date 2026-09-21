"""
入荷機能 - 過去分（預り日 2021-01-04〜2025-09-30）の取り込みと、顧客コード・返却日時の埋め戻し

kinglinesystem の依頼 REQ-20260921-historical-intake（会員利用履歴に 2025-10 より前の来店を出す）。
毎晩の取り込み（services.import_hanjow_csv）は 2025-10-01 からなので、それより前を一度だけ入れる。

CSV:
    RETURN_CSV_DIR/uriage_daityo_download_csv_<YYYY>/uriage_daityo_oazukaribi_shitei<YYYY-MM-DD>.csv
    （今年分は RETURN_CSV_DIR 直下。日付 = 預り日。1 ファイルに 1 預り日の全店舗分）
    - 毎晩の取り込み元 king-req/downloads_hanjow/hanjow_*.csv と同じ売上台帳だが、
      「取消表示［表示］」で取得されていて「取消」列がある。取消が '-' 以外の行は取り込まない
      （毎晩の取り込み元は取消を表示しない設定なので、取消の行はもともと入っていない）。
    - 列は見出しの名前で読む（DictReader。見出しの「タグ」は 2 回あるが値は同じ）。
    - 2021 年分の多くは 2023-02 に取り直したもので「返却日時」列が埋まっている。

重複キーと line_seq:
    services._create_intake_item_from_csv_row と同じ (店舗, 預り日, タグ, 伝票No, 商品名, line_seq)。
    line_seq は取消の行を除いたあとの出現順で振る（毎晩の取り込み元と同じ並びになる）。
    何度流しても、既にある行は入れない。

速さ:
    1 ファイル（= 1 預り日）ごとに、その日の既存キーを 1 回で読み、無い行だけまとめて INSERT する
    （毎晩の取り込みは 1 行ずつ SELECT するので、150 万行では遅い）。

状態:
    status_id = 入荷。返却の記録が無い過去分は Analytics API が「返却記録なし」を返す
    （models.IntakeItem.display_status。預り日 < BUSINESS_MIN_INTAKE_DATE）。

返却日時:
    取り込みでは入れない。取り込みのあと
      1. run.py import-returns --all        （返却 CSV。こちらを優先する）
      2. run.py fill-returned-from-intake   （この CSV の「返却日時」列で、まだ空の品目だけ埋める）
    の順に流す。

顧客コード:
    過去分は取り込み時に入れる。既存の品目（2025-10-01 以降）は backfill_customer_codes() で
    毎晩の取り込み元 hanjow_*.csv と預り日 CSV から同じキーで埋める。以後は毎晩の取り込みで入る。
"""

import csv
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sqlalchemy import bindparam, text

from factory_shipping.extensions import db
from factory_shipping.intake.returns import RETURN_CSV_DIR, _parse_returned_at, _store_code
from factory_shipping.intake.services import _get_or_create_store, _parse_amount, _parse_date
from factory_shipping.models import BUSINESS_MIN_INTAKE_DATE, IntakeItem, ItemStatus
from factory_shipping.utils import now_jst

logger = logging.getLogger(__name__)

INTAKE_CSV_PREFIX = 'uriage_daityo_oazukaribi_shitei'
# 2021-12-2v4_v.csv / 2021-12-2v5.csv のような手作業の控えファイルを拾わないよう、日付だけの名前に限る
INTAKE_CSV_NAME = re.compile(r'^uriage_daityo_oazukaribi_shitei(\d{4}-\d{2}-\d{2})\.csv$')
HANJOW_CSV_DIR = Path('/var/www/html/king-req/downloads_hanjow')

NOT_CANCELLED = '-'
_INSERT_CHUNK = 1000


@dataclass
class IntakeRow:
    """預り日 CSV の 1 行（取り込みに使う列だけ）"""
    row_num: int
    store_code: str
    store_name: str
    slip_number: Optional[str]
    tag_number: str
    intake_date: date
    customer_name: str
    customer_code: Optional[str]
    product_name: str
    amount: Optional[int]
    returned_at: Optional[datetime]
    line_seq: int = 1

    @property
    def key(self):
        return (self.store_code, self.intake_date, self.tag_number, self.slip_number,
                self.product_name, self.line_seq)


def find_intake_csv(intake_date: date) -> Optional[Path]:
    """預り日の CSV を探す。今年分は直下、前年以前は年別ディレクトリの下にある。"""
    name = f'{INTAKE_CSV_PREFIX}{intake_date.isoformat()}.csv'
    for directory in (RETURN_CSV_DIR / f'uriage_daityo_download_csv_{intake_date.year}', RETURN_CSV_DIR):
        path = directory / name
        if path.exists():
            return path
    return None


def list_intake_csv_dates(before: Optional[date] = BUSINESS_MIN_INTAKE_DATE) -> List[date]:
    """手元にある預り日 CSV の預り日を古い順に返す（before より前だけ）。"""
    found = set()
    for directory in [RETURN_CSV_DIR, *sorted(RETURN_CSV_DIR.glob('uriage_daityo_download_csv_*'))]:
        if not directory.is_dir():
            continue
        for path in directory.glob(f'{INTAKE_CSV_PREFIX}*.csv'):
            m = INTAKE_CSV_NAME.match(path.name)
            if m:
                d = datetime.strptime(m.group(1), '%Y-%m-%d').date()
                if before is None or d < before:
                    found.add(d)
    return sorted(found)


def read_intake_csv(file_path: Path, stats: Counter, *, has_cancel_column: bool = True) -> List[IntakeRow]:
    """預り日 CSV を読み、取り込む行を返す。line_seq は毎晩の取り込みと同じ規則で振る。

    has_cancel_column=False は毎晩の取り込み元 hanjow_*.csv（取消の行が無い）を読むとき。
    """
    rows: List[IntakeRow] = []
    seen: Dict[tuple, int] = {}
    with open(file_path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        for _ in range(7):
            if not f.readline():
                break
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=9):
            stats['rows'] += 1
            if has_cancel_column and (row.get('取消') or '').strip() not in (NOT_CANCELLED, ''):
                stats['cancelled'] += 1
                continue
            try:
                store_full = (row.get('店舗') or '').strip()
                store_code = _store_code(store_full)
                store_name = store_full.split(':', 1)[1].strip() if ':' in store_full else store_full
                if not store_code:
                    raise ValueError('店舗コードが空')
                intake_date = _parse_date((row.get('預り日') or '').strip())
                amount_str = (row.get('売価') or '').strip()
                returned_str = (row.get('返却日時') or '').strip()
                parsed = IntakeRow(
                    row_num=row_num,
                    store_code=store_code,
                    store_name=store_name,
                    slip_number=(row.get('伝票No') or '').strip() or None,
                    tag_number=(row.get('タグ') or '').strip(),
                    intake_date=intake_date,
                    customer_name=(row.get('顧客名') or '').strip(),
                    customer_code=(row.get('顧客ｺｰﾄﾞ') or '').strip() or None,
                    product_name=(row.get('商品名') or '').strip(),
                    amount=_parse_amount(amount_str) if amount_str else None,
                    returned_at=None,
                )
            except Exception as e:
                stats['errors'] += 1
                logger.warning(f'{file_path.name} 行 {row_num}: 読めない行をスキップ ({e}): {row}')
                continue
            if returned_str:
                # 返却日時が読めなくても品目は取り込む（返却日時だけ空にする）
                try:
                    parsed.returned_at = _parse_returned_at(returned_str)
                except ValueError:
                    stats['bad_returned_at'] += 1
                    logger.warning(f'{file_path.name} 行 {row_num}: 返却日時が読めない: {returned_str!r}')
            base = (parsed.store_code, parsed.intake_date, parsed.tag_number, parsed.slip_number,
                    parsed.product_name)
            seen[base] = seen.get(base, 0) + 1
            parsed.line_seq = seen[base]
            rows.append(parsed)
    return rows


def _existing_ids(intake_dates: Iterable[date]) -> Dict[tuple, List[int]]:
    """預り日の既存行のキー → id のリスト。

    同じキーの行が 2 行あることがある（2026-06 の line_seq 導入前後の取り込みでできた重複。2025-10 以降で約 2,250 組）。
    埋め戻しは重複の両方に入れる。
    """
    ids: Dict[tuple, List[int]] = defaultdict(list)
    for it in (db.session.query(IntakeItem.id, IntakeItem.store_code, IntakeItem.intake_date,
                                IntakeItem.tag_number, IntakeItem.slip_number, IntakeItem.product_name,
                                IntakeItem.line_seq)
               .filter(IntakeItem.intake_date.in_(sorted(set(intake_dates))))):
        ids[(it.store_code, it.intake_date, it.tag_number or '', it.slip_number,
             (it.product_name or ''), it.line_seq)].append(it.id)
    return dict(ids)


# ---------------------------------------------------------------- 過去分の取り込み

def import_intake_csv(intake_date: date, *, dry_run: bool = False, allow_business_range: bool = False,
                      _cache: Optional[dict] = None) -> Counter:
    """1 預り日分の CSV を取り込んでコミットする。ファイルが無い日は missing=1（エラーにしない）。"""
    stats: Counter = Counter()
    if intake_date >= BUSINESS_MIN_INTAKE_DATE and not allow_business_range:
        raise ValueError(f'{intake_date} は毎晩の取り込みの範囲（{BUSINESS_MIN_INTAKE_DATE} 以降）です')
    path = find_intake_csv(intake_date)
    if path is None:
        stats['missing'] = 1
        logger.info(f'{intake_date.isoformat()}: 預り日 CSV なし（定休日など）')
        return stats

    cache = _cache if _cache is not None else {}
    stats['files'] = 1
    try:
        rows = read_intake_csv(path, stats)
        existing = _existing_ids(r.intake_date for r in rows) if rows else {}
        if 'received_id' not in cache:
            received = ItemStatus.query.filter_by(status_code='received').first()
            cache['received_id'] = received.id if received else None
        store_ids = cache.setdefault('store_ids', {})

        now = now_jst()
        new_rows = []
        for r in rows:
            if r.key in existing:
                stats['existing'] += 1
                continue
            if r.intake_date != intake_date:
                stats['other_date'] += 1  # 預り日 CSV に別の預り日の行（ほぼ無い）。そのまま取り込む
            if r.store_code not in store_ids:
                store_ids[r.store_code] = _get_or_create_store(r.store_code, r.store_name).id
            new_rows.append({
                'store_id': store_ids[r.store_code],
                'store_code': r.store_code,
                'store_name': r.store_name,
                'slip_number': r.slip_number,
                'tag_number': r.tag_number,
                'line_seq': r.line_seq,
                'product_name': r.product_name,
                'customer_name': r.customer_name,
                'customer_code': r.customer_code,
                'amount': r.amount,
                'intake_date': r.intake_date,
                'status_id': cache['received_id'],
                'intake_status': '通常',
                'item_code': r.tag_number,
                'item_name': r.product_name,
                'quantity': 1,
                'imported_at': now,
                'created_at': now,
                'updated_at': now,
            })
            existing[r.key] = [-1]  # 同じファイル内の重複（無いはずだが念のため）
        stats['created'] = len(new_rows)

        if new_rows and not dry_run:
            for i in range(0, len(new_rows), _INSERT_CHUNK):
                db.session.execute(IntakeItem.__table__.insert(), new_rows[i:i + _INSERT_CHUNK])
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
    except Exception:
        db.session.rollback()
        cache.pop('store_ids', None)  # rollback で作りかけの店舗が消えるので読み直す
        raise

    logger.info(f'{path.name}: 行={stats["rows"]} 取消={stats["cancelled"]} 新規={stats["created"]} '
                f'既存={stats["existing"]} 読めない={stats["errors"]}' + (' [dry-run]' if dry_run else ''))
    return stats


def import_intake_csvs(dates: Iterable[date], *, dry_run: bool = False) -> Dict[str, Counter]:
    """複数日の預り日 CSV を古い順に取り込む。預り年ごとの集計を返す（キー 'total' は全体）。"""
    by_year: Dict[str, Counter] = defaultdict(Counter)
    cache: dict = {}
    for d in sorted(set(dates)):
        stats = import_intake_csv(d, dry_run=dry_run, _cache=cache)
        by_year[str(d.year)].update(stats)
        by_year['total'].update(stats)
    return dict(by_year)


# ---------------------------------------------------------------- 返却日時列での補い

def fill_returned_from_intake_csv(intake_date: date, *, dry_run: bool = False) -> Counter:
    """預り日 CSV の「返却日時」列で、returned_at がまだ空の品目だけを埋める。

    返却 CSV（import-returns）を先に流すこと。返却 CSV の値があればそちらを優先する（上書きしない）。
    updated_at は動かさない（returns.py と同じ理由）。
    """
    stats: Counter = Counter()
    path = find_intake_csv(intake_date)
    if path is None:
        stats['missing'] = 1
        return stats
    stats['files'] = 1
    rows = [r for r in read_intake_csv(path, stats) if r.returned_at]
    stats['with_value'] = len(rows)
    if not rows:
        return stats
    ids = _existing_ids(r.intake_date for r in rows)
    params = []
    for r in rows:
        item_ids = ids.get(r.key)
        if not item_ids:
            stats['not_found'] += 1
            continue
        params.extend({'item_id': item_id, 'returned_at': r.returned_at} for item_id in item_ids)
    if params:
        if dry_run:
            stats['filled'] += db.session.execute(
                text('SELECT COUNT(*) FROM intake_items WHERE id IN :ids AND returned_at IS NULL')
                .bindparams(bindparam('ids', expanding=True)),
                {'ids': [p['item_id'] for p in params]}).scalar()
        else:
            result = db.session.execute(
                text('UPDATE intake_items SET returned_at = :returned_at '
                     'WHERE id = :item_id AND returned_at IS NULL'),
                params,
            )
            stats['filled'] += result.rowcount
            db.session.commit()
    stats['already'] = len(params) - stats['filled']
    logger.info(f'{path.name}: 返却日時あり={stats["with_value"]} 埋めた={stats["filled"]} '
                f'返却CSVで反映済み={stats["already"]} 品目なし={stats["not_found"]}'
                + (' [dry-run]' if dry_run else ''))
    return stats


def fill_returned_from_intake_csvs(dates: Iterable[date], *, dry_run: bool = False) -> Dict[str, Counter]:
    by_year: Dict[str, Counter] = defaultdict(Counter)
    for d in sorted(set(dates)):
        stats = fill_returned_from_intake_csv(d, dry_run=dry_run)
        by_year[str(d.year)].update(stats)
        by_year['total'].update(stats)
    return dict(by_year)


# ---------------------------------------------------------------- 既存品目への顧客コードの埋め戻し

def hanjow_csv_path(intake_date: date) -> Path:
    return HANJOW_CSV_DIR / f'hanjow_{intake_date:%Y%m%d}.csv'


def backfill_customer_code(intake_date: date, *, dry_run: bool = False) -> Counter:
    """customer_code が空の既存品目に顧客コードを入れる（既に入っている値は変えない）。

    読むのは 1. 毎晩の取り込み元 hanjow_*.csv 2. 同じ預り日の預り日 CSV（取消の行は除く）。
    取り込み元 CSV が後から取り直されて内容が変わった日は、2 で補う。
    2025-11 の移行でできた伝票No の無い行（同じ品物の伝票No ありの行と重複）は、
    店舗・預り日・タグ・商品名で突き合わせる（同じ店舗・預り日でタグが重なることは無い）。
    """
    stats: Counter = Counter()
    sources = []
    if hanjow_csv_path(intake_date).exists():
        sources.append((hanjow_csv_path(intake_date), False))
    intake_csv = find_intake_csv(intake_date)
    if intake_csv is not None:
        sources.append((intake_csv, True))
    if not sources:
        stats['missing'] = 1
        return stats
    stats['files'] = 1

    ids = _existing_ids([intake_date])
    no_slip: Dict[tuple, List[int]] = defaultdict(list)
    for (store, d, tag, slip, product, _seq), item_ids in ids.items():
        if slip is None and tag:
            no_slip[(store, d, tag, product)].extend(item_ids)

    codes: Dict[int, str] = {}
    for n, (path, has_cancel) in enumerate(sources):
        read_stats: Counter = Counter()
        for r in read_intake_csv(path, read_stats, has_cancel_column=has_cancel):
            if not r.customer_code:
                continue
            item_ids = ids.get(r.key)
            if item_ids:
                for item_id in item_ids:
                    codes.setdefault(item_id, r.customer_code)
            elif r.tag_number:
                for no_slip_id in no_slip.get((r.store_code, r.intake_date, r.tag_number, r.product_name), []):
                    codes.setdefault(no_slip_id, r.customer_code)
        if n == 0:
            stats['rows'] += read_stats['rows']
        stats['errors'] += read_stats['errors']
    stats['items_with_code'] = len(codes)

    params = [{'item_id': k, 'customer_code': v} for k, v in codes.items()]
    if params and not dry_run:
        result = db.session.execute(
            text('UPDATE intake_items SET customer_code = :customer_code '
                 'WHERE id = :item_id AND customer_code IS NULL'),
            params,
        )
        stats['filled'] += result.rowcount
        db.session.commit()
    elif params:
        stats['filled'] += db.session.execute(
            text('SELECT COUNT(*) FROM intake_items WHERE id IN :ids AND customer_code IS NULL')
            .bindparams(bindparam('ids', expanding=True)), {'ids': list(codes)}).scalar()
    logger.info(f'{intake_date.isoformat()}: 顧客コードが分かった品目={stats["items_with_code"]} '
                f'埋めた={stats["filled"]}' + (' [dry-run]' if dry_run else ''))
    return stats


def backfill_customer_codes(dates: Iterable[date], *, dry_run: bool = False) -> Dict[str, Counter]:
    by_year: Dict[str, Counter] = defaultdict(Counter)
    for d in sorted(set(dates)):
        stats = backfill_customer_code(d, dry_run=dry_run)
        by_year[str(d.year)].update(stats)
        by_year['total'].update(stats)
    return dict(by_year)
