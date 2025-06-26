from dataclasses import dataclass, asdict
import difflib
from http.server import HTTPServer, SimpleHTTPRequestHandler
from huggingface_hub import InferenceClient
import json
import numpy as np
import os
from pathlib import Path
import queue
import threading
import time
from typing import Optional, List, Tuple
import urllib.parse

embedding_client = InferenceClient()

CEREBELLA_IGNORE_DIRS = ['__pycache__', 'node_modules', '.git']
FILETYPES_WITH_LINE_NUMBERS = ('.py', '.js', '.ts', '.txt', '.md', '.csv', '.json', '.xml', '.html', '.yaml')
WATCH_INTERVAL = 0.5
SERVER_PORT = 8421
EMBEDDING_MODEL_LOCAL_SERVER_URL = "http://localhost:8080/embed"

# Queue for embedding processing
EMBEDDING_QUEUE = queue.Queue()

@dataclass
class FileData:
    mtime: float
    size: int
    lines: Optional[int] = None
    content: Optional[str] = None
    embedding: Optional[List[float]] = None

@dataclass
class FileChange:
    file: str
    time: str
    size_change: int
    lines_change: Optional[int]
    ext: str
    diff: Optional[str] = None
    vector_head: Optional[List[float]] = None
    vector_tail: Optional[List[float]] = None

@dataclass
class StateVectorHistoryEntry:
    time: str
    vector_head: List[float]
    vector_tail: List[float]
    magnitude: float

CEREBELLA_STATE = {
    'watching': None,
    'files': {},
    'changes': [],
    'state_vector': None,
    'state_vector_history': [],
    'initial_state_vector': None
}

def load_dashboard_html():
    """Load the dashboard HTML template."""
    try:
        with open('dashboard.html', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return "<html><body><h1>Dashboard not found</h1></body></html>"

def generate_diff_format(old_content, new_content):
    """Generate diff format."""
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=''))
    if not diff: return None
    patch_lines = []
    context_lines = []
    changes = []
    in_hunk = False
    for line in diff:
        if line.startswith('@@'):
            in_hunk = True
            continue
        elif line.startswith(('---', '+++')):
            continue
        elif in_hunk:
            if line.startswith(' '):
                context_lines.append(line[1:])
            elif line.startswith('-'):
                changes.append(('-', line[1:]))
            elif line.startswith('+'):
                changes.append(('+', line[1:]))    
    if context_lines or changes:
        for context in context_lines[:3]:
            patch_lines.append(f"    {context}")        
        for change_type, content in changes:
            prefix = "-" if change_type == '-' else "+"
            patch_lines.append(f"{prefix}        {content}")
    return '\n'.join(patch_lines)

def read_file_content(filepath):
    """Read file content and return content, lines count, or None if failed."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = len(content.splitlines())
            return content, lines
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None, None

def should_track_file(filepath):
    """Check if file should be tracked based on extension and ignore rules."""
    return (
        not os.path.basename(filepath).startswith('.') and
        filepath.endswith(FILETYPES_WITH_LINE_NUMBERS)
    )

def create_file_change(filepath, watching_dir, old_file_data, size, lines, content):
    """Create a change record for a file modification."""
    relative_path = os.path.relpath(filepath, watching_dir)
    
    diff = None
    if content is not None and old_file_data.content is not None:
        diff = generate_diff_format(old_file_data.content, content)
    
    return FileChange(
        file=relative_path,
        time=time.strftime('%H:%M:%S'),
        size_change=size - old_file_data.size,
        lines_change=lines - old_file_data.lines if lines is not None and old_file_data.lines is not None else None,
        ext=Path(filepath).suffix,
        diff=diff,
        vector_head=None,
        vector_tail=None
    )

def create_file_change_for_new_file(filepath, watching_dir, size, lines, content):
    """Create a change record for a new file."""
    relative_path = os.path.relpath(filepath, watching_dir)
    
    return FileChange(
        file=relative_path,
        time=time.strftime('%H:%M:%S'),
        size_change=size,
        lines_change=lines,
        ext=Path(filepath).suffix,
        diff=f"New file created with {lines or 0} lines" if content else "New binary file",
        vector_head=None,  # Will be updated after embeddings are computed
        vector_tail=None   # Will be updated after embeddings are computed
    )

def scan_directory(directory, is_initial_scan=False):
    """Scan directory for file changes and update state."""
    try:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in CEREBELLA_IGNORE_DIRS]
            for file in files:
                if file.startswith('.'):
                    continue
                filepath = os.path.join(root, file)
                process_file(filepath, directory, is_initial_scan)
                
    except Exception as e:
        print(f"Error scanning directory {directory}: {e}")

def compute_embedding(text):
    """Compute embedding for given text using the embedding client."""
    try:
        if not text or len(text.strip()) == 0:
            return None
        embedding = embedding_client.feature_extraction(text, model=EMBEDDING_MODEL_LOCAL_SERVER_URL)
        return np.array(embedding)
    except Exception as e:
        print(f"Error computing embedding: {e}")
        return None

def normalize_to_unit_vector(vector):
    """Normalize a vector to unit length."""
    if vector is None:
        return None
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm

def compute_state_vector():
    """Compute the state vector as sum of unit vectors from all file embeddings."""
    embeddings = []
    for _, file_data in CEREBELLA_STATE['files'].items():
        if isinstance(file_data, FileData) and file_data.embedding is not None:
            embedding_array = np.array(file_data.embedding)
            # Handle nested array structure
            if embedding_array.ndim > 1:
                embedding_array = embedding_array.flatten()
            unit_vector = normalize_to_unit_vector(embedding_array)
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
        # Set initial state vector if not set
        if CEREBELLA_STATE['initial_state_vector'] is None:
            CEREBELLA_STATE['initial_state_vector'] = new_state_vector.tolist()
        
        CEREBELLA_STATE['state_vector'] = new_state_vector.tolist()
        
        # Update vector info for recent changes
        vector_head = new_state_vector[:5].tolist()
        vector_tail = new_state_vector[-5:].tolist()
        
        # Update the most recent changes with vector info
        for change in CEREBELLA_STATE['changes'][:5]:  # Update last 5 changes
            if isinstance(change, FileChange) and change.vector_head is None:
                change.vector_head = vector_head
                change.vector_tail = vector_tail
        
        history_entry = StateVectorHistoryEntry(
            time=time.strftime('%H:%M:%S'),
            vector_head=vector_head,
            vector_tail=vector_tail,
            magnitude=float(np.linalg.norm(new_state_vector))
        )
        CEREBELLA_STATE['state_vector_history'].insert(0, history_entry)
        if len(CEREBELLA_STATE['state_vector_history']) > 50:
            CEREBELLA_STATE['state_vector_history'] = CEREBELLA_STATE['state_vector_history'][:50]

def process_file(filepath, watching_dir, is_initial_scan=False):
    """Process a single file for changes."""
    try:
        stat = os.stat(filepath)
        mtime = stat.st_mtime
        size = stat.st_size
        content, lines = None, None
        file_changed = False
        
        if should_track_file(filepath):
            content, lines = read_file_content(filepath)
        
        if filepath in CEREBELLA_STATE['files']:
            old_file_data = CEREBELLA_STATE['files'][filepath]
            if old_file_data.mtime < mtime:
                # Only create change record if not initial scan
                if not is_initial_scan:
                    change = create_file_change(filepath, watching_dir, old_file_data, size, lines, content)
                    CEREBELLA_STATE['changes'].insert(0, change)
                file_changed = True
        else:
            # New file - only create change record if not initial scan
            if not is_initial_scan:
                change = create_file_change_for_new_file(filepath, watching_dir, size, lines, content)
                CEREBELLA_STATE['changes'].insert(0, change)
            file_changed = True
        
        # Always update stored file data
        if file_changed or is_initial_scan:
            CEREBELLA_STATE['files'][filepath] = FileData(
                mtime=mtime,
                size=size,
                lines=lines,
                content=content,
                embedding=None  # Will be computed asynchronously
            )
            
            # Queue the file for embedding computation (non-blocking)
            if content is not None:
                try:
                    EMBEDDING_QUEUE.put_nowait((filepath, content))
                except queue.Full:
                    print(f"Embedding queue full, skipping {filepath}")
            
    except Exception as e:
        print(f"Error processing file {filepath}: {e}")

def serialize_state():
    """Convert the state to a JSON-serializable format."""
    state_copy = CEREBELLA_STATE.copy()
    state_copy['files'] = {
        path: asdict(file_data) if isinstance(file_data, FileData) else file_data
        for path, file_data in CEREBELLA_STATE['files'].items()
    }    
    state_copy['changes'] = [
        asdict(change) if isinstance(change, FileChange) else change
        for change in CEREBELLA_STATE['changes']
    ]
    state_copy['state_vector_history'] = [
        asdict(entry) if isinstance(entry, StateVectorHistoryEntry) else entry
        for entry in CEREBELLA_STATE['state_vector_history']
    ]
    return state_copy

def embedding_worker():
    """Worker thread for processing embeddings."""
    while True:
        try:
            # Get file info from queue (blocking)
            filepath, content = EMBEDDING_QUEUE.get()
            
            if content is None:
                continue
                
            # Compute embedding
            embedding = compute_embedding(content)
            
            if embedding is not None and filepath in CEREBELLA_STATE['files']:
                # Update the file's embedding
                file_data = CEREBELLA_STATE['files'][filepath]
                if isinstance(file_data, FileData):
                    # Handle nested array structure and flatten if needed
                    if embedding.ndim > 1:
                        embedding_flat = embedding.flatten()
                    else:
                        embedding_flat = embedding
                    file_data.embedding = embedding_flat.tolist()
                    # Update state vector after embedding is computed
                    update_state_vector()
                    
        except Exception as e:
            print(f"Error in embedding worker: {e}")
        finally:
            EMBEDDING_QUEUE.task_done()

def watch_files():
    """Main file watching loop."""
    while True:
        if CEREBELLA_STATE['watching']:
            scan_directory(CEREBELLA_STATE['watching'])
        time.sleep(WATCH_INTERVAL)

class CerebellaLocalServer(SimpleHTTPRequestHandler):
    """HTTP server for the Cerebella dashboard."""
    
    def __init__(self, *args, **kwargs):
        self.html_content = load_dashboard_html()
        super().__init__(*args, **kwargs)
    
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
            self.wfile.write(json.dumps(serialize_state()).encode())
        elif self.path == '/dashboard.css':
            try:
                with open('dashboard.css', 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/css')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, 'CSS file not found')
        elif self.path == '/dashboard.js':
            try:
                with open('dashboard.js', 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/javascript')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, 'JavaScript file not found')
        else:
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/watch':
            self.handle_watch_request()
        elif self.path == '/clear':
            self.handle_clear_request()
    
    def handle_watch_request(self):
        """Handle directory watching request."""
        try:
            length = int(self.headers['Content-Length'])
            data = urllib.parse.parse_qs(self.rfile.read(length).decode())
            directory = data.get('directory', [''])[0]
            
            if os.path.exists(directory):
                CEREBELLA_STATE['watching'] = directory
                CEREBELLA_STATE['files'] = {}
                CEREBELLA_STATE['changes'] = []
                CEREBELLA_STATE['state_vector'] = None
                CEREBELLA_STATE['state_vector_history'] = []
                CEREBELLA_STATE['initial_state_vector'] = None
                print(f"Now watching: {directory}")
                # Do initial scan without creating change records
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
        CEREBELLA_STATE['changes'] = []
        print("Changes cleared")
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass

def print_banner():
    """Print the Cerebella banner."""
    print("""
   ██████╗███████╗██████╗ ███████╗██████╗ ███████╗██╗     ██╗      █████╗ 
  ██╔════╝██╔════╝██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██║     ██╔══██╗
  ██║     █████╗  ██████╔╝█████╗  ██████╔╝█████╗  ██║     ██║     ███████║
  ██║     ██╔══╝  ██╔══██╗██╔══╝  ██╔══██╗██╔══╝  ██║     ██║     ██╔══██║
  ╚██████╗███████╗██║  ██║███████╗██████╔╝███████╗███████╗███████╗██║  ██║
   ╚═════╝╚══════╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝
""")

if __name__ == '__main__':
    print_banner()
    print(f"Open http://localhost:{SERVER_PORT} in your browser")
    
    # Start file watching thread
    watch_thread = threading.Thread(target=watch_files, daemon=True)
    watch_thread.start()
    
    # Start embedding worker thread
    embedding_thread = threading.Thread(target=embedding_worker, daemon=True)
    embedding_thread.start()
    
    try:
        httpd = HTTPServer(('localhost', SERVER_PORT), CerebellaLocalServer)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(e)