#!/usr/bin/env python3
"""
km-notebooklm: 透過 NotebookLM MCP 拉取筆記本內容，建立知識圖譜。

需要先安裝 notebooklm-mcp：
    npm install -g notebooklm-mcp

第一次使用會開啟瀏覽器讓你登入 Google 帳號。

用法：
    python3 km-notebooklm.py                    # 互動式選擇筆記本
    python3 km-notebooklm.py --list              # 列出所有筆記本
    python3 km-notebooklm.py --notebook "筆記本名稱"  # 指定筆記本
    python3 km-notebooklm.py --all               # 掃描所有筆記本
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


WIKI_DIR = Path(__file__).parent / 'wiki'
MCP_CMD = ['npx', 'notebooklm-mcp@latest']


def call_mcp(tool_name, arguments=None):
    """透過 stdio 呼叫 NotebookLM MCP tool"""
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {}
        }
    }

    try:
        proc = subprocess.run(
            MCP_CMD + ['--oneshot'],
            input=json.dumps(request),
            capture_output=True, text=True, timeout=120
        )

        if proc.returncode != 0:
            # 有些 MCP server 用 stderr 輸出 log，但 stdout 有結果
            pass

        # 嘗試解析 JSON-RPC 回應
        output = proc.stdout.strip()
        if not output:
            return None

        # MCP 可能輸出多行，取最後一個 JSON
        for line in reversed(output.split('\n')):
            line = line.strip()
            if line.startswith('{'):
                try:
                    resp = json.loads(line)
                    if 'result' in resp:
                        content = resp['result'].get('content', [])
                        if content and content[0].get('text'):
                            return content[0]['text']
                    if 'error' in resp:
                        print(f"  ✗ MCP 錯誤: {resp['error']}", file=sys.stderr)
                        return None
                except json.JSONDecodeError:
                    continue

        return output

    except subprocess.TimeoutExpired:
        print(f"  ✗ MCP 呼叫逾時: {tool_name}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("✗ 找不到 npx，請先安裝 Node.js", file=sys.stderr)
        print("  brew install node", file=sys.stderr)
        sys.exit(1)


def call_mcp_interactive(tool_name, arguments=None):
    """用更簡單的方式呼叫 MCP：直接用 subprocess 跑 CLI 指令"""
    cmd = ['npx', 'notebooklm-mcp@latest']

    if tool_name == 'list_notebooks':
        cmd.append('list')
    elif tool_name == 'setup_auth':
        cmd.append('auth')
    elif tool_name == 'select_notebook':
        cmd.extend(['select', arguments.get('notebook_url', '')])
    elif tool_name == 'ask_question':
        cmd.extend(['ask', arguments.get('question', '')])
    else:
        cmd.extend([tool_name])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.stdout.strip() if proc.stdout else proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        print("✗ 找不到 npx，請先安裝 Node.js", file=sys.stderr)
        sys.exit(1)


def stable_id(text):
    """產生穩定的短 ID"""
    return hashlib.md5(text.encode()).hexdigest()[:10]


def ask_structured(question, retries=2):
    """問一個問題，期望回傳結構化文字"""
    for attempt in range(retries):
        result = call_mcp('ask_question', {'question': question})
        if result:
            return result
        time.sleep(2)
    return None


def extract_sources(notebook_name):
    """向 NotebookLM 問出所有來源文件"""
    print(f"\n📋 正在取得來源清單...")

    result = ask_structured(
        "請列出這個筆記本中的所有來源文件（sources），"
        "每個來源一行，格式：「來源名稱 | 類型」。"
        "類型請標示為：PDF、網頁、文字、影片、投影片 等。"
        "只列出名稱和類型，不要其他說明。"
    )

    if not result:
        print("  ✗ 無法取得來源清單")
        return []

    sources = []
    for line in result.strip().split('\n'):
        line = line.strip().lstrip('•-•·0123456789. ')
        if not line or line.startswith('#') or line.startswith('來源'):
            continue
        parts = line.split('|')
        name = parts[0].strip().strip('*').strip()
        stype = parts[1].strip() if len(parts) > 1 else '文件'
        if name:
            sources.append({'name': name, 'type': stype})

    print(f"  ✓ 找到 {len(sources)} 個來源")
    return sources


def analyze_source(source_name, index, total):
    """分析單一來源：取得摘要、關鍵字、標籤"""
    print(f"\n🔍 [{index}/{total}] 分析: {source_name}")

    result = ask_structured(
        f"針對來源「{source_name}」，請用以下 JSON 格式回答（不要 markdown code block，直接輸出 JSON）：\n"
        f'{{"summary": "200-400字的中文摘要", '
        f'"keywords": ["關鍵字1", "關鍵字2", ...最多10個], '
        f'"tags": ["#標籤1", "#標籤2", ...最多8個]}}'
    )

    if not result:
        print(f"  ✗ 分析失敗")
        return {'summary': '', 'keywords': [], 'tags': []}

    # 嘗試從回傳文字中提取 JSON
    try:
        # 可能包在 ```json ``` 裡
        text = result.strip()
        if '```' in text:
            import re
            m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
            if m:
                text = m.group(1)

        # 找第一個 { 到最後一個 }
        start = text.index('{')
        end = text.rindex('}') + 1
        data = json.loads(text[start:end])

        print(f"  ✓ 摘要: {len(data.get('summary', ''))}字 | "
              f"關鍵字: {len(data.get('keywords', []))} | "
              f"標籤: {len(data.get('tags', []))}")
        return data
    except (json.JSONDecodeError, ValueError):
        # JSON 解析失敗，把整段當摘要
        print(f"  △ 無法解析 JSON，使用原始文字作為摘要")
        return {'summary': result[:400], 'keywords': [], 'tags': []}


def analyze_relations(sources):
    """分析來源之間的關聯"""
    if len(sources) < 2:
        return []

    names = [s['name'] for s in sources[:30]]  # 最多 30 個
    names_str = '\n'.join(f'{i+1}. {n}' for i, n in enumerate(names))

    print(f"\n🔗 分析文件間關聯...")

    result = ask_structured(
        f"以下是筆記本中的來源文件：\n{names_str}\n\n"
        f"請分析哪些文件之間有內容關聯（主題相近、互相引用、互補等），"
        f"用以下格式列出，每行一組：\n"
        f"來源A名稱 | 來源B名稱 | 關聯描述\n"
        f"最多列出 20 組最重要的關聯。"
    )

    if not result:
        return []

    relations = []
    name_set = set(names)
    for line in result.strip().split('\n'):
        parts = line.split('|')
        if len(parts) >= 2:
            a = parts[0].strip().lstrip('•-·0123456789. ').strip('*').strip()
            b = parts[1].strip().strip('*').strip()
            desc = parts[2].strip() if len(parts) > 2 else ''
            # 模糊比對：找最相似的 source name
            a_match = find_closest(a, name_set)
            b_match = find_closest(b, name_set)
            if a_match and b_match and a_match != b_match:
                relations.append((a_match, b_match, desc))

    print(f"  ✓ 找到 {len(relations)} 組關聯")
    return relations


def find_closest(query, name_set):
    """模糊比對：找最相似的名稱"""
    query = query.lower().strip()
    # 完全比對
    for name in name_set:
        if name.lower() == query:
            return name
    # 包含比對
    for name in name_set:
        if query in name.lower() or name.lower() in query:
            return name
    return None


def type_to_category(stype):
    """將來源類型轉換為 km-viewer 類別"""
    stype = stype.lower()
    if 'pdf' in stype or '文' in stype or '文字' in stype:
        return '文件'
    if '投影片' in stype or 'ppt' in stype or '簡報' in stype:
        return '簡報'
    if '試算' in stype or 'excel' in stype or 'csv' in stype:
        return '試算表'
    if '影片' in stype or '影音' in stype or '音' in stype:
        return '影音'
    if '圖' in stype or 'image' in stype:
        return '圖片'
    if '網頁' in stype or 'url' in stype or 'http' in stype:
        return '文件'
    return '文件'


def build_graph(notebook_name, sources, analyses, relations):
    """建立 graph-data.json"""
    nodes = []
    edges = []
    id_map = {}  # name → id

    now = datetime.now().isoformat()
    categories = {}

    for i, src in enumerate(sources):
        nid = stable_id(f"nlm_{notebook_name}_{src['name']}")
        id_map[src['name']] = nid
        cat = type_to_category(src['type'])
        categories[cat] = categories.get(cat, 0) + 1

        analysis = analyses.get(src['name'], {})

        node = {
            'id': nid,
            'label': src['name'],
            'stem': src['name'],
            'type': 'file',
            'category': cat,
            'ext': '.nlm',
            'path': f"notebooklm://{notebook_name}/{src['name']}",
            'size': '',
            'modified': now[:10],
            'modifiedDate': now[:10],
            'modifiedMonth': now[:7],
            'tags': analysis.get('tags', []),
            'keywords': analysis.get('keywords', []),
            'summary': analysis.get('summary', ''),
            'source': 'notebooklm',
            'notebookName': notebook_name,
        }
        nodes.append(node)

    # 建立關聯邊
    for a_name, b_name, desc in relations:
        a_id = id_map.get(a_name)
        b_id = id_map.get(b_name)
        if a_id and b_id:
            edges.append({
                'source': a_id,
                'target': b_id,
                'type': 'semantic',
                'label': desc,
            })

    # 同類別的 sibling 邊
    by_cat = {}
    for src in sources:
        cat = type_to_category(src['type'])
        by_cat.setdefault(cat, []).append(id_map[src['name']])
    for cat, ids in by_cat.items():
        for i in range(len(ids)):
            for j in range(i+1, min(i+3, len(ids))):  # 最多連 2 個鄰居
                edges.append({'source': ids[i], 'target': ids[j], 'type': 'sibling'})

    graph = {
        'meta': {
            'rootDir': f'notebooklm://{notebook_name}',
            'rootName': f'📓 {notebook_name}',
            'scannedAt': now,
            'totalFiles': len(nodes),
            'totalFolders': 0,
            'categories': categories,
            'dateRange': {
                'min': now,
                'max': now,
            },
            'hasWiki': True,
            'source': 'notebooklm',
        },
        'nodes': nodes,
        'edges': edges,
    }

    return graph


def save_project(notebook_name, graph, analyses):
    """儲存為 km-viewer 專案"""
    safe_name = f"NLM_{notebook_name}"
    project_dir = WIKI_DIR / safe_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # 儲存 graph-data.json
    graph_path = project_dir / 'graph-data.json'
    with open(graph_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 圖譜已儲存: {graph_path}")

    # 為每個來源建立 .md 檔
    for node in graph['nodes']:
        name = node['label']
        analysis = analyses.get(name, {})
        md_name = name.replace('/', '_').replace('\\', '_') + '.md'
        md_path = project_dir / md_name
        node['wikiFile'] = md_name

        tags_str = ', '.join(analysis.get('tags', []))
        keywords_str = ', '.join(analysis.get('keywords', []))

        content = f"""---
title: "{name}"
source: "NotebookLM - {notebook_name}"
category: "{node['category']}"
tags: [{tags_str}]
keywords: [{keywords_str}]
---

# {name}

| 欄位 | 值 |
|------|-----|
| 來源 | NotebookLM: {notebook_name} |
| 類型 | {node['category']} |

## 摘要

{analysis.get('summary', '（無摘要）')}

## 關鍵字

{', '.join(analysis.get('keywords', []))}
"""
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(content)

    # 重新儲存 graph（更新了 wikiFile）
    with open(graph_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    # 建立 index.md
    index_path = project_dir / 'index.md'
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(f"# 📓 {notebook_name}\n\n")
        f.write(f"來源：Google NotebookLM\n\n")
        f.write(f"掃描時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"| 檔案 | 類型 | 關鍵字 |\n|------|------|--------|\n")
        for node in graph['nodes']:
            kw = ', '.join(node.get('keywords', [])[:5])
            f.write(f"| [[{node['label']}]] | {node['category']} | {kw} |\n")

    print(f"✓ Wiki 已建立: {project_dir} ({len(graph['nodes'])} 個檔案)")
    return safe_name


def main():
    parser = argparse.ArgumentParser(description='從 NotebookLM 建立知識圖譜')
    parser.add_argument('--list', action='store_true', help='列出所有筆記本')
    parser.add_argument('--notebook', type=str, help='指定筆記本名稱或 URL')
    parser.add_argument('--all', action='store_true', help='掃描所有筆記本')
    parser.add_argument('--auth', action='store_true', help='設定 Google 帳號認證')
    args = parser.parse_args()

    print("=" * 50)
    print("📓 KM-NotebookLM — 知識圖譜建立工具")
    print("=" * 50)

    # 認證
    if args.auth:
        print("\n🔑 啟動 Google 帳號認證...")
        result = call_mcp('setup_auth')
        print(result or "認證流程已啟動，請在瀏覽器中登入。")
        return

    # 列出筆記本
    if args.list:
        print("\n📚 正在取得筆記本清單...")
        result = call_mcp('list_notebooks')
        if result:
            print(result)
        else:
            print("✗ 無法取得筆記本清單。請先執行: python3 km-notebooklm.py --auth")
        return

    # 需要先選擇筆記本
    notebook_name = args.notebook

    if not notebook_name and not args.all:
        # 互動模式：列出筆記本讓使用者選擇
        print("\n📚 正在取得筆記本清單...")
        result = call_mcp('list_notebooks')
        if not result:
            print("✗ 無法取得筆記本清單。")
            print("  請先執行: python3 km-notebooklm.py --auth")
            return

        print(result)
        print()
        notebook_name = input("請輸入要掃描的筆記本名稱（或 URL）: ").strip()
        if not notebook_name:
            print("已取消。")
            return

    # 選擇筆記本
    print(f"\n📓 選擇筆記本: {notebook_name}")
    select_result = call_mcp('select_notebook', {'notebook_url': notebook_name})
    if select_result:
        print(f"  ✓ {select_result}")

    # 1. 取得來源清單
    sources = extract_sources(notebook_name)
    if not sources:
        print("\n✗ 沒有找到任何來源。請確認筆記本存在且有來源文件。")
        return

    # 2. 逐一分析每個來源
    analyses = {}
    for i, src in enumerate(sources):
        analysis = analyze_source(src['name'], i + 1, len(sources))
        analyses[src['name']] = analysis
        time.sleep(1)  # 避免太頻繁

    # 3. 分析關聯
    relations = analyze_relations(sources)

    # 4. 建立圖譜
    print(f"\n📊 建立知識圖譜...")
    graph = build_graph(notebook_name, sources, analyses, relations)

    # 5. 儲存專案
    project_name = save_project(notebook_name, graph, analyses)

    print(f"\n{'=' * 50}")
    print(f"✅ 完成！")
    print(f"   專案名稱: {project_name}")
    print(f"   來源數量: {len(sources)}")
    print(f"   關聯數量: {len(relations)}")
    print(f"\n   啟動伺服器查看：python3 km-server.py")
    print(f"   然後在設定中切換到「{project_name}」專案")
    print(f"{'=' * 50}")


if __name__ == '__main__':
    main()
