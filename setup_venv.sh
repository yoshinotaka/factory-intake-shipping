#!/bin/bash
#
# 新・出荷システム - 仮想環境セットアップスクリプト
#
# 使い方:
#   bash setup_venv.sh [PYTHON_BIN]
#
# 例:
#   bash setup_venv.sh python3.10
#   bash setup_venv.sh python3.9
#

set -e  # エラー時に即座に終了

# プロジェクトルート
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# Python バイナリの指定（引数で渡すか、デフォルトは python3）
PYTHON_BIN="${1:-python3}"

echo "==============================================="
echo "  新・出荷システム 仮想環境セットアップ"
echo "==============================================="
echo ""
echo "プロジェクトルート: $PROJECT_ROOT"
echo "Python バイナリ: $PYTHON_BIN"
echo ""

# Python バージョン確認
echo "[1/5] Python バージョン確認..."
$PYTHON_BIN --version

# venv が既に存在する場合は確認
if [ -d "venv" ]; then
    echo ""
    echo "警告: venv ディレクトリが既に存在します"
    read -p "削除して再作成しますか? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "既存の venv を削除しています..."
        rm -rf venv
    else
        echo "セットアップを中止しました"
        exit 1
    fi
fi

# venv 作成
echo ""
echo "[2/5] 仮想環境を作成しています..."
$PYTHON_BIN -m venv venv

# venv 有効化
echo ""
echo "[3/5] 仮想環境を有効化しています..."
source venv/bin/activate

# pip アップグレード
echo ""
echo "[4/5] pip をアップグレードしています..."
pip install --upgrade pip

# パッケージインストール
echo ""
echo "[5/5] 必要なパッケージをインストールしています..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "requirements.txt が見つかりません。基本パッケージをインストールします..."
    pip install \
        flask \
        flask-sqlalchemy \
        sqlalchemy \
        alembic \
        python-dotenv \
        gunicorn \
        pymysql \
        cryptography

    # requirements.txt を生成
    pip freeze > requirements.txt
    echo "requirements.txt を生成しました"
fi

echo ""
echo "==============================================="
echo "  セットアップ完了！"
echo "==============================================="
echo ""
echo "次のコマンドで仮想環境を有効化してください:"
echo "  source venv/bin/activate"
echo ""
echo "Alembic を初期化するには:"
echo "  alembic init migrations"
echo ""
echo "開発サーバーを起動するには:"
echo "  python run.py"
echo ""
