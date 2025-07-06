import difflib
import numpy as np
import os
from pathlib import Path
import time

from cerebella_state import FileChange

FILETYPES_WITH_LINE_NUMBERS = ('.py', '.js', '.ts', '.txt', '.md', '.csv', '.json', '.xml', '.html', '.yaml')


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

def flatten_embedding(embedding):
    """Flatten an embedding array if needed."""
    if embedding is None:
        return None
    embedding_array = np.array(embedding)
    if embedding_array.ndim > 1:
        return embedding_array.flatten()
    return embedding_array

def normalize_to_unit_vector(vector):
    """Normalize a vector to unit length."""
    if vector is None:
        return None
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


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
        diff=diff
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
        diff=f"New file created with {lines or 0} lines" if content else "New binary file"
    )

def load_dashboard_html():
    """Load the dashboard HTML template."""
    install_dir = os.environ.get('CEREBELLA_INSTALL_DIR', os.path.dirname(os.path.abspath(__file__)))
    dashboard_path = os.path.join(install_dir, 'dashboard', 'dashboard.html')
    with open(dashboard_path, 'r') as f:
        return f.read()

def read_file_content(filepath):
    """Read file content and return content, lines count, or None if failed."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        lines = len(content.splitlines())
        return content, lines
