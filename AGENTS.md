# AGENTS.md

## Commands
- No build, test or lint commands exist yet (no manifest). The planned stack is Python (`pyproject.toml`, `uv sync`, `python -m pytest -q`); update this file when it lands.

## Rules
- CI lives in `.github/workflows/ci.yml` and must stay green.
- Never commit with `--no-verify`.
- Never commit game data or binaries (`raw/`, `*.apk`, `*.so`, `global-metadata.dat`); they are gitignored on purpose.
