from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict


@dataclass
class FileData:
    mtime: float
    size: int
    lines: Optional[int] = None
    content: Optional[str] = None
    embedding: Optional[List[float]] = None
    locked: bool = False

@dataclass
class FileChange:
    file: str
    time: str
    size_change: int
    lines_change: Optional[int]
    ext: str
    diff: Optional[str] = None

@dataclass
class CerebellaState:
    watching: Optional[str] = None
    files: Dict[str, FileData] = field(default_factory=dict)
    changes: List[FileChange] = field(default_factory=list)
    state_vector: Optional[List[float]] = None
    initial_state_vector: Optional[List[float]] = None
    file_locks: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize any additional attributes after dataclass initialization."""
        # All fields are now properly initialized by dataclass
        pass
    
    def reset(self):
        """Reset the state to initial values."""
        self.watching = None
        self.files = {}
        self.changes = []
        self.state_vector = None
        self.initial_state_vector = None
        self.file_locks = {}
    
    def add_change(self, change: FileChange):
        """Add a new change to the beginning of the changes list."""
        self.changes.insert(0, change)
    
    def update_file(self, filepath: str, file_data: FileData):
        """Update or add a file to the tracked files."""
        self.files[filepath] = file_data
    
    def get_file(self, filepath: str) -> Optional[FileData]:
        """Get file data if it exists."""
        return self.files.get(filepath)
    
    def clear_changes(self):
        """Clear all tracked changes."""
        self.changes = []
    
    def update_vectors(self, state_vector: List[float]):
        """Update state vector and set initial if needed."""
        if self.initial_state_vector is None:
            self.initial_state_vector = state_vector
        self.state_vector = state_vector
    
    def process_file_change(self, filepath: str, file_data: FileData, change: Optional[FileChange] = None, is_initial_scan: bool = False):
        """Process a file change, updating state and optionally adding a change record."""
        if not is_initial_scan and change:
            self.add_change(change)
        self.update_file(filepath, file_data)
    
    def serialize(self) -> dict:
        """Convert the state to a JSON-serializable format."""
        return {
            'watching': self.watching,
            'files': {
                path: asdict(file_data)
                for path, file_data in self.files.items()
            },
            'changes': [
                asdict(change)
                for change in self.changes
            ],
            'state_vector': self.state_vector,
            'initial_state_vector': self.initial_state_vector,
            'file_locks': self.file_locks
        }
    
    def set_lock_status(self, filepath, locked):
        """Set the lock status for a file."""
        self.file_locks[filepath] = locked
        if filepath in self.files:
            self.files[filepath].locked = locked

    def get_lock_status(self, filepath):
        """Get the lock status for a file."""
        return self.file_locks.get(filepath, False)