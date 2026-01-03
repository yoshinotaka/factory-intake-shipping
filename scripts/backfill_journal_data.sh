#!/bin/bash
#
# ジャーナルデータの過去データ一括取得スクリプト
#
# 使用方法:
#   ./backfill_journal_data.sh 2025-01-01 2025-12-12
#
# 処理内容:
#   1. 指定期間のジャーナルデータを半蔵サイトからダウンロード
#   2. ダウンロードしたファイルからCSVを生成
#   3. CSVをデータベースに取り込む
#

set -e

# 引数チェック
if [ $# -ne 2 ]; then
    echo "使用方法: $0 START_DATE END_DATE"
    echo "例: $0 2025-01-01 2025-12-12"
    exit 1
fi

START_DATE="$1"
END_DATE="$2"

KING_REQ_DIR="/var/www/html/king-req"
FACTORY_SHIPPING_DIR="/var/www/html/factory-intake-shipping"
PYTHON_KING="/var/www/html/king-req/venv-king/bin/python3"
PYTHON_FACTORY="/var/www/html/factory-intake-shipping/venv/bin/python"

LOG_FILE="/var/log/factory-shipping/backfill_$(date +%Y%m%d_%H%M%S).log"

echo "========================================"
echo "ジャーナルデータ一括取得開始"
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

    # ステップ1: ジャーナルデータをダウンロード
    echo "" | tee -a "$LOG_FILE"
    echo "[1/3] ジャーナルデータをダウンロード中..." | tee -a "$LOG_FILE"
    cd "$KING_REQ_DIR"

    if $PYTHON_KING hanjow_journal_downloader.py --date "$current" >> "$LOG_FILE" 2>&1; then
        echo "✓ ダウンロード成功" | tee -a "$LOG_FILE"
    else
        echo "✗ ダウンロード失敗（スキップ）" | tee -a "$LOG_FILE"
        current=$(date -I -d "$current + 1 day")
        continue
    fi

    # ステップ2: CSVを生成
    echo "" | tee -a "$LOG_FILE"
    echo "[2/3] CSVを生成中..." | tee -a "$LOG_FILE"

    if $PYTHON_KING extract_journal_data.py "$current" >> "$LOG_FILE" 2>&1; then
        echo "✓ CSV生成成功" | tee -a "$LOG_FILE"
    else
        echo "✗ CSV生成失敗（スキップ）" | tee -a "$LOG_FILE"
        current=$(date -I -d "$current + 1 day")
        continue
    fi

    # ステップ3: データベースに取り込む
    echo "" | tee -a "$LOG_FILE"
    echo "[3/3] データベースに取り込み中..." | tee -a "$LOG_FILE"
    cd "$FACTORY_SHIPPING_DIR"

    if $PYTHON_FACTORY run.py import-journal --date "$current" >> "$LOG_FILE" 2>&1; then
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
    sleep 2
done

echo "========================================"
echo "一括取得完了"
echo "========================================"
echo "ログファイル: $LOG_FILE"
echo ""
