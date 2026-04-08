# KM Viewer — 本地知識圖譜工具

掃描任意資料夾，自動產生互動式知識圖譜。
資料完全不離開本機，不需要雲端服務。

## 快速開始

### 1. 掃描目錄

```bash
python3 km-scan.py /path/to/your/folder
```

會在當前目錄產生 `graph-data.json`。

### 2. 啟動本地伺服器

```bash
python3 -m http.server 8765
```

### 3. 開啟知識圖譜

瀏覽器開啟 `http://localhost:8765/graph-view.html`

## 功能

- **三種維度切換**：檔案類型 / 資料夾結構 / 時間軸
- **即時搜尋**：輸入檔名快速定位
- **圖例篩選**：點擊圖例只顯示特定分類
- **時間滑桿**：拖曳篩選特定時間範圍的檔案
- **點擊開檔**：節點點擊後可開啟原始檔案
- **拖拉縮放**：滑鼠拖拉平移、滾輪縮放

## 支援的檔案類型

| 分類 | 副檔名 |
|------|--------|
| 文件 | .pdf .doc .docx .txt .rtf .odt .md |
| 簡報 | .ppt .pptx .key .odp |
| 試算表 | .xls .xlsx .csv .ods .numbers |
| 圖片 | .jpg .jpeg .png .gif .svg .bmp .webp |
| 影音 | .mp4 .mov .avi .mkv .mp3 .wav .flac |
| 程式碼 | .py .js .ts .html .css .json .yaml 等 |
| 壓縮檔 | .zip .rar .7z .tar .gz |

## 進階用法

```bash
# 指定輸出目錄
python3 km-scan.py /path/to/folder -o /path/to/output

# 掃描後把 graph-view.html 複製到輸出目錄一起使用
cp graph-view.html /path/to/output/
```

## 檔案結構

```
km-viewer/
├── km-scan.py          # CLI 掃描工具
├── graph-view.html     # 知識圖譜視覺化介面
├── graph-data.json     # 掃描產生的資料（自動產生）
└── README.md
```

## 開發路線

- [ ] LLM 解析檔案內容（Claude API），產生摘要與語意連結
- [ ] 關鍵字搜尋
- [ ] 語意搜尋（本地 LLM）
- [ ] macOS App 打包

## 技術架構

- **前端**：純 HTML/CSS/JavaScript（無框架依賴）
- **後端**：Python CLI（僅掃描階段需要）
- **圖譜引擎**：Canvas + 力導向佈局
