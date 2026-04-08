#!/usr/bin/env python3
"""
km-scan: 掃描指定目錄，產生 graph-data.json 供 graph-view.html 使用。

用法：
    python3 km-scan.py /path/to/your/folder
    python3 km-scan.py /path/to/your/folder -o /path/to/output
"""

import argparse
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path

# 支援的檔案類型與分類
FILE_CATEGORIES = {
    '文件': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.md'},
    '簡報': {'.ppt', '.pptx', '.key', '.odp'},
    '試算表': {'.xls', '.xlsx', '.csv', '.ods', '.numbers'},
    '圖片': {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.bmp', '.webp', '.tiff'},
    '影音': {'.mp4', '.mov', '.avi', '.mkv', '.mp3', '.wav', '.flac', '.m4a'},
    '程式碼': {'.py', '.js', '.ts', '.html', '.css', '.json', '.xml', '.yaml', '.yml',
               '.java', '.c', '.cpp', '.h', '.go', '.rs', '.rb', '.php', '.sh', '.sql'},
    '壓縮檔': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'},
}

# 副檔名 → 分類 反查表
EXT_TO_CATEGORY = {}
for cat, exts in FILE_CATEGORIES.items():
    for ext in exts:
        EXT_TO_CATEGORY[ext] = cat


def get_file_category(ext: str) -> str:
    return EXT_TO_CATEGORY.get(ext.lower(), '其他')


def stable_id(path: str) -> str:
    """產生穩定的短 ID"""
    return hashlib.md5(path.encode('utf-8')).hexdigest()[:10]


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def scan_directory(root_dir: str) -> dict:
    """掃描目錄，回傳 graph-data 結構"""
    root = Path(root_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"目錄不存在：{root}")

    nodes = []
    folder_nodes = {}  # path -> node_id
    file_count = 0

    # 先建立根目錄節點
    root_id = stable_id(str(root))
    nodes.append({
        'id': root_id,
        'label': root.name,
        'type': 'folder',
        'category': '資料夾',
        'path': str(root),
        'depth': 0,
        'children': [],
        'fileCount': 0,
    })
    folder_nodes[str(root)] = root_id

    # 遞迴掃描
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳過隱藏目錄和常見非必要目錄
        dirnames[:] = [d for d in dirnames
                       if not d.startswith('.')
                       and d not in {'node_modules', '__pycache__', '.git', 'venv', '.venv'}]

        current_path = Path(dirpath).resolve()
        depth = len(current_path.relative_to(root).parts)

        # 建立子目錄節點
        if str(current_path) != str(root):
            folder_id = stable_id(str(current_path))
            parent_path = str(current_path.parent)
            parent_id = folder_nodes.get(parent_path, root_id)

            nodes.append({
                'id': folder_id,
                'label': current_path.name,
                'type': 'folder',
                'category': '資料夾',
                'path': str(current_path),
                'depth': depth,
                'parent': parent_id,
                'children': [],
                'fileCount': 0,
            })
            folder_nodes[str(current_path)] = folder_id

            # 加入父目錄的 children
            for n in nodes:
                if n['id'] == parent_id:
                    n['children'].append(folder_id)
                    break

        # 處理檔案
        current_folder_id = folder_nodes.get(str(current_path), root_id)
        for fname in sorted(filenames):
            if fname.startswith('.'):
                continue

            fpath = current_path / fname
            try:
                stat = fpath.stat()
            except (PermissionError, OSError):
                continue

            ext = fpath.suffix.lower()
            category = get_file_category(ext)
            rel_path = str(fpath.relative_to(root))
            file_id = stable_id(str(fpath))
            modified = datetime.fromtimestamp(stat.st_mtime)

            nodes.append({
                'id': file_id,
                'label': fname,
                'type': 'file',
                'category': category,
                'ext': ext,
                'path': str(fpath),
                'relativePath': rel_path,
                'size': stat.st_size,
                'sizeFormatted': format_size(stat.st_size),
                'modified': modified.isoformat(),
                'modifiedDate': modified.strftime('%Y-%m-%d'),
                'modifiedYear': modified.year,
                'modifiedMonth': modified.strftime('%Y-%m'),
                'parent': current_folder_id,
                'depth': depth + 1,
            })

            # 更新父目錄的 children 和 fileCount
            for n in nodes:
                if n['id'] == current_folder_id:
                    n['children'].append(file_id)
                    n['fileCount'] += 1
                    break

            file_count += 1

    # 建立 edges（資料夾 → 子項目）
    edges = []
    for n in nodes:
        if 'parent' in n:
            edges.append({
                'source': n['parent'],
                'target': n['id'],
                'type': 'contains',
            })

    # 建立同類檔案之間的弱連結（同一資料夾內的同類型檔案）
    from collections import defaultdict
    folder_category_files = defaultdict(list)
    for n in nodes:
        if n['type'] == 'file':
            key = (n['parent'], n['category'])
            folder_category_files[key].append(n['id'])

    for (folder_id, category), file_ids in folder_category_files.items():
        if len(file_ids) > 1 and len(file_ids) <= 20:
            for i in range(len(file_ids)):
                for j in range(i + 1, len(file_ids)):
                    edges.append({
                        'source': file_ids[i],
                        'target': file_ids[j],
                        'type': 'sibling',
                    })

    # 統計資訊
    categories = {}
    for n in nodes:
        if n['type'] == 'file':
            cat = n['category']
            categories[cat] = categories.get(cat, 0) + 1

    folders = [n for n in nodes if n['type'] == 'folder']

    # 收集時間範圍
    file_nodes = [n for n in nodes if n['type'] == 'file']
    dates = [n['modified'] for n in file_nodes]
    date_range = {'min': min(dates), 'max': max(dates)} if dates else None

    graph_data = {
        'meta': {
            'rootDir': str(root),
            'rootName': root.name,
            'scannedAt': datetime.now().isoformat(),
            'totalFiles': file_count,
            'totalFolders': len(folders),
            'categories': categories,
            'dateRange': date_range,
        },
        'nodes': nodes,
        'edges': edges,
    }

    return graph_data


def main():
    parser = argparse.ArgumentParser(description='掃描目錄，產生知識圖譜資料')
    parser.add_argument('directory', help='要掃描的目錄路徑')
    parser.add_argument('-o', '--output', default='.', help='輸出目錄（預設為當前目錄）')
    args = parser.parse_args()

    print(f'🔍 掃描目錄：{args.directory}')
    graph_data = scan_directory(args.directory)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 輸出到 wiki/專案名/ 子目錄
    project_name = Path(args.directory).resolve().name
    project_dir = output_dir / 'wiki' / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    project_graph = project_dir / 'graph-data.json'
    # 如果已有 wiki 版（hasWiki=True），不覆蓋
    skip_write = False
    if project_graph.exists():
        try:
            existing = json.load(open(project_graph, encoding='utf-8'))
            if existing.get('meta', {}).get('hasWiki'):
                skip_write = True
                print(f'   ⏭️  已有 Wiki 版 graph-data.json，不覆蓋')
        except Exception:
            pass
    if not skip_write:
        with open(project_graph, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)

    # 根目錄的 graph-data.json 由 switch_project 負責，這裡不寫

    meta = graph_data['meta']
    print(f'✅ 完成！')
    print(f'   📁 資料夾：{meta["totalFolders"]} 個')
    print(f'   📄 檔案：{meta["totalFiles"]} 個')
    print(f'   📊 分類：{meta["categories"]}')
    print(f'   💾 輸出：{output_file}')
    print(f'\n啟動方式：')
    print(f'   cd {output_dir} && python3 -m http.server 8765')
    print(f'   然後開啟 http://localhost:8765/graph-view.html')


if __name__ == '__main__':
    main()
