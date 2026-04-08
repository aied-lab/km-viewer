#!/bin/bash
# KM Viewer 一鍵啟動
# 雙擊此檔案即可啟動

cd "$(dirname "$0")"

# 檢查 graph-data.json 是否存在
if [ ! -f "graph-data.json" ]; then
    echo ""
    echo "⚠️  尚未掃描任何目錄！"
    echo ""
    echo "請輸入要掃描的資料夾路徑（可以把資料夾拖進來）："
    read -r TARGET_DIR

    if [ -z "$TARGET_DIR" ]; then
        echo "❌ 未輸入路徑，結束。"
        exit 1
    fi

    # 移除可能的引號和尾部空白
    TARGET_DIR=$(echo "$TARGET_DIR" | sed "s/^'//" | sed "s/'$//" | sed 's/^ *//' | sed 's/ *$//' | sed 's/\\//g')

    if [ ! -d "$TARGET_DIR" ]; then
        echo "❌ 目錄不存在：$TARGET_DIR"
        exit 1
    fi

    echo ""
    echo "要使用 AI 分析文件內容嗎？（需要 API Key，會產生費用）"
    echo "  1) 是，用 AI 分析（推薦，產生摘要和語意連結）"
    echo "  2) 否，只掃描檔案結構（快速，免費）"
    echo ""
    read -p "請選擇 (1/2): " CHOICE

    if [ "$CHOICE" = "1" ]; then
        python3 km-build.py "$TARGET_DIR"
    else
        python3 km-scan.py "$TARGET_DIR"
    fi

    echo ""
fi

echo ""
echo "🚀 啟動 KM Viewer..."
echo "   瀏覽器將自動開啟"
echo "   關閉此視窗即可停止伺服器"
echo ""

# 延遲 1 秒後自動開啟瀏覽器
(sleep 1 && open "http://localhost:8765/graph-view.html") &

python3 km-server.py
