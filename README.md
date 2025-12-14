# Talemon

Traceable Web Data Collection Platform.

## Environment Management

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

### Prerequisites

- Python 3.12+
- `uv` installed (see [uv installation guide](https://github.com/astral-sh/uv?tab=readme-ov-file#installation))

### Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```
   This will create a virtual environment in `.venv` and install the locked dependencies.

2. **Activate environment**:
   - Windows: `.venv\Scripts\activate`
   - Unix/MacOS: `source .venv/bin/activate`

3. **Add a dependency**:
   ```bash
   uv add <package_name>
   ```

4. **Add a development dependency**:
   ```bash
   uv add --dev <package_name>
   ```

5. **Run tests**:
   ```bash
   uv run pytest
   ```
