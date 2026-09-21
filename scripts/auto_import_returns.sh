#!/bin/bash
################################################################################
# 返却日指定 CSV 自動取り込みスクリプト
#
# 説明:
#   kingdrysystem から毎日 04:30 の rsync で届く返却日指定 CSV
#   (uriage_daityo_henkyakubi_shitei<YYYY-MM-DD>.csv) を読み、返却された品目の
#   intake_items.returned_at を設定する。直近7日分を毎回読み直すので、
#   あとから取り込まれた品目も返却済になる（何度流しても結果は同じ）。
#   CSV が無い日（定休日など）はエラーにしない。
#
# 使用方法:
#   ./auto_import_returns.sh              # 直近7日分（昨日まで）
#   ./auto_import_returns.sh --days 14    # run.py import-returns の引数をそのまま渡す
#
# cron設定:
#   0 5 * * * ec2-user /var/www/html/factory-intake-shipping/scripts/auto_import_returns.sh >> /var/log/factory-shipping/import-returns.log 2>&1
################################################################################

# 並行起動防止（手動の一括反映と cron が重ならないように）
LOCK_FILE="/tmp/factory-import-returns.lock"
exec 9> "${LOCK_FILE}"
if ! flock -n 9; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] auto_import_returns.sh: 別プロセスが実行中のためスキップ"
    exit 0
fi

PROJECT_DIR="/var/www/html/factory-intake-shipping"
PYTHON="${PROJECT_DIR}/venv/bin/python"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 返却 CSV 取り込み開始"

cd "${PROJECT_DIR}" || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: プロジェクトディレクトリに移動できません: ${PROJECT_DIR}" >&2
    exit 1
}

"${PYTHON}" run.py import-returns "$@"
RESULT=$?

if [ ${RESULT} -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 返却 CSV 取り込み正常終了"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: 返却 CSV 取り込み失敗（終了コード: ${RESULT}）" >&2
fi
exit ${RESULT}
