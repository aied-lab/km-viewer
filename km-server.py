#!/usr/bin/env python3
"""
km-server: 本地知識圖譜伺服器。
提供靜態檔案服務 + API 端點（開檔、讀檔、查詢、模型切換）。

用法：
    python3 km-server.py
    python3 km-server.py --port 8765
"""

import argparse
import json
import os
import subprocess
import platform
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import urllib.request

from dotenv import load_dotenv

# 載入 .env
load_dotenv(Path(__file__).parent / '.env')

WIKI_DIR = Path(__file__).parent / 'wiki'

# 當前 LLM 設定（可在執行時透過 API 切換）
current_provider = os.getenv('LLM_PROVIDER', 'claude-sonnet')


class KMHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/open':
            self.handle_open(parsed)
        elif parsed.path == '/api/read':
            self.handle_read(parsed)
        elif parsed.path == '/api/models':
            self.handle_get_models()
        elif parsed.path == '/api/projects':
            self.handle_list_projects()
        elif parsed.path == '/api/browse':
            self.handle_browse(parsed)
        elif parsed.path == '/api/download':
            self.handle_download(parsed)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/query':
            self.handle_query()
        elif parsed.path == '/api/set-model':
            self.handle_set_model()
        elif parsed.path == '/api/scan':
            self.handle_scan()
        elif parsed.path == '/api/switch-project':
            self.handle_switch_project()
        else:
            self.send_json(404, {'error': 'Not found'})

    def handle_open(self, parsed):
        params = parse_qs(parsed.query)
        file_path = params.get('path', [None])[0]
        if not file_path:
            self.send_json(400, {'error': '缺少 path 參數'}); return
        if not os.path.exists(file_path):
            self.send_json(404, {'error': f'檔案不存在：{file_path}'}); return
        try:
            system = platform.system()
            if system == 'Darwin':
                result = subprocess.run(['open', file_path], capture_output=True, text=True, timeout=5)
            elif system == 'Windows':
                os.startfile(file_path); result = None
            else:
                result = subprocess.run(['xdg-open', file_path], capture_output=True, text=True, timeout=5)
            if result and result.returncode != 0:
                self.send_json(500, {'error': result.stderr.strip() or '開啟失敗'})
            else:
                self.send_json(200, {'ok': True, 'path': file_path})
                print(f'📂 開啟：{file_path}')
        except Exception as e:
            self.send_json(500, {'error': str(e)})

    def handle_read(self, parsed):
        params = parse_qs(parsed.query)
        file_path = params.get('path', [None])[0]
        if not file_path:
            self.send_json(400, {'error': '缺少 path 參數'}); return
        if not os.path.exists(file_path):
            self.send_json(404, {'error': f'檔案不存在：{file_path}'}); return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            body = content.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_json(500, {'error': str(e)})

    def handle_get_models(self):
        """回傳可用的 LLM 模型列表"""
        global current_provider
        has_anthropic = bool(os.getenv('ANTHROPIC_API_KEY'))
        models = [
            {'id': 'claude-sonnet', 'name': 'Claude Sonnet', 'type': 'cloud', 'available': has_anthropic},
            {'id': 'claude-haiku', 'name': 'Claude Haiku (快速)', 'type': 'cloud', 'available': has_anthropic},
            {'id': 'claude-opus', 'name': 'Claude Opus (強)', 'type': 'cloud', 'available': has_anthropic},
            {'id': 'gemini-flash', 'name': 'Gemini 2.5 Flash (快速)', 'type': 'cloud', 'available': bool(os.getenv('GOOGLE_API_KEY'))},
            {'id': 'gemini-pro', 'name': 'Gemini 2.5 Pro', 'type': 'cloud', 'available': bool(os.getenv('GOOGLE_API_KEY'))},
            {'id': 'gemini-3-pro', 'name': 'Gemini 3 Pro (最新)', 'type': 'cloud', 'available': bool(os.getenv('GOOGLE_API_KEY'))},
            {'id': 'gemini-3-flash', 'name': 'Gemini 3 Flash', 'type': 'cloud', 'available': bool(os.getenv('GOOGLE_API_KEY'))},
            {'id': 'openai', 'name': 'GPT-4o', 'type': 'cloud', 'available': bool(os.getenv('OPENAI_API_KEY'))},
        ]
        # 檢查 Ollama
        ollama_models = get_ollama_models()
        for m in ollama_models:
            models.append({'id': f'ollama:{m}', 'name': f'{m} (本地)', 'type': 'local', 'available': True})

        self.send_json(200, {'models': models, 'current': current_provider})

    def handle_set_model(self):
        """切換 LLM 模型"""
        global current_provider
        try:
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            data = json.loads(body.decode('utf-8'))
            model_id = data.get('model', '')
            if not model_id:
                self.send_json(400, {'error': '缺少 model 參數'}); return
            current_provider = model_id
            print(f'🔄 切換模型：{current_provider}')
            self.send_json(200, {'ok': True, 'current': current_provider})
        except Exception as e:
            self.send_json(500, {'error': str(e)})

    def handle_browse(self, parsed):
        """瀏覽目錄結構"""
        params = parse_qs(parsed.query)
        dir_path = params.get('path', [os.path.expanduser('~')])[0]

        if not os.path.isdir(dir_path):
            self.send_json(400, {'error': f'不是目錄：{dir_path}'})
            return

        try:
            items = []
            parent = str(Path(dir_path).parent)
            for name in sorted(os.listdir(dir_path)):
                if name.startswith('.'):
                    continue
                full = os.path.join(dir_path, name)
                if os.path.isdir(full):
                    # 計算子項目數
                    try:
                        count = len([f for f in os.listdir(full) if not f.startswith('.')])
                    except PermissionError:
                        count = -1
                    items.append({'name': name, 'path': full, 'type': 'dir', 'count': count})

            self.send_json(200, {
                'current': dir_path,
                'parent': parent if parent != dir_path else None,
                'items': items,
            })
        except PermissionError:
            self.send_json(403, {'error': '沒有存取權限'})
        except Exception as e:
            self.send_json(500, {'error': str(e)})

    def handle_download(self, parsed):
        """下載檔案（串流傳輸）"""
        params = parse_qs(parsed.query)
        file_path = params.get('path', [None])[0]
        if not file_path or not os.path.isfile(file_path):
            self.send_json(404, {'error': '檔案不存在'})
            return
        try:
            import mimetypes
            import urllib.parse
            filename = os.path.basename(file_path)
            # 中文檔名 URL 編碼
            encoded_name = urllib.parse.quote(filename)
            mime, _ = mimetypes.guess_type(file_path)
            if not mime:
                mime = 'application/octet-stream'
            file_size = os.path.getsize(file_path)
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{encoded_name}")
            self.send_header('Content-Length', file_size)
            self.end_headers()
            # 串流寫入，避免大檔案佔滿記憶體
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 用戶取消下載
        except Exception as e:
            try:
                self.send_json(500, {'error': str(e)})
            except Exception:
                pass

    def handle_list_projects(self):
        """列出所有已掃描的專案"""
        projects = list_projects()
        self.send_json(200, {'projects': projects, 'current': get_current_project()})

    def handle_scan(self):
        """掃描新目錄（在背景執行 km-build.py 或 km-scan.py）"""
        try:
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            data = json.loads(body.decode('utf-8'))
            directory = data.get('directory', '').strip()
            use_llm = data.get('useLlm', False)
            model = data.get('model', 'claude-sonnet')

            if not directory:
                self.send_json(400, {'error': '請輸入目錄路徑'}); return
            if not os.path.isdir(directory):
                self.send_json(400, {'error': f'目錄不存在：{directory}'}); return

            script_dir = Path(__file__).parent
            if use_llm:
                cmd = ['python3', str(script_dir / 'km-build.py'), directory, '-o', str(script_dir), '--model', model]
            else:
                cmd = ['python3', str(script_dir / 'km-scan.py'), directory, '-o', str(script_dir)]

            project_name = Path(directory).name
            print(f'🔄 開始掃描：{directory} (LLM: {use_llm})')

            # 背景執行
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _ = proc.communicate(timeout=600)

            if proc.returncode == 0:
                # 切換到新專案
                switch_project(project_name)
                self.send_json(200, {'ok': True, 'project': project_name, 'output': output})
                print(f'✅ 掃描完成：{project_name}')
            else:
                self.send_json(500, {'error': f'掃描失敗：\n{output}'})
                print(f'❌ 掃描失敗：{output}')
        except subprocess.TimeoutExpired:
            self.send_json(500, {'error': '掃描超時（10分鐘）'})
        except Exception as e:
            self.send_json(500, {'error': str(e)})

    def handle_switch_project(self):
        """切換專案"""
        try:
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            data = json.loads(body.decode('utf-8'))
            project = data.get('project', '').strip()
            if not project:
                self.send_json(400, {'error': '缺少 project 參數'}); return
            if switch_project(project):
                self.send_json(200, {'ok': True, 'project': project})
                print(f'🔄 切換專案：{project}')
            else:
                self.send_json(404, {'error': f'專案不存在：{project}'})
        except Exception as e:
            self.send_json(500, {'error': str(e)})

    def handle_query(self):
        """自然語言查詢"""
        try:
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            data = json.loads(body.decode('utf-8'))
            question = data.get('question', '').strip()
            if not question:
                self.send_json(400, {'error': '請輸入問題'}); return

            print(f'🔍 查詢 [{current_provider}]：{question}')
            wiki_content = collect_wiki_content()
            if not wiki_content:
                self.send_json(400, {'error': '知識庫為空，請先執行 km-build.py'}); return

            answer = query_llm(question, wiki_content)
            self.send_json(200, {'answer': answer, 'model': current_provider})
            print(f'✅ 回答完成')
        except Exception as e:
            self.send_json(500, {'error': str(e)})
            print(f'❌ 查詢錯誤：{e}')

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if args and isinstance(args[0], str) and ('/api/' in args[0] or 'graph-view' in args[0]):
            super().log_message(format, *args)


# ====== 專案管理 ======

def list_projects() -> list:
    """列出 wiki/ 下所有專案子目錄"""
    projects = []
    if WIKI_DIR.exists():
        for d in sorted(WIKI_DIR.iterdir()):
            if d.is_dir():
                md_count = len(list(d.glob('*.md')))
                has_graph = (d / 'graph-data.json').exists()
                projects.append({
                    'name': d.name,
                    'files': md_count,
                    'hasGraph': has_graph,
                })
    return projects


def get_current_project() -> str:
    """從 graph-data.json 讀取當前專案名"""
    gf = Path(__file__).parent / 'graph-data.json'
    if gf.exists():
        try:
            data = json.loads(gf.read_text(encoding='utf-8'))
            return data.get('meta', {}).get('rootName', '')
        except Exception:
            pass
    return ''


def switch_project(project_name: str) -> bool:
    """切換到指定專案，複製其 graph-data.json 到根目錄"""
    project_dir = WIKI_DIR / project_name
    project_graph = project_dir / 'graph-data.json'

    print(f'  切換專案：{project_dir}')
    print(f'  graph 存在：{project_graph.exists()}')

    if not project_graph.exists():
        return False

    # 複製到根目錄
    import shutil
    root_graph = Path(__file__).parent / 'graph-data.json'
    shutil.copy2(str(project_graph), str(root_graph))
    print(f'  已複製 → {root_graph}')

    # 更新活動 wiki 目錄（供查詢用）
    global _active_wiki_dir
    _active_wiki_dir = project_dir
    return True


_active_wiki_dir = None


# ====== LLM 相關 ======

def get_ollama_models() -> list:
    """取得 Ollama 已安裝的模型列表"""
    try:
        base = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        req = urllib.request.Request(f'{base}/api/tags')
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            return [m['name'] for m in data.get('models', [])]
    except Exception:
        return []


def collect_wiki_content() -> str:
    wiki = _active_wiki_dir or WIKI_DIR
    # 如果 wiki 本身有 .md 就用它，否則找子目錄
    md_files = list(wiki.glob('*.md'))
    if not md_files:
        # 嘗試找第一個有內容的子目錄
        for d in sorted(wiki.iterdir()) if wiki.exists() else []:
            if d.is_dir():
                md_files = list(d.glob('*.md'))
                if md_files:
                    break
    if not md_files:
        return ''
    parts = []
    for f in sorted(md_files):
        if f.name == 'log.md':
            continue
        content = f.read_text(encoding='utf-8')
        parts.append(f'=== {f.stem} ===\n{content}')
    return '\n\n'.join(parts)


SYSTEM_PROMPT = """你是知識庫助手。根據提供的知識庫內容回答用戶的問題。

規則：
1. 只根據知識庫中的內容回答，不要編造
2. 引用來源時，使用 [[文件名稱]] 格式
3. 如果知識庫中沒有相關資訊，明確說明
4. 用繁體中文回答
5. 回答要簡潔有重點，但不遺漏關鍵資訊"""


def query_llm(question: str, wiki_content: str) -> str:
    """根據 current_provider 選擇 LLM"""
    if current_provider.startswith('claude'):
        return query_claude(question, wiki_content, current_provider)
    elif current_provider.startswith('gemini'):
        return query_gemini(question, wiki_content, current_provider)
    elif current_provider == 'openai':
        return query_openai(question, wiki_content)
    elif current_provider.startswith('ollama:'):
        model_name = current_provider.split(':', 1)[1]
        return query_ollama(question, wiki_content, model_name)
    else:
        return f'❌ 未知的模型：{current_provider}'


CLAUDE_MODELS = {
    'claude-sonnet': 'claude-sonnet-4-20250514',
    'claude-haiku': 'claude-haiku-4-5-20251001',
    'claude-opus': 'claude-opus-4-20250514',
}

def query_claude(question: str, wiki_content: str, provider: str = 'claude-sonnet') -> str:
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return '❌ 未設定 ANTHROPIC_API_KEY'
    model_id = CLAUDE_MODELS.get(provider, CLAUDE_MODELS['claude-sonnet'])
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_id,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"以下是知識庫內容：\n\n{wiki_content}\n\n---\n\n問題：{question}"}],
    )
    return response.content[0].text


def query_ollama(question: str, wiki_content: str, model: str) -> str:
    base = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    payload = json.dumps({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是知識庫內容：\n\n{wiki_content}\n\n---\n\n問題：{question}"},
        ],
    }).encode('utf-8')

    req = urllib.request.Request(
        f'{base}/api/chat',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            return data.get('message', {}).get('content', '（無回應）')
    except Exception as e:
        return f'❌ Ollama 錯誤：{e}'


GEMINI_MODELS = {
    'gemini-flash': 'gemini-2.5-flash',
    'gemini-pro': 'gemini-2.5-pro',
    'gemini-3-pro': 'gemini-3-pro-preview',
    'gemini-3-flash': 'gemini-3-flash-preview',
}

def query_gemini(question: str, wiki_content: str, provider: str = 'gemini-flash') -> str:
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        return '❌ 未設定 GOOGLE_API_KEY'

    model_id = GEMINI_MODELS.get(provider, GEMINI_MODELS['gemini-flash'])
    payload = json.dumps({
        "contents": [{
            "parts": [{"text": f"{SYSTEM_PROMPT}\n\n以下是知識庫內容：\n\n{wiki_content}\n\n---\n\n問題：{question}"}]
        }],
        "generationConfig": {"maxOutputTokens": 2048},
    }).encode('utf-8')

    req = urllib.request.Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            return data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f'❌ Gemini 錯誤：{e}'


def query_openai(question: str, wiki_content: str) -> str:
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return '❌ 未設定 OPENAI_API_KEY'

    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是知識庫內容：\n\n{wiki_content}\n\n---\n\n問題：{question}"},
        ],
        "max_tokens": 2048,
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=payload,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data['choices'][0]['message']['content']
    except Exception as e:
        return f'❌ OpenAI 錯誤：{e}'


def main():
    parser = argparse.ArgumentParser(description='KM Viewer 本地伺服器')
    parser.add_argument('-p', '--port', type=int, default=8765, help='埠號（預設 8765）')
    parser.add_argument('--host', default='127.0.0.1', help='綁定位址（預設 127.0.0.1，用 0.0.0.0 允許遠端存取）')
    args = parser.parse_args()

    # 檢測可用模型
    ollama_models = get_ollama_models()
    # 取得本機 IP
    import socket
    local_ip = ''
    if args.host == '0.0.0.0':
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = '?'

    print(f'🚀 KM Viewer 伺服器啟動')
    print(f'   本機：http://localhost:{args.port}/graph-view.html')
    if local_ip:
        print(f'   遠端：http://{local_ip}:{args.port}/graph-view.html')
    print(f'   📝 Wiki 目錄：{WIKI_DIR}')
    print(f'   🤖 目前模型：{current_provider}')
    if ollama_models:
        print(f'   🏠 Ollama 模型：{", ".join(ollama_models)}')
    print(f'   按 Ctrl+C 停止\n')

    server = HTTPServer((args.host, args.port), KMHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 已停止')
        server.server_close()


if __name__ == '__main__':
    main()
