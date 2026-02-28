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

    def debug(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a debug message."""
        ...

    def info(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log an info message."""
        ...

    def notice(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a notice message."""
        ...

    def warning(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a warning message."""
        ...

    def error(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log an error message."""
        ...

    def critical(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log a critical message."""
        ...

    def alert(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
        """Log an alert message."""
        ...

    def emergency(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
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


def _console_line(emoji: str, message: str, payload: Optional[Dict[str, Any]] = None, scope: Optional[str] = None) -> str:
    """Format a pretty console log line: '{emoji} {local timestamp} [(scope) ]{message}[\n  {payload}]'"""
    d = datetime.now()
    ts = d.strftime("%Y-%m-%d %H:%M:%S") + "." + str(d.microsecond // 1000).zfill(3)
    scope_part = f"({scope}) " if scope else ""
    suffix = ""
    if payload:
        payload_json = json.dumps(payload, indent=2)
        # Indent each line with 4 spaces
        indented_payload = "\n".join("    " + line for line in payload_json.split("\n"))
        suffix = f"\n\x1b[38;5;66m{indented_payload}\x1b[0m"
    return f"{emoji} \x1b[90m{ts}\x1b[0m  {scope_part}{message}{suffix}"


def _console_plain(message: str, payload: Optional[Dict[str, Any]] = None, scope: Optional[str] = None) -> str:
    """Plain console line: '[(scope) ]{message}[ {payload}]'"""
    scope_part = f"({scope}) " if scope else ""
    suffix = ""
    if payload:
        payload_json = json.dumps(payload, separators=(",", ":"))
        # Replace newlines and extra whitespace with single space
        payload_compact = " ".join(payload_json.split())
        suffix = f" {payload_compact}"
    return f"{scope_part}{message}{suffix}"


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

    def resolve_labels(call_labels: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Merge instance labels with per-call labels."""
        merged = {**instance_labels}
        if call_labels:
            merged.update(call_labels)
        return merged if merged else None

    def gcp_meta(severity: str, call_labels: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Build GCP entry metadata."""
        labels = resolve_labels(call_labels)
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

            def _log(self, severity: str, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                try:
                    entry_metadata = self._meta(severity, labels)
                    entry_data = self._data(message, payload)
                    # Convert severity string to GCP severity enum
                    from google.cloud.logging import Severity
                    severity_enum = getattr(Severity, severity, Severity.DEFAULT)
                    entry_labels = entry_metadata.get("labels")
                    self._logger.log_struct(entry_data, severity=severity_enum, labels=entry_labels)
                except Exception:
                    _noop()

            def debug(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("DEBUG", message, payload, labels)

            def info(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("INFO", message, payload, labels)

            def notice(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("NOTICE", message, payload, labels)

            def warning(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("WARNING", message, payload, labels)

            def error(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("ERROR", message, payload, labels)

            def critical(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("CRITICAL", message, payload, labels)

            def alert(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("ALERT", message, payload, labels)

            def emergency(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                self._log("EMERGENCY", message, payload, labels)

        backends.append(GcpBackend(g, gcp_meta, gcp_data))

    # Console backend
    if USE_CONSOLE or len(backends) == 0:
        class ConsoleBackend:
            def __init__(self, pretty: bool, scope: Optional[str]):
                self._pretty = pretty
                self._scope = scope

            def debug(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("🐞", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

            def info(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("⚪️", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

            def notice(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("🔵", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

            def warning(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("🟡", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

            def error(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("🔴", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

            def critical(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("⛔️", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

            def alert(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("❗️", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

            def emergency(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
                if self._pretty:
                    print(_console_line("🚨", message, payload, self._scope))
                else:
                    print(_console_plain(message, payload, self._scope))

        backends.append(ConsoleBackend(CONSOLE_PRETTY, scope))

    # Return single backend or multi-backend dispatcher
    if len(backends) == 1:
        return backends[0]  # type: ignore

    # Multi-backend dispatcher
    class MultiBackend:
        def __init__(self, backends_list: List[Logger]):
            self._backends = backends_list

        def debug(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.debug(message, payload, labels)

        def info(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.info(message, payload, labels)

        def notice(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.notice(message, payload, labels)

        def warning(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.warning(message, payload, labels)

        def error(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.error(message, payload, labels)

        def critical(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.critical(message, payload, labels)

        def alert(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.alert(message, payload, labels)

        def emergency(self, message: str, payload: Optional[Dict[str, Any]] = None, labels: Optional[Dict[str, str]] = None) -> None:
            for backend in self._backends:
                backend.emergency(message, payload, labels)

    return MultiBackend(backends)  # type: ignore


__all__ = ["logger", "Logger"]
