#!/bin/bash
#
# 半蔵CSVデータの過去データ一括取得スクリプト
#
# 使用方法:
#   ./backfill_hanjow_csv.sh 2025-10-01 2025-11-10
#
# 処理内容:
#   1. 指定期間の半蔵CSVを半蔵サイトからダウンロード
#   2. ダウンロードしたCSVをIntakeItemテーブルに取り込む
#

set -e

# 引数チェック
if [ $# -ne 2 ]; then
    echo "使用方法: $0 START_DATE END_DATE"
    echo "例: $0 2025-10-01 2025-11-10"
    exit 1
fi

START_DATE="$1"
END_DATE="$2"

KING_REQ_DIR="/var/www/html/king-req"
FACTORY_SHIPPING_DIR="/var/www/html/factory-intake-shipping"
PYTHON_KING="/var/www/html/king-req/venv-king/bin/python3"
PYTHON_FACTORY="/var/www/html/factory-intake-shipping/venv/bin/python"

LOG_FILE="/var/log/factory-shipping/backfill_hanjow_$(date +%Y%m%d_%H%M%S).log"

echo "========================================"
echo "半蔵CSV一括取得開始"
echo "========================================"
echo "開始日: $START_DATE"
echo "終了日: $END_DATE"
echo "ログファイル: $LOG_FILE"
echo "========================================"
echo ""

# ログディレクトリ作成
mkdir -p /var/log/factory-shipping

# 日付を生成（START_DATEからEND_DATEまで）
current="$START_DATE"
end="$END_DATE"

while [ "$current" != "$(date -I -d "$end + 1 day")" ]; do
    echo "========================================" | tee -a "$LOG_FILE"
    echo "処理日付: $current" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"

    # 曜日を確認（木曜日はスキップ）
    weekday=$(date -d "$current" +%u)  # 1=月曜, 4=木曜, 7=日曜
    if [ "$weekday" -eq 4 ]; then
        echo "木曜日（定休日）のためスキップ: $current" | tee -a "$LOG_FILE"
        current=$(date -I -d "$current + 1 day")
        continue
    fi

    # ステップ1: 半蔵CSVをダウンロード
    echo "" | tee -a "$LOG_FILE"
    echo "[1/2] 半蔵CSVをダウンロード中..." | tee -a "$LOG_FILE"
    cd "$KING_REQ_DIR"

    if timeout 180 $PYTHON_KING hanjow_csv_downloader.py --date "$current" >> "$LOG_FILE" 2>&1; then
        echo "✓ ダウンロード成功" | tee -a "$LOG_FILE"
    else
        echo "✗ ダウンロード失敗またはタイムアウト（スキップ）" | tee -a "$LOG_FILE"
        current=$(date -I -d "$current + 1 day")
        continue
    fi

    # ステップ2: CSVをデータベースに取り込む
    echo "" | tee -a "$LOG_FILE"
    echo "[2/2] CSVをデータベースに取り込み中..." | tee -a "$LOG_FILE"
    cd "$FACTORY_SHIPPING_DIR"

    # CSVファイルのパスを確認
    csv_date=$(date -d "$current" +%Y%m%d)
    csv_file="$KING_REQ_DIR/downloads_hanjow/hanjow_${csv_date}.csv"

    if [ ! -f "$csv_file" ]; then
        echo "✗ CSVファイルが見つかりません: $csv_file" | tee -a "$LOG_FILE"
        current=$(date -I -d "$current + 1 day")
        continue
    fi

    # run.py import-hanjow --date でCSVを取り込む
    if $PYTHON_FACTORY run.py import-hanjow --date "$current" >> "$LOG_FILE" 2>&1; then
        echo "✓ データベース取り込み成功" | tee -a "$LOG_FILE"
    else
        echo "✗ データベース取り込み失敗" | tee -a "$LOG_FILE"
    fi

    echo "" | tee -a "$LOG_FILE"
    echo "✓ $current の処理完了" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # 次の日付へ
    current=$(date -I -d "$current + 1 day")

    # サーバー負荷軽減のため少し待機
    sleep 3
done

echo "========================================"
echo "一括取得完了"
echo "========================================"
echo "ログファイル: $LOG_FILE"
echo ""
