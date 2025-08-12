# Cerebella Agent Guidelines

## Build/Test Commands
- **Start**: `npm start` or `node cli.js`
- **Python**: Uses `uv` package manager with virtual environment in `~/.cerebella`
- **No formal test suite**: Manual testing via dashboard at http://localhost:8421
- **No lint/typecheck commands**: Code style enforced through conventions

## Languages & Structure
- **Node.js CLI** (cli.js): ES modules, chalk for colors, ora for spinners
- **Python server** (*.py): HTTP server with file watching, state management (simplified)
- **Frontend** (dashboard/): Vanilla HTML/CSS/JS, no frameworks

## Code Style
- **Python**: snake_case, dataclasses, type hints, docstrings for functions
- **JavaScript**: camelCase, ES6+ features, const/let (no var)
- **Imports**: Standard library first, then third-party, then local imports
- **Error handling**: Try/catch with console logging, graceful degradation
- **File structure**: Flat structure, descriptive filenames

## Key Patterns
- State management via CerebellaState dataclass
- File watching with threading for async operations
- HTTP endpoints for dashboard communication
- Visual-only file locking (no actual permission changes)

## Recent Fixes Applied
- **Diff display bug**: Fixed `split('\\n')` → `split('\n')` and `join('\\n')` → `join('\n')` in dashboard.js
- **Missing DOM element**: Added `<div id="file-summary"></div>` to dashboard.html
- **File reading errors**: Added try/catch to `read_file_content()` in util.py
- **Simplified architecture**: Removed all ML/embedding complexity, kept beautiful UI
- **Dependencies cleaned**: Removed numpy, huggingface-hub, and other ML packages

## Known Issues & TODOs
- **Lock button race condition**: Buttons recreated every 1s via innerHTML, causing click delays
  - Need immediate visual feedback and optimistic updates
  - Consider event delegation instead of inline onclick handlers
- **Performance**: 1-second polling could be optimized with WebSockets or Server-Sent Events
- **File watching**: Could replace polling with proper filesystem events (fs.watch)

## Testing Strategy
- Use isolated test directories (e.g., /tmp/test-cerebella)
- Test Python server directly with curl before testing full UI
- Verify API endpoints work before debugging frontend issues
- Clean up test artifacts: `rm -rf /tmp/test-* && pkill -f cerebella`