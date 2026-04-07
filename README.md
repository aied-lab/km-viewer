# Knowledge Graph — 本地知識管理系統

本地端知識圖譜工具，適用於公部門、醫療、企業等需要資安合規的環境。
資料完全不離開本機，不需要雲端服務。

## 功能

- 自動掃描資料夾，建立知識庫 .md 檔案
- 自動計算雙向連結（正向 + 反向）
- 互動式知識圖譜視覺化
- 點擊節點直接閱讀 Markdown 內容
- 支援開啟原始檔案（.docx、.pdf、.pptx）

## 使用方式

### 1. 建立反向連結

```bash
python3 build_backlinks.py
```

掃描 knowledge-base/ 資料夾裡所有 .md 檔案，自動更新反向連結。

### 2. 啟動本地伺服器

```bash
cd 你的資料夾 && python3 -m http.server 8765
```

### 3. 開啟知識圖譜

在瀏覽器開啟：

```
http://localhost:8765/knowledge-base/graph-view.html
```

## 檔案結構

```
knowledge-graph/
├── build_backlinks.py    # 自動計算反向連結
├── graph-view.html       # 知識圖譜視覺化介面
├── README.md
└── knowledge-base/       # 放你的 .md 知識庫
    ├── 00-INDEX.md
    ├── 01-xxx.md
    └── ...
```

## 開發路線

- [ ] build.py — 自動從 .docx/.pdf/.pptx 產生 .md（整合 Claude API）
- [ ] 關鍵字搜尋功能
- [ ] 語意搜尋（整合 Gemma 4 本地 LLM）
- [ ] standalone 模式（不需要 server，雙擊 HTML 即用）
- [ ] macOS App 打包

## 技術架構

- **前端**：純 HTML/CSS/JavaScript（無框架依賴）
- **Markdown 渲染**：marked.js
- **知識圖譜**：Canvas + 力導向佈局
- **後端**：Python（僅開發階段需要）
- **LLM**：Claude API（雲端）/ Gemma 4（本地，開發中）
