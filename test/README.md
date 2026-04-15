# Test suite

This directory contains automated tests for both backend (pytest + httpx)
and frontend (vitest). It is intentionally placed at the repo root so tests
from either side can be run with a single command from CI.

## Backend tests

Requirements (already in `backend/requirements.txt` or installed on demand):

```
pip install pytest pytest-asyncio httpx aiosqlite
```

Run from the repository root:

```bash
# Windows / cross-platform
python -m pytest test/backend -v
```

The tests spin up an in-memory SQLite database per test — PostgreSQL is
**not** required. `ARQ / Redis` integrations are stubbed, so tests are
fully hermetic.

### Coverage

| File | Covers |
|---|---|
| `test_config.py` | production safeguards on SECRET_KEY / CORS / ENCRYPTION_KEY |
| `test_auth.py` | login, wrong-password, `/me`, JWT round-trip |
| `test_users.py` | admin-only user management, non-admin is forbidden, password change clears `must_change_password` |
| `test_upload_security.py` | filename sanitisation, path-traversal defence, extension whitelist |
| `test_encryption.py` | API-key encryption/decryption incl. legacy-salt fallback |
| `test_system_settings.py` | system settings CRUD |
| `test_logs.py` | audit middleware records mutating requests; error log captures exceptions; `/api/system/logs` endpoints |
| `test_toes.py` | TOE CRUD smoke test |
| `test_health.py` | `/api/health` liveness |

## Frontend tests

Install vitest (only needed for development machines):

```bash
cd frontend
npm install -D vitest @vue/test-utils jsdom @vitest/coverage-v8
```

Run from the repo root:

```bash
cd test/frontend
npx vitest run
```

The frontend suite is intentionally small — it exercises pure logic
(stores, api helpers) rather than rendering full component trees, which
keeps CI fast and avoids brittle snapshots.
