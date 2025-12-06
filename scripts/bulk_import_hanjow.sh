#!/bin/bash
################################################################################
# hanjow CSV 一括取り込みスクリプト
#
# 説明:
#   指定された期間のhanjow CSVファイルを一括で取り込みます。
#   遡って取得したデータと既存データが混在していても、重複を防いで
#   差分のみを取り込みます。
#
# 使用方法:
#   ./bulk_import_hanjow.sh START_DATE END_DATE
#
# 例:
#   # 2025-11-01 から 2025-11-29 までを取り込み
#   ./bulk_import_hanjow.sh 2025-11-01 2025-11-29
#
#   # 過去7日分を取り込み
#   ./bulk_import_hanjow.sh $(date -d '7 days ago' '+%Y-%m-%d') $(date '+%Y-%m-%d')
#
################################################################################

# 設定
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_IMPORT_SCRIPT="${SCRIPT_DIR}/auto_import_hanjow.sh"
LOG_DIR="/var/log/factory-shipping"
LOG_FILE="${LOG_DIR}/bulk-import.log"

# ログディレクトリが存在しない場合は作成
mkdir -p "${LOG_DIR}"

# ログ関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# 引数チェック
if [ $# -ne 2 ]; then
    echo "使用方法: $0 START_DATE END_DATE"
    echo "例: $0 2025-11-01 2025-11-29"
    exit 1
fi

START_DATE="$1"
END_DATE="$2"

# 日付妥当性チェック
if ! date -d "${START_DATE}" '+%Y-%m-%d' > /dev/null 2>&1; then
    echo "エラー: 開始日付が不正です: ${START_DATE}"
    exit 1
fi

if ! date -d "${END_DATE}" '+%Y-%m-%d' > /dev/null 2>&1; then
    echo "エラー: 終了日付が不正です: ${END_DATE}"
    exit 1
fi

log "=========================================="
log "hanjow CSV 一括取り込み開始"
log "=========================================="
log "開始日: ${START_DATE}"
log "終了日: ${END_DATE}"
log "=========================================="

# 統計カウンタ
TOTAL_DAYS=0
SUCCESS_COUNT=0
SKIP_COUNT=0
ERROR_COUNT=0

# 日付ループ
CURRENT_DATE="${START_DATE}"
while [ "$(date -d "${CURRENT_DATE}" '+%Y%m%d')" -le "$(date -d "${END_DATE}" '+%Y%m%d')" ]; do
    TOTAL_DAYS=$((TOTAL_DAYS + 1))
    log "----------------------------------------"
    log "処理日: ${CURRENT_DATE} (${TOTAL_DAYS}日目)"

    # 自動取り込みスクリプトを実行
    if "${AUTO_IMPORT_SCRIPT}" "${CURRENT_DATE}"; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        log "✓ ${CURRENT_DATE}: 成功"
    else
        RESULT=$?
        if [ ${RESULT} -eq 0 ]; then
            SKIP_COUNT=$((SKIP_COUNT + 1))
            log "- ${CURRENT_DATE}: スキップ（CSVファイルなし）"
        else
            ERROR_COUNT=$((ERROR_COUNT + 1))
            log "✗ ${CURRENT_DATE}: エラー"
        fi
    fi

    # 次の日付へ
    CURRENT_DATE=$(date -d "${CURRENT_DATE} + 1 day" '+%Y-%m-%d')
done

log "=========================================="
log "一括取り込み完了"
log "=========================================="
log "対象期間: ${START_DATE} ～ ${END_DATE}"
log "総日数: ${TOTAL_DAYS}日"
log "成功: ${SUCCESS_COUNT}日"
log "スキップ: ${SKIP_COUNT}日"
log "エラー: ${ERROR_COUNT}日"
log "=========================================="

# 終了コードを決定
if [ ${ERROR_COUNT} -gt 0 ]; then
    exit 1
else
    exit 0
fi
