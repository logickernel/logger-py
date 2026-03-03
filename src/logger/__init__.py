"""Lightweight Python logger that automatically routes logs to Google Cloud Logging or the local console."""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

try:
    from google.cloud import logging as cloud_logging
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False


class Logger(Protocol):
    """Logger interface with all severity methods."""

    def debug(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a debug message."""
        ...

    def info(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log an info message."""
        ...

    def notice(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a notice message."""
        ...

    def warning(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a warning message."""
        ...

    def error(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log an error message."""
        ...

    def critical(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a critical message."""
        ...

    def alert(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log an alert message."""
        ...

    def emergency(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log an emergency message."""
        ...


# Resolved once at module load — no per-call branching.
# LOGGER_TARGET accepts a comma-separated list of backends: "gcp", "console", or "gcp,console".
raw_targets = os.environ.get("LOGGER_TARGET")
targets = None
if raw_targets:
    targets = {t.strip().lower() for t in raw_targets.split(",") if t.strip()}

USE_GCP = ("gcp" in targets) if targets else bool(os.environ.get("GCP_PROJECT"))
USE_CONSOLE = ("console" in targets) if targets else not bool(os.environ.get("GCP_PROJECT"))
CONSOLE_PRETTY = os.environ.get("LOGGER_CONSOLE_FORMAT", "").lower() == "pretty"


def _noop() -> None:
    """No-op function for error handling."""
    pass


# Environment labels — set once at module load
env_labels: Dict[str, str] = {}
if os.environ.get("ENVIRONMENT"):
    env_labels["environment"] = os.environ["ENVIRONMENT"]
if os.environ.get("SERVICE"):
    env_labels["service"] = os.environ["SERVICE"]
if os.environ.get("VERSION"):
    env_labels["version"] = os.environ["VERSION"]

# GCP Log singleton — shared across all logger() calls.
gcp_logger = None
gcp_log_name = None

if USE_GCP and GCP_AVAILABLE:
    try:
        project_id = os.environ.get("GCP_PROJECT")
        if project_id:
            log_name = os.environ.get("LOGGER_NAME") or os.environ.get("K_SERVICE") or "local"
            client = cloud_logging.Client(project=project_id)
            gcp_logger = client.logger(log_name)
            gcp_log_name = log_name
    except Exception:
        gcp_logger = None
        gcp_log_name = None


# Severity mapping for GCP
SEVERITY_MAP = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "NOTICE": "NOTICE",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
    "ALERT": "ALERT",
    "EMERGENCY": "EMERGENCY",
}


# ANSI colors for pretty console (message text only)
_CONSOLE_RED = "\x1b[31m"
_CONSOLE_YELLOW = "\x1b[33m"
_CONSOLE_RESET = "\x1b[0m"


def _console_line(
    emoji: str,
    message: str,
    event: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    scope: Optional[str] = None,
    message_color: Optional[str] = None,
) -> str:
    """Format a pretty console log line: '{emoji} {local timestamp} [(scope) ][[event] ]{message}[\n  {payload}]'"""
    d = datetime.now()
    ts = d.strftime("%Y-%m-%d %H:%M:%S") + "." + str(d.microsecond // 1000).zfill(3)
    scope_part = f"({scope}) " if scope else ""
    event_part = f"[{event}] " if event else ""
    suffix = ""
    if payload:
        payload_json = json.dumps(payload, indent=2)
        # Indent each line with 4 spaces
        indented_payload = "\n".join("    " + line for line in payload_json.split("\n"))
        suffix = f"\n\x1b[38;5;66m{indented_payload}\x1b[0m"
    content = f"{scope_part}{event_part}{message}"
    ts_color = message_color if message_color else "\x1b[90m"
    if message_color:
        content = f"{message_color}{content}{_CONSOLE_RESET}"
    return f"{emoji} {ts_color}{ts}{_CONSOLE_RESET}  {content}{suffix}"


def _console_plain(message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, scope: Optional[str] = None) -> str:
    """Plain console line: '[(scope) ][[event] ]{message}[ {payload}]'"""
    scope_part = f"({scope}) " if scope else ""
    event_part = f"[{event}] " if event else ""
    suffix = ""
    if payload:
        payload_json = json.dumps(payload, separators=(",", ":"))
        # Replace newlines and extra whitespace with single space
        payload_compact = " ".join(payload_json.split())
        suffix = f" {payload_compact}"
    return f"{scope_part}{event_part}{message}{suffix}"


def logger(scope: Optional[str] = None) -> Logger:
    """Create a logger instance with optional scope.

    Args:
        scope: Optional scope label attached to every log entry.

    Returns:
        A Logger instance with all severity methods.
    """
    instance_labels: Dict[str, str] = {**env_labels}
    if scope:
        instance_labels["scope"] = scope

    def resolve_labels(event_name: Optional[str], call_labels: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Merge instance labels with event and per-call labels."""
        merged = {**instance_labels}
        if event_name:
            merged["event"] = event_name
        if call_labels:
            merged.update(call_labels)
        return merged if merged else None

    def gcp_meta(severity: str, event_name: Optional[str], call_labels: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Build GCP entry metadata."""
        labels = resolve_labels(event_name, call_labels)
        if labels:
            return {"severity": severity, "labels": labels}
        return {"severity": severity}

    def gcp_data(message: str, payload: Optional[Dict[str, Any]]) -> Any:
        """Build GCP entry data."""
        if payload:
            return {**payload, "message": message}
        return message

    backends: List[Logger] = []

    # GCP backend
    if gcp_logger:
        g = gcp_logger

        class GcpBackend:
            def __init__(self, logger_instance, meta_func, data_func):
                self._logger = logger_instance
                self._meta = meta_func
                self._data = data_func

            def _log(self, severity: str, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                try:
                    entry_metadata = self._meta(severity, event, labels)
                    entry_data = self._data(message, payload)
                    entry_labels = entry_metadata.get("labels")
                    # GCP client accepts severity as uppercase string (e.g. "INFO")
                    self._logger.log_struct(entry_data, severity=severity, labels=entry_labels)
                except Exception:
                    _noop()

            def _severity_log(self, severity: str, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log(severity, message, event, payload, labels)

            def debug(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("DEBUG", message, event, payload, labels)

            def info(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("INFO", message, event, payload, labels)

            def notice(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("NOTICE", message, event, payload, labels)

            def warning(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("WARNING", message, event, payload, labels)

            def error(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("ERROR", message, event, payload, labels)

            def critical(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("CRITICAL", message, event, payload, labels)

            def alert(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("ALERT", message, event, payload, labels)

            def emergency(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._severity_log("EMERGENCY", message, event, payload, labels)

        backends.append(GcpBackend(g, gcp_meta, gcp_data))

    # Console backend
    if USE_CONSOLE or len(backends) == 0:
        class ConsoleBackend:
            def __init__(self, pretty: bool, scope: Optional[str]):
                self._pretty = pretty
                self._scope = scope

            def _out(self, emoji: str, message: str, event: Optional[str], payload: Optional[Dict[str, Any]], message_color: Optional[str] = None) -> None:
                if self._pretty:
                    print(_console_line(emoji, message, event, payload, self._scope, message_color))
                else:
                    print(_console_plain(message, event, payload, self._scope))

            def debug(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("🐞", message, event, payload)

            def info(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("⚪️", message, event, payload)

            def notice(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("🔵", message, event, payload)

            def warning(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("🟡", message, event, payload, _CONSOLE_YELLOW)

            def error(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("🔴", message, event, payload, _CONSOLE_RED)

            def critical(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("⛔️", message, event, payload, _CONSOLE_RED)

            def alert(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("❗️", message, event, payload, _CONSOLE_RED)

            def emergency(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._out("🚨", message, event, payload, _CONSOLE_RED)

        backends.append(ConsoleBackend(CONSOLE_PRETTY, scope))

    # Return single backend or multi-backend dispatcher
    if len(backends) == 1:
        return backends[0]  # type: ignore

    # Multi-backend dispatcher
    class MultiBackend:
        def __init__(self, backends_list: List[Logger]):
            self._backends = backends_list

        def debug(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.debug(message, event, payload, labels)

        def info(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.info(message, event, payload, labels)

        def notice(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.notice(message, event, payload, labels)

        def warning(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.warning(message, event, payload, labels)

        def error(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.error(message, event, payload, labels)

        def critical(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.critical(message, event, payload, labels)

        def alert(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.alert(message, event, payload, labels)

        def emergency(self, message: str, event: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.emergency(message, event, payload, labels)

    return MultiBackend(backends)  # type: ignore


__all__ = ["logger", "Logger"]
