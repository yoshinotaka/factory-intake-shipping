#!/bin/bash
################################################################################
# hanjow CSV 自動取り込みスクリプト
#
# 説明:
#   指定されたディレクトリから hanjow CSV ファイルを自動的に取り込みます。
#   取得できない日があっても、遡って取得した場合でも、重複を防いで
#   差分のみを取り込みます。
#
# 使用方法:
#   ./auto_import_hanjow.sh [YYYY-MM-DD]
#
#   引数なし: 今日の日付のCSVを取り込み
#   引数あり: 指定日付のCSVを取り込み
#
# cron設定例:
#   # 毎日22:35に自動実行（CSVは22:30に配置される想定）
#   35 22 * * * /var/www/html/factory-intake-shipping/scripts/auto_import_hanjow.sh >> /var/log/factory-shipping/auto-import.log 2>&1
#
################################################################################

# 並行起動防止: cron二重登録や手動実行の重複が起きても DB に重複を作らないよう
# flock で排他制御する。既に動作中なら即座に exit 0 する。
LOCK_FILE="/tmp/factory-auto-import.lock"
exec 9> "${LOCK_FILE}"
if ! flock -n 9; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] auto_import_hanjow.sh: 別プロセスが実行中のためスキップ" \
        | tee -a /var/log/factory-shipping/auto-import.log
    exit 0
fi

# 設定
PROJECT_DIR="/var/www/html/factory-intake-shipping"
VENV_DIR="${PROJECT_DIR}/venv"
PYTHON="${VENV_DIR}/bin/python"
LOG_DIR="/var/log/factory-shipping"
CSV_DIR="/var/www/html/king-req/downloads_hanjow"

# ログファイル
LOG_FILE="${LOG_DIR}/auto-import.log"
ERROR_LOG="${LOG_DIR}/auto-import-error.log"

# ログディレクトリが存在しない場合は作成
mkdir -p "${LOG_DIR}"

# ログ関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

error_log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "${ERROR_LOG}" >&2
}

# メイン処理開始
log "========================================"
log "hanjow CSV 自動取り込み開始"
log "========================================"

# 日付引数の処理
if [ -n "$1" ]; then
    TARGET_DATE="$1"
    log "指定日付: ${TARGET_DATE}"
else
    TARGET_DATE=$(date '+%Y-%m-%d')
    log "対象日付: ${TARGET_DATE} (今日)"
fi

# CSVファイルパスを生成
DATE_YYYYMMDD=$(echo "${TARGET_DATE}" | sed 's/-//g')
CSV_FILE="${CSV_DIR}/hanjow_${DATE_YYYYMMDD}.csv"

log "CSVファイル: ${CSV_FILE}"

# CSVファイルの存在チェック
if [ ! -f "${CSV_FILE}" ]; then
    error_log "CSVファイルが見つかりません: ${CSV_FILE}"
    log "スキップします（取得できない日の可能性があります）"
    log "========================================"
    exit 0  # エラー終了ではなく正常終了（取得できない日は正常）
fi

# ファイルサイズチェック（0バイトの場合はスキップ）
FILE_SIZE=$(stat -c%s "${CSV_FILE}" 2>/dev/null || echo "0")
if [ "${FILE_SIZE}" -eq 0 ]; then
    error_log "CSVファイルが空です: ${CSV_FILE}"
    log "スキップします"
    log "========================================"
    exit 0
fi

log "ファイルサイズ: ${FILE_SIZE} バイト"

# Python仮想環境の存在チェック
if [ ! -f "${PYTHON}" ]; then
    error_log "Python仮想環境が見つかりません: ${PYTHON}"
    log "========================================"
    exit 1
fi

# プロジェクトディレクトリに移動
cd "${PROJECT_DIR}" || {
    error_log "プロジェクトディレクトリに移動できません: ${PROJECT_DIR}"
    exit 1
}

# CSV取り込み実行
log "CSV取り込みを開始..."
"${PYTHON}" run.py import-hanjow --date "${TARGET_DATE}" 2>&1 | tee -a "${LOG_FILE}"
RESULT=$?

if [ ${RESULT} -eq 0 ]; then
    log "CSV取り込みが正常に完了しました"
    log "========================================"
    exit 0
else
    error_log "CSV取り込み中にエラーが発生しました（終了コード: ${RESULT}）"
    log "========================================"
    exit ${RESULT}
fi
