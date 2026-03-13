# Claude Instructions for ice9-sdk

## Before Publishing

**Read `PUBLISHING.md` before doing anything related to a release or PyPI upload.**

It covers the full checklist, the correct build and upload commands, and how to
source credentials from `.env` without mangling the token.

Key points:
- Version bumps happen **only when publishing to PyPI**, not on every GitHub commit
- Build with `venv/bin/python -m build`
- Upload with `set -a && source .env && set +a` then `venv/bin/twine upload dist/ice9-X.Y.Z*`
- Run unit tests (`pytest tests/ --ignore=tests/integration`) before committing
- Run integration tests (`ICE9_API_KEY=... pytest tests/integration/ -v`) before publishing

## Project Layout

- `ice9/` — SDK source
- `tests/` — unit tests; `tests/integration/` — integration tests (require API key)
- `issues/` — open issues; `issues/resolved/` — resolved
- `examples/` — runnable scripts and notebooks
- `CHANGELOG.md` — all notable changes, updated with every release
- `PUBLISHING.md` — release runbook (read before publishing)
- `.env` — credentials (gitignored)
- `venv/` — virtualenv (gitignored)

## Use the Reference Material

`images/z-test-premium-raw.json` is a captured API response from a real premium
analysis. **Read it before implementing anything that touches data shapes** —
postprocessing entries, service result fields, nested structures, etc.

Do not guess at field names or data shapes. Do not assume the happy path covers
it. If the reference JSON shows a `cluster_id` inside `data`, that means the
aggregation code needs to handle `cluster_id`. Check first, code second.

If the reference JSON is stale (new services added, schema changed, etc.), refresh it:

```bash
set -a && source .env && set +a
python3 - <<'EOF'
import json, os, ice9
client = ice9.Ice9(api_key=os.environ["API_KEY"])
result = client.analyze("images/z-test.jpg", tier="premium", timeout=120.0)
with open("images/z-test-premium-raw.json", "w") as f:
    json.dump(result._raw, f, indent=2, default=str)
print(f"Saved image_id={result.image_id}")
EOF
```

Update the reference after any significant API-side change (new services, schema
migrations, new postprocessing entries). The file is gitignored — it stays local.

## Conventions

- `POLL_INTERVAL = 0.25` (quarter-second polling floor)
- `ServiceResult.text` → `predictions[0]["text"]` for VLMs
- Postprocessing entries are injected into `service_results` at build time
- `caption_score_*` entries are aggregated into a single `caption_scores` ServiceResult
- `rembg` arrives as a top-level API key and is injected into `service_results`
- Version policy: `0.0.x` — pre-stable, anything can change; see `issues/sdk-versioning-policy.md`
