# AGENTS.md

## Commands
- Install: `pip install -e ".[dev]"` (Python >= 3.11, stdlib-only runtime).
- Test: `python -m pytest -q` (offline, synthetic data).
- Run: `zk status`, `zk tools [names]`, `zk <stage>`; architecture in `docs/architecture.md`.

## Rules
- CI lives in `.github/workflows/ci.yml` and must stay green.
- Never commit with `--no-verify`.
- Never commit game data or binaries (`raw/`, `*.apk`, `*.so`, `global-metadata.dat`); they are gitignored on purpose.
