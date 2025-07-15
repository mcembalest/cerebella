from http.server import SimpleHTTPRequestHandler
from huggingface_hub import InferenceClient
import json
import numpy as np
import os
from pathlib import Path
import queue
import time
import urllib.parse

from cerebella_state import CerebellaState, FileData
from util import load_dashboard_html, read_file_content, create_file_change, create_file_change_for_new_file, flatten_embedding, normalize_to_unit_vector

WATCH_INTERVAL = 0.5
CEREBELLA_SERVER_PORT = 8421
EMBEDDING_SERVER_PORT = 8080
EMBEDDING_QUEUE = queue.Queue()
CEREBELLA_IGNORE_DIRS = ['__pycache__', 'node_modules', '.git']
CEREBELLA_STATE = CerebellaState()
embedding_client = InferenceClient()

def apply_file_permission(filepath, locked):
    """Apply readonly (444) or read-write (644) permissions to a file."""
    try:
        if locked:
            os.chmod(filepath, 0o444)  # readonly
        else:
            os.chmod(filepath, 0o644)  # read-write
        return True
    except Exception as e:
        print(f"Error changing permissions for {filepath}: {e}")
        return False

def enforce_file_permissions():
    """Enforce lock status for all tracked files."""
    for filepath, file_data in CEREBELLA_STATE.files.items():
        if os.path.exists(filepath):
            locked = CEREBELLA_STATE.get_lock_status(filepath)
            apply_file_permission(filepath, locked)

def scan_directory(directory, is_initial_scan=False):
    """Scan directory for file changes and update state."""
    try:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in CEREBELLA_IGNORE_DIRS]
            for file in files:
                if file.startswith('.'):
                    continue
                filepath = os.path.join(root, file)
                content, lines = read_file_content(filepath)
                process_file(filepath, directory, content, lines, is_initial_scan)
                
    except Exception as e:
        print(f"Error scanning directory {directory}: {e}")

def compute_embedding(text):
    """Compute embedding for given text using the embedding client."""
    embedding = embedding_client.feature_extraction(
        text, model=f"http://localhost:{EMBEDDING_SERVER_PORT}/embed"
    )
    return np.array(embedding)

def compute_state_vector():
    """Compute the state vector as sum of unit vectors from all file embeddings."""
    embeddings = []
    for _, file_data in CEREBELLA_STATE.files.items():
        if file_data.embedding is not None:
            embedding_flat = flatten_embedding(file_data.embedding)
            unit_vector = normalize_to_unit_vector(embedding_flat)
            if unit_vector is not None:
                embeddings.append(unit_vector)
    if not embeddings:
        return None
    state_vector = np.sum(embeddings, axis=0)
    return state_vector

def update_state_vector():
    """Update the state vector and track its history."""
    new_state_vector = compute_state_vector()
    if new_state_vector is not None:
        CEREBELLA_STATE.update_vectors(new_state_vector.tolist())

def process_file(filepath, watching_dir, content, lines, is_initial_scan=False):
    """Process a single file for changes."""
    try:
        stat = os.stat(filepath)
        mtime = stat.st_mtime
        size = stat.st_size
        
        old_file_data = CEREBELLA_STATE.get_file(filepath)
        change = None
        file_changed = False
        
        if old_file_data:
            if old_file_data.mtime < mtime:
                if not is_initial_scan:
                    change = create_file_change(filepath, watching_dir, old_file_data, size, lines, content)
                file_changed = True
        else:
            if not is_initial_scan:
                change = create_file_change_for_new_file(filepath, watching_dir, size, lines, content)
            file_changed = True
        
        if file_changed or is_initial_scan:
            new_file_data = FileData(
                mtime=mtime,
                size=size,
                lines=lines,
                content=content,
                embedding=None  # computed asynchronously
            )
            CEREBELLA_STATE.process_file_change(filepath, new_file_data, change, is_initial_scan)
            EMBEDDING_QUEUE.put_nowait((filepath, content))
            
            # Apply lock status if file is locked
            locked = CEREBELLA_STATE.get_lock_status(filepath)
            if locked:
                apply_file_permission(filepath, locked)
            
    except Exception as e:
        print(f"Error processing file {filepath}: {e}")


def compute_state_vector_loop():
    """Worker thread for processing state vector with embeddings."""
    while True:
        try:
            filepath, content = EMBEDDING_QUEUE.get()
            embedding = compute_embedding(content)
            if embedding is not None:
                file_data = CEREBELLA_STATE.get_file(filepath)
                if file_data:
                    embedding_flat = flatten_embedding(embedding)
                    file_data.embedding = embedding_flat.tolist() if embedding_flat is not None else None
                    update_state_vector()
        except Exception as e:
            print(f"Error in embedding worker: {e}")
        finally:
            EMBEDDING_QUEUE.task_done()

def watch_files_loop():
    """Main file watching loop."""
    iteration_count = 0
    while True:
        if CEREBELLA_STATE.watching:
            scan_directory(CEREBELLA_STATE.watching)
            # Enforce permissions every 10 iterations (5 seconds)
            iteration_count += 1
            if iteration_count % 10 == 0:
                enforce_file_permissions()
        time.sleep(WATCH_INTERVAL)

class CerebellaLocalServer(SimpleHTTPRequestHandler):
    """HTTP server for the Cerebella dashboard."""
    
    def __init__(self, *args, **kwargs):
        self.html_content = load_dashboard_html()
        super().__init__(*args, **kwargs)
    
    def serve_static_file(self, filepath, content_type=None):
        """Serve a static file with appropriate content type."""
        install_dir = os.environ.get('CEREBELLA_INSTALL_DIR', os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(install_dir, filepath)
        
        if content_type is None:
            content_types = {
                '.css': 'text/css',
                '.js': 'application/javascript',
                '.html': 'text/html',
                '.png': 'image/png',
                '.ico': 'image/x-icon'
            }
            ext = Path(full_path).suffix
            content_type = content_types.get(ext, 'application/octet-stream')
        
        try:
            with open(full_path, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            self.send_error(404, f'File not found: {full_path}')
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self.html_content.encode())
        elif self.path == '/state':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(CEREBELLA_STATE.serialize()).encode())
        elif self.path == '/favicon.ico':
            self.serve_static_file('assets/cerebella_icon.png', 'image/png')
        elif self.path in ['/dashboard.css', '/dashboard.js']:
            self.serve_static_file(f'dashboard{self.path}')
        else:
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/watch':
            self.handle_watch_request()
        elif self.path == '/clear':
            self.handle_clear_request()
        elif self.path == '/lock':
            self.handle_lock_request()
        elif self.path == '/unlock':
            self.handle_unlock_request()
        elif self.path == '/toggle-lock':
            self.handle_toggle_lock_request()
        elif self.path == '/lock-all':
            self.handle_lock_all_request()
        elif self.path == '/unlock-all':
            self.handle_unlock_all_request()
    
    def handle_watch_request(self):
        """Handle directory watching request."""
        try:
            length = int(self.headers['Content-Length'])
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            directory = data.get('directory', [''])[0]
            
            if os.path.exists(directory):
                CEREBELLA_STATE.reset()
                CEREBELLA_STATE.watching = directory
                print(f"Now watching: {directory}")
                scan_directory(directory, is_initial_scan=True)
            else:
                print(f"Directory not found: {directory}")
                
        except Exception as e:
            print(f"Error handling watch request: {e}")
        
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()
    
    def handle_clear_request(self):
        """Handle clear changes request."""
        CEREBELLA_STATE.clear_changes()
        print("Changes cleared")
        self.send_response(200)
        self.end_headers()
    
    def handle_lock_request(self):
        """Handle file lock request."""
        try:
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length).decode())
            filepath = data.get('filepath')
            
            if filepath and os.path.exists(filepath):
                CEREBELLA_STATE.set_lock_status(filepath, True)
                success = apply_file_permission(filepath, True)
                print(f"Locked file: {filepath}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': success}).encode())
            else:
                self.send_response(400)
                self.end_headers()
        except Exception as e:
            print(f"Error handling lock request: {e}")
            self.send_response(500)
            self.end_headers()
    
    def handle_unlock_request(self):
        """Handle file unlock request."""
        try:
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length).decode())
            filepath = data.get('filepath')
            
            if filepath and os.path.exists(filepath):
                CEREBELLA_STATE.set_lock_status(filepath, False)
                success = apply_file_permission(filepath, False)
                print(f"Unlocked file: {filepath}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': success}).encode())
            else:
                self.send_response(400)
                self.end_headers()
        except Exception as e:
            print(f"Error handling unlock request: {e}")
            self.send_response(500)
            self.end_headers()
    
    def handle_toggle_lock_request(self):
        """Handle file lock toggle request."""
        try:
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length).decode())
            filepath = data.get('filepath')
            
            if filepath and os.path.exists(filepath):
                current_status = CEREBELLA_STATE.get_lock_status(filepath)
                new_status = not current_status
                CEREBELLA_STATE.set_lock_status(filepath, new_status)
                success = apply_file_permission(filepath, new_status)
                print(f"Toggled lock for {filepath}: {'locked' if new_status else 'unlocked'}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': success, 'locked': new_status}).encode())
            else:
                self.send_response(400)
                self.end_headers()
        except Exception as e:
            print(f"Error handling toggle lock request: {e}")
            self.send_response(500)
            self.end_headers()
    
    def handle_lock_all_request(self):
        """Handle lock all files request."""
        try:
            success_count = 0
            for filepath in CEREBELLA_STATE.files.keys():
                if os.path.exists(filepath):
                    CEREBELLA_STATE.set_lock_status(filepath, True)
                    if apply_file_permission(filepath, True):
                        success_count += 1
            
            print(f"Locked {success_count} files")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'count': success_count}).encode())
        except Exception as e:
            print(f"Error handling lock all request: {e}")
            self.send_response(500)
            self.end_headers()
    
    def handle_unlock_all_request(self):
        """Handle unlock all files request."""
        try:
            success_count = 0
            for filepath in CEREBELLA_STATE.files.keys():
                if os.path.exists(filepath):
                    CEREBELLA_STATE.set_lock_status(filepath, False)
                    if apply_file_permission(filepath, False):
                        success_count += 1
            
            print(f"Unlocked {success_count} files")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'count': success_count}).encode())
        except Exception as e:
            print(f"Error handling unlock all request: {e}")
            self.send_response(500)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass