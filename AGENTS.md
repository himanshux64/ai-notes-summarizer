# Repository Guidelines

## Project Structure & Module Organization

This repository is a small Flask web application. `app.py` defines configuration, authentication, routes, PDF ingestion, and the Gunicorn application object. `database.py` contains the MongoDB data layer and SQLite development fallback; keep persistence logic there rather than in route handlers. `summarizer.py` owns Hugging Face calls, response parsing, and mock summarization. Jinja pages live in `templates/`, while browser code and styling live under `static/js/` and `static/css/`. Runtime databases belong in `data/` and must remain untracked.

## Build, Test, and Development Commands

- `python -m venv venv` creates the local virtual environment.
- `venv\Scripts\Activate.ps1` activates it in PowerShell.
- `python -m pip install -r requirements.txt` installs application dependencies.
- `$env:USE_LOCAL_DB="1"; python app.py` runs the development server at `http://localhost:5000` with SQLite.
- `gunicorn app:app --workers 4 --threads 2 --timeout 120` mirrors the production entry point (use a Unix-like environment).
- `python -m compileall app.py database.py summarizer.py` provides a quick syntax check.

There is currently no automated build step or committed test suite.

## Coding Style & Naming Conventions

Follow PEP 8 with four-space indentation. Use `snake_case` for functions and variables, `UPPER_SNAKE_CASE` for constants, and `PascalCase` for classes. Keep route functions thin, use type hints for reusable helpers, and add concise docstrings where behavior is not obvious. Preserve the existing separation between Flask, persistence, and AI logic. No formatter or linter is configured, so keep imports grouped and avoid unrelated reformatting.

## Testing Guidelines

New behavior should include `pytest` tests under `tests/`, named `test_<module>.py`; test functions should describe behavior, for example `test_parse_llm_output_handles_missing_tags`. Prefer Flask's test client, temporary SQLite paths, and mocked Hugging Face calls. Once tests exist, run them with `python -m pytest` and cover success, validation, authentication, and fallback paths.

## Commit & Pull Request Guidelines

History is sparse, so use short imperative commit subjects such as `Add PDF validation` or `Fix SQLite fallback`. Keep commits focused. Pull requests should explain the user-visible change, list verification commands, note environment or schema changes, link relevant issues, and include screenshots for template or CSS updates.

## Security & Configuration

Never commit `.env`, API tokens, database files, or user content. Configure `SECRET_KEY`, `MONGODB_URI`, and `HUGGINGFACEHUB_API_TOKEN` through the environment. Use `USE_LOCAL_DB=1` and optionally `LOCAL_DB_PATH` for offline development.
