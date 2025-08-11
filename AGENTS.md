# Cerebella Agent Guidelines

## Build/Test Commands
- **Start**: `npm start` or `node cli.js`
- **Python**: Uses `uv` package manager with virtual environment in `~/.cerebella`
- **No formal test suite**: Manual testing via dashboard at http://localhost:8421
- **No lint/typecheck commands**: Code style enforced through conventions

## Languages & Structure
- **Node.js CLI** (cli.js): ES modules, chalk for colors, ora for spinners
- **Python server** (*.py): HTTP server with file watching, embeddings, state management
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
- Embedding computation with queue-based processing