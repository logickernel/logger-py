# logickernel-logger — Implementation Skill

Authoritative reference for implementing and modifying `src/logger/__init__.py` and its tests. All invariants here are normative — the tests enforce them.

---

## Repository & installation

**Source**: https://github.com/logickernel/logger-py

**Install for users:**
```bash
pip install git+https://github.com/logickernel/logger-py.git
```

**Install for development** (clone first, then editable install with dev extras):
```bash
git clone https://github.com/logickernel/logger-py.git
cd logger-py
pip install -e ".[dev]"
```

The installed package name is `logickernel-logger`; the importable module name is `logger`.

---

## File layout

```
src/logger/__init__.py   # entire implementation — single file, no sub-modules
tests/test_logger.py     # unit tests (mock GCP)
tests/test_logger_integration.py  # integration tests (real GCP, skipped locally)
```

---

## Public API

```python
# install: pip install git+https://github.com/logickernel/logger-py.git
from logger import logger, Logger

log: Logger = logger("scope")   # scope is optional
log.info("message", {"key": val}, {"label": "val"})
```

### `logger(scope?)` factory

- Takes one optional positional arg: `scope: str | None = None`
- Returns a `Logger` instance
- **Called once per module** — never inside request handlers or loops
- Backend (GCP vs console) is resolved **once at module load**, not per call

### `Logger` protocol — 8 severity methods

All share the identical signature:

```python
def <severity>(
    self,
    message: str,
    payload: dict[str, Any] | None = None,
    labels: dict[str, str] | None = None,
) -> None
```

| Method | GCP severity | Console emoji | Color |
|---|---|---|---|
| `debug` | `DEBUG` | 🐞 | — |
| `info` | `INFO` | ⚪️ | — |
| `notice` | `NOTICE` | 🔵 | — |
| `warning` | `WARNING` | 🟡 | yellow |
| `error` | `ERROR` | 🔴 | red |
| `critical` | `CRITICAL` | ⛔️ | red |
| `alert` | `ALERT` | ❗️ | red |
| `emergency` | `EMERGENCY` | 🚨 | red |

ANSI colors apply to the message text in pretty mode: `\x1b[33m` (yellow), `\x1b[31m` (red), reset `\x1b[0m`.

---

## Module-level setup (resolved once at import)

```python
# 1. Parse LOGGER_TARGET
raw_targets = os.environ.get("LOGGER_TARGET")
targets = {t.strip().lower() for t in raw_targets.split(",") if t.strip()} if raw_targets else None

# 2. Backend flags
USE_GCP     = ("gcp"     in targets) if targets else bool(os.environ.get("GCP_PROJECT"))
USE_CONSOLE = ("console" in targets) if targets else not bool(os.environ.get("GCP_PROJECT"))

# 3. Console format — pretty is DEFAULT; plain only when explicitly set
CONSOLE_PRETTY = os.environ.get("LOGGER_CONSOLE_FORMAT", "").lower() != "plain"

# 4. Environment labels (attached to every GCP entry)
env_labels = {}
for key, label in [("ENVIRONMENT", "environment"), ("SERVICE", "service"), ("VERSION", "version")]:
    if os.environ.get(key):
        env_labels[label] = os.environ[key]

# 5. GCP singleton
gcp_logger = None   # google.cloud.logging Logger instance, or None
```

### GCP singleton init

```python
if USE_GCP and GCP_AVAILABLE:
    try:
        project_id = os.environ.get("GCP_PROJECT")
        if project_id:
            log_name = os.environ.get("LOGGER_NAME") or os.environ.get("K_SERVICE") or "local"
            client = cloud_logging.Client(project=project_id)
            gcp_logger = client.logger(log_name)
    except Exception:
        gcp_logger = None   # silent fallback to console
```

`GCP_AVAILABLE` is `True` only if `from google.cloud import logging as cloud_logging` succeeds.

---

## Backend selection inside `logger(scope)`

```
gcp_logger is not None  →  build GcpBackend, append to backends[]
USE_CONSOLE or len(backends)==0  →  build ConsoleBackend, append to backends[]
len(backends)==1  →  return backends[0] directly
len(backends)==2  →  return MultiBackend(backends)
```

The `len(backends)==0` guard ensures a ConsoleBackend is always created when the GCP singleton failed to initialize — this is the fallback path.

---

## Label merging

```python
instance_labels = {**env_labels}
if scope:
    instance_labels["scope"] = scope

def resolve_labels(call_labels):
    merged = {**instance_labels}
    if call_labels:
        merged.update(call_labels)
    return merged if merged else None
```

Precedence (highest last, wins): `env_labels` → `scope` → `call_labels`

Labels are passed to `gcp_logger.log_struct(..., labels=resolved_labels)`. Console backend ignores `labels` entirely.

---

## GCP entry structure

```python
def gcp_data(message, payload):
    if payload:
        return {**payload, "message": message}   # jsonPayload with message merged in
    return message                                # plain string entry
```

`log_struct` call:
```python
gcp_logger.log_struct(entry_data, severity=severity, labels=entry_labels)
```

`severity` is the uppercase string: `"DEBUG"`, `"INFO"`, `"NOTICE"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`, `"ALERT"`, `"EMERGENCY"`.

Exceptions in the GCP backend are swallowed silently (no re-raise, no fallback print).

---

## Console output

### Pretty (default)

```
{emoji} {dim_ts}  {(scope) }{colored_message}
    {
      "key": "value"
    }
```

- Timestamp: `datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "." + str(microsecond//1000).zfill(3)`
- Timestamp ANSI: `\x1b[90m` (dim grey) unless `message_color` is set, then uses `message_color` for timestamp too
- Scope: `"({scope}) "` prefix before message, omitted when no scope
- Message color: wraps `{scope_part}{message}` with `{color}...{reset}`
- Payload: `json.dumps(payload, indent=2)`, each line prefixed with 4 spaces, wrapped in `\x1b[38;5;66m...\x1b[0m` (muted blue-grey), on a new line after message
- No payload → no trailing newline

### Plain (`LOGGER_CONSOLE_FORMAT=plain`)

```
{(scope) }{message}{ compact_json}
```

- `json.dumps(payload, separators=(",", ":"))` then `" ".join(value.split())` (collapse whitespace)
- Single space before payload
- No emoji, no timestamp, no ANSI codes

---

## Class structure inside `logger(scope)`

All three backend classes are **defined inside** the `logger()` function (closures). They are not module-level classes.

```
GcpBackend      — holds _logger, _meta, _data; _log() dispatches to log_struct
ConsoleBackend  — holds _pretty, _scope; _out() dispatches to print
MultiBackend    — holds _backends list; each method fans out to all backends
```

The `Logger` class is a `Protocol` at module level for type-checking only.

---

## Environment variables — complete list

| Variable | Effect |
|---|---|
| `GCP_PROJECT` | Enables GCP backend; used as project ID for Cloud Logging client |
| `LOGGER_TARGET` | Comma-separated override: `"gcp"`, `"console"`, `"gcp,console"` |
| `LOGGER_NAME` | Log name in Cloud Logging. Falls back to `K_SERVICE`, then `"local"` |
| `K_SERVICE` | Fallback log name (set automatically by Cloud Run) |
| `LOGGER_CONSOLE_FORMAT` | Set to `"plain"` to disable pretty formatting. Default: pretty |
| `ENVIRONMENT` | Added as `labels.environment` on every GCP entry |
| `SERVICE` | Added as `labels.service` on every GCP entry |
| `VERSION` | Added as `labels.version` on every GCP entry |

---

## Test conventions

- `fresh_logger(scope, gcp_logger_override)` — deletes `"logger"` / `"src.logger"` / `"src"` from `sys.modules`, then `importlib.reload(logger)`. Call **after** `apply_env()` so module-level resolution picks up new env vars.
- `gcp_logger_override` — assigned to `logger.gcp_logger` after reload to inject a `MagicMock`.
- `apply_env({key: None})` removes the key; `apply_env({key: "val"})` sets it.
- `snapshot_env()` / `restore_env()` used in `setup_class` / `teardown_class` to bracket test classes.
- GCP call assertions use `mock_logger.log_struct.call_args[1]` (kwargs) to inspect `severity=` and `labels=`.

### Key test invariants

1. All 8 severity methods exist and are callable.
2. Pretty format includes emoji + timestamp regex `\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}`.
3. Pretty is the **default** — no `LOGGER_CONSOLE_FORMAT` set → emoji present.
4. `LOGGER_CONSOLE_FORMAT=plain` → no emoji, message + compact payload on one line.
5. `scope` appears as `(scope)` in pretty output.
6. Payload fields appear in `call_args[1]["labels"]` when passed as `labels` kwarg to GCP.
7. Multi-backend: both `mock_print` and `mock_logger.log_struct` are called.
8. `LOGGER_TARGET="console,gcp"` (reversed order) behaves identically to `"gcp,console"`.
9. `env_labels` only includes keys for env vars that are actually set (no None entries).
10. Per-call labels override nothing from scope/env — they are merged with `merged.update(call_labels)`.

---

## Coding constraints

- **No module-level classes for backends** — they must be defined inside `logger()` as closures.
- **No per-call branching on USE_GCP/USE_CONSOLE** — backend list is fixed at factory call time.
- **No exceptions propagated** from GCP backend — always catch `Exception` and swallow.
- **`google.cloud.logging` import is optional** — wrap in `try/except ImportError`, set `GCP_AVAILABLE`.
- **Single file** — do not split into multiple modules.
- **`__all__ = ["logger", "Logger"]`** — only these two are public exports.
