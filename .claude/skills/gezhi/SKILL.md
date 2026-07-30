---
name: gezhi
description: Repository-specific Python, testing, migration, and packaging conventions for GEZHI contributors.
version: 1.0.0
---

# GEZHI Development Patterns

> Repository-specific guidance for the GEZHI Python project.

## Python Conventions

- Name modules and functions with `snake_case`, classes with `PascalCase`, and
  constants with `UPPER_SNAKE_CASE`.
- Use relative imports between modules inside `src/gezhi/`.
- Keep public exports deliberate. Define `__all__` only when a module exposes a
  supported public surface.
- Preserve `goal` in domain and upstream names such as `GoalConfig`,
  `codex_goal`, and Codex `/goal`; GEZHI is the product identity.

## Tests

- Put tests in `tests/` and name files `test_*.py`.
- Add regression coverage for behavior changes, especially state durability,
  scheduler installation, repository locking, and fail-closed migration.
- Run the repository checks before committing:

  ```bash
  python -m ruff check src tests
  python -m mypy src
  python -m pytest -q tests
  ```

## Repository Identity

- The distribution, import package, and command are all `gezhi`.
- The default configuration is `gezhi.toml`; durable runtime state lives in
  `.gezhi/`; GEZHI-owned environment variables use the `GEZHI_` prefix.
- Earlier product identifiers belong only in the explicit migration guard and
  migration guide. Do not add compatibility aliases or a second state root.

## Changes and Commits

- Keep changes scoped and preserve unrelated user files in a dirty worktree.
- Use an appropriate Conventional Commit type such as `feat:`, `fix:`,
  `docs:`, or `test:` with a concise description.
- Build and smoke-test the wheel when changing packaging, imports, or the CLI.
