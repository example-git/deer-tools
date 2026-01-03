# Contributing

Thanks for contributing to Deer Toolbox.

## Project Principles

- Keep the core usable with the Python standard library.
- Optional features (web/desktop/markdown rendering) must degrade gracefully when dependencies are missing.
- Prefer small, composable modules over large “god” scripts.
- Changes should not break plugin discovery or the `toolbox.py` entrypoint.

## Development Setup

- Python: 3.8+
- Install optional deps (recommended for UI work):

```bash
pip install -r requirements.txt
```

## Code Guidelines

### Style

- Follow PEP 8 (4 spaces, no tabs).
- Prefer explicit names over abbreviations.
- Keep functions focused; avoid deeply nested logic.

### Types

- Add type hints for new functions and public APIs.
- Use `Optional[T]` / `T | None` intentionally and keep `None` handling explicit.

### Errors & Logging

- Avoid `except Exception:` unless you’re at a CLI boundary or a deliberate “best-effort” fallback.
- Catch specific exceptions where possible (`FileNotFoundError`, `OSError`, `ValueError`, etc.).
- Surface actionable error messages to users; don’t hide failures silently.

### Optional Dependencies

- Treat `flask`, `pywebview`, `markdown`, etc. as optional.
- Import optional packages lazily (inside functions) and handle `ImportError` with a clear fallback.

### Security & Safety

- Never execute user-provided strings with `eval` / `exec`.
- Validate filesystem paths before destructive operations.
- Default to “dry-run” behavior for file-modifying commands when appropriate.

## Plugin Guidelines

Plugins live under `plugins/<tool_name>/` and should include:

- `tool.py` implementing `register_cli(subparsers)` and `run(mode='cli', **kwargs)`
- `metadata.json` describing the tool
- `README.md` documenting usage and flags

Avoid importing other plugins directly; use shared utilities in `shared/` where possible.

## Running Checks

Quick sanity checks:

```bash
python -m py_compile toolbox/webui.py
pytest
```

## Pull Requests

- Keep PRs small and focused.
- Update documentation (plugin `README.md` or root `README.md`) when behavior changes.
- If you add a new dependency, justify why it’s optional vs required and update `requirements.txt`.
