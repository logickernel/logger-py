## logickernel-logger

Lightweight Python logger that automatically routes logs to **Google Cloud Logging** (when available) or the **local console**. Designed for services and tools where you want structured logs in GCP without wiring up a full logging stack.

```python
from logger import logger

log = logger("api")  # optional scope label on every entry

log.notice("server started", {"startupMs": 432})
log.info("user login", {"userId": "123"})
log.warning("disk space low", {"usedPct": 92}, {"mount": "/data"})
```

> Your code never has to care whether it's running on Cloud Run / GCP or locally – the logger picks the right backend at startup.

---

## 1. Introduction

- **What it is**: A tiny logging helper with the full GCP severity ladder and a configurable backend:
  - In **GCP** (or when `LOGGER_TARGET=gcp`): writes to Google Cloud Logging with proper severities and structured `jsonPayload` when a payload object is provided.
  - On the **console**: writes with emoji prefixes, a local timestamp, and the payload inlined as compact JSON.
  - **Both at once**: set `LOGGER_TARGET=gcp,console` to fan out to both.
- **Why it exists**: To make it easy to produce structured, queryable telemetry from any Python service without wiring up a separate metrics stack. Log entries are first-class data points: their `jsonPayload` fields and labels feed directly into Cloud Monitoring log-based metrics and dashboards.

**Key features**

- **Zero config in GCP**: Uses `LOGGER_NAME` / `K_SERVICE` and `GCP_PROJECT` from the environment.
- **Auto backend selection**: GCP vs console decided once at module load; override with `LOGGER_TARGET`.
- **Multi-backend**: `LOGGER_TARGET` accepts a comma-separated list — `"gcp,console"` writes to both simultaneously.
- **Full severity ladder**: `debug`, `info`, `notice`, `warning`, `error`, `critical`, `alert`, `emergency`.
- **Structured context**: Pass a plain dict as the second argument — it becomes a `jsonPayload` in GCP (queryable by field) and inline JSON in the console.
- **Scope**: `logger("name")` attaches a `scope` label to every entry, great for filtering by component.
- **Per-call labels**: Pass a third argument to attach GCP labels to a single entry (e.g. `provider`, `region`, `method`).

---

## 2. Installation & Usage

### Install from PyPI

```bash
pip install logickernel-logger
```

### Basic usage

```python
from logger import logger

# Scopeless logger — fine for scripts and simple tools
log = logger()

log.notice("server started")
log.debug("cache miss")
log.warning("disk space low", {"usedPct": 92}, {"mount": "/data"})
log.error("request failed", {"status": 503, "ms": 1250}, {"method": "POST", "route": "/api/orders"})
log.critical("primary db unreachable", {"retries": 3}, {"host": "db-1"})

# Scoped logger — attaches scope: "api" to every entry as a GCP label
api_log = logger("api")
api_log.info("request handled", {"ms": 55, "status": 200}, {"method": "GET"})

# Per-call labels — merged with scope and env labels for that entry only
api_log.info("request handled", {"ms": 42, "status": 200}, {"method": "GET", "route": "/users"})
```

`logger(scope=None)` returns a `Logger` instance. Call it once per module or service boundary. The backend (GCP or console) is chosen once at module load:

- **GCP backend** is used when `GCP_PROJECT` is set.
- Otherwise, the **console backend** is used.

### Method signature

All eight severity methods share the same signature:

```python
log.info(message: str, payload: dict[str, Any] | None = None, labels: dict[str, str] | None = None) -> None
```

- **`message`** — required string.
- **`payload`** — optional plain dict. Becomes `jsonPayload` in GCP (fields indexed and queryable); inlined as compact JSON on the console.
- **`labels`** — optional per-call labels merged with scope and env labels (GCP only; ignored on console).

### Severity methods

| Method | GCP severity | Console emoji | When to use |
|---|---|---|---|
| `debug` | `DEBUG` | 🐞 | Debug or trace information |
| `info` | `INFO` | ⚪️ | Routine information, such as ongoing status or performance |
| `notice` | `NOTICE` | 🔵 | Normal but significant events, such as start up, shut down, or a configuration change |
| `warning` | `WARNING` | 🟡 | Warning events that might cause problems |
| `error` | `ERROR` | 🔴 | Error events that are likely to cause problems |
| `critical` | `CRITICAL` | ⛔️ | Critical events that cause more severe problems or outages |
| `alert` | `ALERT` | ❗️ | A person must take an action immediately |
| `emergency` | `EMERGENCY` | 🚨 | One or more systems are unusable |

### Scope

`logger(scope)` attaches a `scope` label to every entry, letting you filter by component in Cloud Logging:

```python
db = logger("db")
db.warning("slow query", {"ms": 412, "rows": 5200})
# GCP entry: labels.scope = "db"
```

### Structured context

Pass a plain dict as the second argument to attach structured data to a log entry:

```python
log.info("request complete", {"status": 200, "ms": 42}, {"method": "GET", "route": "/api/users"})
```

- **GCP backend**: written as `jsonPayload` — fields are indexed and queryable in Cloud Logging.
- **Console backend**: inlined as spaced JSON on the same line.

### Per-call labels

Pass a `dict[str, str]` as the third argument to attach labels to a single entry (GCP only). They are merged with env labels and scope, with per-call values taking precedence:

```python
log.info("payment processed", {"amount": 99, "orderId": "o-4421"}, {"provider": "stripe", "currency": "usd"})
# GCP entry: labels = { ...envLabels, scope: "...", provider: "stripe", currency: "usd" }
```

### Console format

By default, console logs are plain: `[(scope) ]message[ {payload}]` without emoji or timestamp.

When `LOGGER_CONSOLE_FORMAT=pretty`, the output mimics the [GCP Log Explorer](https://cloud.google.com/logging/docs/view/logs-explorer-interface) — severity as an emoji, a local timestamp, and the payload expanded below the message — so local development feels close to what you see when browsing entries in production. Console logs look like:

```
🔵 2026-02-26 13:04:22.120  server started
🐞 2026-02-26 13:04:22.341  (api) cache miss
    {
      "key": "user:42",
      "ttl": 300
    }
🟡 2026-02-26 13:04:22.512  disk space low
    {
      "used": "92%",
      "mount": "/data"
    }
```

Scope (if set) appears in parentheses before the message. Payload (if any) is printed on the next line with 4-space indentation. Labels are GCP metadata and are not shown on the console.

### Environment variables

- `LOGGER_NAME`
  Log name in Google Cloud Logging. This is a very important attribute that is the primary group in reports — logs are usually grouped by system instance/environment so entries stay together. Falls back to `K_SERVICE`, then `"local"`.

- `GCP_PROJECT`
  Project ID for Google Cloud Logging. When set (and `LOGGER_TARGET` isn't forcing console), the GCP backend is used.

- `LOGGER_TARGET`
  Comma-separated list of backends to activate: `"gcp"`, `"console"`, or `"gcp,console"` for both simultaneously. When unset, GCP is used if `GCP_PROJECT` is set, otherwise console.

- `LOGGER_CONSOLE_FORMAT`
  Controls the console output format. When set to `"pretty"`, uses emoji + timestamp lines to emulate GCP's log viewer; otherwise (default) prints plain `message [payload]` without emoji or timestamp.

- `ENVIRONMENT`
  Attached as `labels.environment` on every GCP entry. Useful for filtering by `"production"`, `"staging"`, etc.

- `SERVICE`
  Attached as `labels.service` on every GCP entry.

- `VERSION`
  Attached as `labels.version` on every GCP entry.

- `K_SERVICE`
  Fallback log name in Google Cloud Logging when `LOGGER_NAME` is not set. Usually set automatically by Google Cloud Run.

### Imports

```python
from logger import logger, Logger

log: Logger = logger("my-scope")
```

---

## 3. Best Practices

### Purpose: structured telemetry, not just log lines

Every log entry written to Cloud Logging is a queryable data point. The goal is to make those entries useful beyond text search: payload fields become extractable metric values (latency, counts, sizes), and labels become the dimensions you filter and group by in Cloud Monitoring dashboards and alerting policies.

### Write specific, past-tense messages

The message is what you read when scanning a log stream — it should be self-explanatory without opening the payload. Use a specific past-tense phrase.

| Avoid | Prefer |
|---|---|
| `"error"` | `"payment charge failed"` |
| `"db error"` | `"query timed out"`, `"connection pool exhausted"` |
| `"user action"` | `"user login"`, `"password reset requested"` |
| `"job done"` | `"invoice batch processed"`, `"report generated"` |

Payload fields and labels exist for querying and metrics — the message is for humans.

### Payload carries values; labels carry categories

The two data arguments serve distinct roles and should not be mixed:

| | `payload` — 2nd arg | `labels` — scope + 3rd arg |
|---|---|---|
| Type | `dict[str, Any]` | `dict[str, str]` — strings only |
| Purpose | Measurements and event data | Categorization and filtering |
| GCP storage | Indexed as `jsonPayload` fields | Stored as entry labels |
| Metrics use | Field values extracted into metric data points | Dimensions for aggregation and segmentation |
| Cardinality | Can be high (IDs, URLs, queries) | Must be low (bounded enums and categories) |

**Put measurements and context in payload — always as numbers, not strings:**

```python
log.info("request handled",     {"ms": 42, "status": 200, "bytes": 1024})
log.info("cache result",        {"hit": True, "ttl": 300})
log.warning("slow query",       {"ms": 850, "rowsScanned": 12000})
log.info("batch job complete",  {"processed": 142, "failed": 3, "durationMs": 5400})
```

Measurements must be numbers — `usedPct: 92`, not `used: "92%"`. Strings cannot be extracted as metric values in Cloud Monitoring.

**Put grouping dimensions in labels:**

```python
# scope sets a label on every entry from this logger
log = logger("payments")

# per-call labels add event-specific dimensions
log.info("charge processed", {"amount": 99.95}, {"provider": "stripe", "currency": "usd"})
log.warning("charge failed",   {"code": "card_declined"}, {"provider": "stripe"})
```

### Keep label cardinality low

Labels become metric dimensions. High-cardinality values — user IDs, request IDs, raw URLs with path parameters — will explode the cardinality of any metric built on them and will be rejected or silently dropped by Cloud Monitoring. Put those values in the payload instead.

```python
# Good — labels are bounded, payload carries the variable data
log.info("payment processed", {"amount": 99.95, "userId": "u-9182", "orderId": "o-4421"}, {"provider": "stripe"})

# Avoid — userId in labels has unbounded cardinality
log.info("payment processed", {"amount": 99.95}, {"provider": "stripe", "userId": "u-9182"})
```

### Instantiate once per module or service boundary

Create the logger at module scope, not inside request handlers or loops. The factory is lightweight, but calling it repeatedly is unnecessary and loses the benefit of a stable scope label.

```python
# Good — created once, reused everywhere in this module
log = logger("orders")

async def create_order(data: OrderData):
    log.info("order created", {"orderId": data.id, "total": data.total})

# Avoid — recreated on every call
async def create_order(data: OrderData):
    logger("orders").info("order created", {"orderId": data.id, "total": data.total})
```

### Building log-based metrics in Cloud Monitoring

Once entries flow into Cloud Logging you can create log-based metrics in a few steps:

1. Open **Cloud Logging → Log-based Metrics → Create metric**.
2. Set a filter to scope the metric, e.g.:
   ```
   logName="projects/MY_PROJECT/logs/MY_LOG"
   severity="INFO"
   jsonPayload.ms > 0
   ```
3. For a **distribution metric** (e.g. request latency), set the **field extractor** to `jsonPayload.ms`.
4. Add **label extractors** for the dimensions you want to slice by, e.g. `labels.scope`, `labels."service"`.
5. Chart the metric in **Cloud Monitoring** or attach an alerting policy (e.g. p99 latency > 500 ms).

---

## 4. Local Setup (Development)

### Prerequisites

- **Python**: 3.8+ recommended (any actively supported version should work).
- **pip** (or compatible package manager).

### Clone and install

```bash
git clone https://github.com/logickernel/logger-py.git
cd logger-py
pip install -e ".[dev]"
```

### Useful commands

```bash
# Run tests
pytest

# Run unit tests only
pytest tests/test_logger.py

# Run integration tests (requires GCP_PROJECT set)
pytest tests/test_logger_integration.py

# Type-check
mypy src/
```

---

## 5. Additional Resources

- **Package**: `logickernel-logger` on PyPI.
- **License**: MIT (see `LICENSE` in this repository).
- **Contributions**: Feel free to open issues or pull requests if you'd like improvements (extra transports, richer metadata, etc.).
