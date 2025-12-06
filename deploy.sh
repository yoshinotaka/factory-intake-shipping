#!/bin/bash
#
# deploy.sh - Factory Intake & Shipping System デプロイスクリプト
#
# 使い方: ./deploy.sh
#

set -e  # エラーで停止

# カラー出力
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT_DIR="/var/www/html/factory-intake-shipping"
SERVICE_NAME="factory-shipping"
ERROR_LOG="/var/log/factory-shipping/error.log"

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Factory Shipping System - デプロイ開始  ${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# プロジェクトディレクトリに移動
cd "$PROJECT_DIR" || exit 1

# 1. 現在のブランチとステータスを確認
echo -e "${YELLOW}[1/6]${NC} Gitの状態を確認中..."
git status
echo ""

# 2. 最新のコードを取得
echo -e "${YELLOW}[2/6]${NC} GitHubから最新のコードを取得中..."
git fetch origin
echo ""

# 3. ローカルの変更があるか確認
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}警告: ローカルに未コミットの変更があります${NC}"
    echo "以下のファイルが変更されています:"
    git status --short
    echo ""
    read -p "続行しますか? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "デプロイを中止しました"
        exit 1
    fi
fi

# 4. プル実行
echo -e "${YELLOW}[3/6]${NC} 最新のコードをマージ中..."
git pull origin main
echo ""

# 5. 依存関係の更新（requirements.txtが変更されている場合）
if git diff HEAD@{1} --name-only | grep -q "requirements.txt"; then
    echo -e "${YELLOW}[4/6]${NC} requirements.txtが更新されています。依存関係をインストール中..."
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    echo ""
else
    echo -e "${YELLOW}[4/6]${NC} 依存関係の更新は不要です"
    echo ""
fi

# 6. サービスを再起動
echo -e "${YELLOW}[5/6]${NC} ${SERVICE_NAME}サービスを再起動中..."
sudo systemctl restart "$SERVICE_NAME"
echo ""

# 7. サービスの状態を確認
echo -e "${YELLOW}[6/6]${NC} サービスの状態を確認中..."
sleep 3

if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo -e "${GREEN}✓ デプロイ成功!${NC}"
    echo -e "${GREEN}✓ サービスは正常に稼働しています${NC}"
    echo ""
    
    # サービスの簡易ステータス表示
    sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -15
    echo ""
    
    # 最新のエラーログを確認
    echo -e "${YELLOW}最新のエラーログ（最後の10行）:${NC}"
    sudo tail -10 "$ERROR_LOG" 2>/dev/null || echo "ログファイルが見つかりません"
    
else
    echo -e "${RED}✗ エラー: サービスの起動に失敗しました${NC}"
    echo ""
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    echo ""
    echo -e "${YELLOW}エラーログを確認してください:${NC}"
    sudo tail -50 "$ERROR_LOG"
    exit 1
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  デプロイ完了                          ${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
