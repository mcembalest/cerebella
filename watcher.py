import os
import json
import time
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import urllib.parse
import difflib

CEREBELLA_IGNORE_DIRS = ['__pycache__', 'node_modules', '.git']
FILETYPES_WITH_LINE_NUMBERS = ('.py', '.js', '.ts', '.txt', '.md', '.csv', '.json', '.xml', '.html', '.yaml')

with open('dashboard.html', 'r') as f:
    HTML = f.read()

state = {
    'watching': None,
    'files': {},
    'changes': []
}

class LocalServer(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/state':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(state).encode())
        else:
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/watch':
            length = int(self.headers['Content-Length'])
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            directory = data.get('directory', [''])[0]
            if os.path.exists(directory):
                state['watching'] = directory
                state['files'] = {}
                state['changes'] = []
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        elif self.path == '/clear':
            state['changes'] = []
            self.send_response(200)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

def watch_files():
    global state
    while True:
        if state['watching']:
            try:
                for root, dirs, files in os.walk(state['watching']):
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in CEREBELLA_IGNORE_DIRS]
                    for file in files:
                        if file.startswith('.'):
                            continue
                        filepath = os.path.join(root, file)
                        stat = os.stat(filepath)
                        mtime = stat.st_mtime
                        size = stat.st_size
                        
                        # Read content for text files
                        lines = None
                        content = None
                        if filepath.endswith(FILETYPES_WITH_LINE_NUMBERS):
                            try:
                                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read()
                                    lines = len(content.splitlines())
                            except:
                                pass
                        
                        if filepath in state['files']:
                            old = state['files'][filepath]
                            if old['mtime'] < mtime:
                                # File was modified
                                lines_change = None
                                if lines is not None and 'lines' in old:
                                    lines_change = lines - old['lines']
                                
                                change = {
                                    'file': os.path.relpath(filepath, state['watching']),
                                    'time': time.strftime('%H:%M:%S'),
                                    'size_change': size - old['size'],
                                    'lines_change': lines_change,
                                    'ext': Path(filepath).suffix,
                                    'diff': None
                                }
                                
                                # Generate diff for text files
                                if content is not None and old.get('content') is not None:
                                    diff_lines = list(difflib.unified_diff(
                                        old['content'].splitlines(keepends=True),
                                        content.splitlines(keepends=True),
                                        fromfile=f"{change['file']} (before)",
                                        tofile=f"{change['file']} (after)",
                                        n=3
                                    ))
                                    change['diff'] = ''.join(diff_lines[:200])  # Limit diff size
                                
                                state['changes'].insert(0, change)
                        else:
                            change = {
                                'file': os.path.relpath(filepath, state['watching']),
                                'time': time.strftime('%H:%M:%S'),
                                'size_change': size,
                                'lines_change': lines,
                                'ext': Path(filepath).suffix,
                                'diff': f"New file created with {lines or 0} lines" if content else "New binary file"
                            }
                            state['changes'].insert(0, change)
                        
                        state['files'][filepath] = {
                            'mtime': mtime, 
                            'size': size, 
                            'lines': lines,
                            'content': content  # Store content for next diff
                        }
            except Exception as e:
                pass
        time.sleep(0.5)

if __name__ == '__main__':
    watcher = threading.Thread(target=watch_files, daemon=True)
    watcher.start()    
    print("🌐 Open http://localhost:8421 in your browser")
    httpd = HTTPServer(('localhost', 8421), LocalServer)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")