"""Unit tests for the logger module."""

import importlib
import os
import re
from typing import Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

# Type for environment keys
EnvKey = str
ENV_KEYS = ["GCP_PROJECT", "LOGGER_TARGET", "LOGGER_CONSOLE_FORMAT", "ENVIRONMENT", "SERVICE", "VERSION"]


def snapshot_env() -> Dict[EnvKey, Optional[str]]:
    """Snapshot current environment variables."""
    return {k: os.environ.get(k) for k in ENV_KEYS}


def restore_env(snapshot: Dict[EnvKey, Optional[str]]) -> None:
    """Restore environment variables from snapshot."""
    for k in ENV_KEYS:
        v = snapshot.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def apply_env(overrides: Dict[str, Optional[str]]) -> None:
    """Apply environment variable overrides."""
    for k, v in overrides.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def fresh_logger(scope: Optional[str] = None, gcp_logger_override=None):
    """Get a fresh logger instance by reloading the module.
    If gcp_logger_override is set, use it as the GCP backend (for tests that mock GCP)."""
    # Remove the module from cache to force reload
    import sys
    module_name = "logger"
    if module_name in sys.modules:
        del sys.modules[module_name]
    # Also remove the parent package
    if "src.logger" in sys.modules:
        del sys.modules["src.logger"]
    if "src" in sys.modules:
        del sys.modules["src"]
    
    # Import and reload the module
    # Add src to path if not already there
    import os
    src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    
    import logger
    importlib.reload(logger)
    if gcp_logger_override is not None:
        logger.gcp_logger = gcp_logger_override
    return logger.logger(scope)


class TestConsoleBackend:
    """Tests for console backend."""

    original_env: Dict[EnvKey, Optional[str]]

    @classmethod
    def setup_class(cls):
        """Save original environment."""
        cls.original_env = snapshot_env()

    def setup_method(self):
        """Set up test environment."""
        apply_env({
            "GCP_PROJECT": None,
            "LOGGER_TARGET": "console",
            "LOGGER_CONSOLE_FORMAT": "pretty",
        })

    def teardown_method(self):
        """Restore original environment."""
        restore_env(self.original_env)

    @classmethod
    def teardown_class(cls):
        """Restore original environment."""
        restore_env(cls.original_env)

    def test_has_all_severity_functions(self):
        """Test that logger has all severity functions."""
        log = fresh_logger()
        methods = ["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"]
        for method in methods:
            assert hasattr(log, method)
            assert callable(getattr(log, method))

    @patch("builtins.print")
    def test_debug_logs_with_emoji_and_timestamp(self, mock_print):
        """Test debug logs with 🐞 and timestamp."""
        log = fresh_logger()
        log.debug("verbose")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "🐞" in call_args
        assert "verbose" in call_args
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}", call_args)

    @patch("builtins.print")
    def test_info_logs_with_emoji_and_timestamp(self, mock_print):
        """Test info logs with ⚪️ and timestamp."""
        log = fresh_logger()
        log.info("hello")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "⚪️" in call_args
        assert "hello" in call_args

    @patch("builtins.print")
    def test_notice_logs_with_emoji_and_timestamp(self, mock_print):
        """Test notice logs with 🔵 and timestamp."""
        log = fresh_logger()
        log.notice("normal but significant")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "🔵" in call_args
        assert "normal but significant" in call_args

    @patch("builtins.print")
    def test_warning_logs_with_emoji_and_timestamp(self, mock_print):
        """Test warning logs with 🟡 and timestamp."""
        log = fresh_logger()
        log.warning("disk space low")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "🟡" in call_args
        assert "disk space low" in call_args

    @patch("builtins.print")
    def test_error_logs_with_emoji_and_timestamp(self, mock_print):
        """Test error logs with 🔴 and timestamp."""
        log = fresh_logger()
        log.error("something broke")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "🔴" in call_args
        assert "something broke" in call_args

    @patch("builtins.print")
    def test_critical_logs_with_emoji_and_timestamp(self, mock_print):
        """Test critical logs with ⛔️ and timestamp."""
        log = fresh_logger()
        log.critical("primary db down")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "⛔️" in call_args
        assert "primary db down" in call_args

    @patch("builtins.print")
    def test_alert_logs_with_emoji_and_timestamp(self, mock_print):
        """Test alert logs with ❗️ and timestamp."""
        log = fresh_logger()
        log.alert("data loss imminent")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "❗️" in call_args
        assert "data loss imminent" in call_args

    @patch("builtins.print")
    def test_emergency_logs_with_emoji_and_timestamp(self, mock_print):
        """Test emergency logs with 🚨 and timestamp."""
        log = fresh_logger()
        log.emergency("system unusable")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "🚨" in call_args
        assert "system unusable" in call_args

    @patch("builtins.print")
    def test_debug_shows_payload_on_new_indented_line(self, mock_print):
        """Test debug shows payload on new indented line."""
        log = fresh_logger()
        log.debug("user logged in", None, {"userId": "123", "action": "login"})
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "user logged in" in call_args
        assert '"userId": "123"' in call_args
        assert '"action": "login"' in call_args
        # Check for indentation (4 spaces)
        assert "    {" in call_args or call_args.count("    ") > 0

    @patch("builtins.print")
    def test_info_shows_payload_on_new_indented_line(self, mock_print):
        """Test info shows payload on new indented line."""
        log = fresh_logger()
        log.info("request handled", None, {"method": "GET", "status": 200})
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "request handled" in call_args
        assert '"method": "GET"' in call_args
        assert '"status": 200' in call_args

    @patch("builtins.print")
    def test_error_shows_payload_on_new_indented_line(self, mock_print):
        """Test error shows payload on new indented line."""
        log = fresh_logger()
        log.error("request failed", None, {"method": "POST", "status": 500})
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "request failed" in call_args
        assert '"method": "POST"' in call_args
        assert '"status": 500' in call_args

    @patch("builtins.print")
    def test_event_shown_in_brackets_in_pretty_mode(self, mock_print):
        """Test event appears as [event] in pretty console output."""
        log = fresh_logger("api")
        log.info("user logged in", "user_login", {"userId": "u-42"})
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "[user_login]" in call_args
        assert "(api)" in call_args
        assert "user logged in" in call_args

    @patch("builtins.print")
    def test_defaults_to_plain_format_when_not_set(self, mock_print):
        """Test defaults to plain format when LOGGER_CONSOLE_FORMAT is not set."""
        apply_env({
            "GCP_PROJECT": None,
            "LOGGER_TARGET": "console",
            "LOGGER_CONSOLE_FORMAT": None,
        })
        log = fresh_logger()
        log.info("test message")
        mock_print.assert_called_once_with("test message")

    @patch("builtins.print")
    def test_uses_plain_format_when_not_pretty(self, mock_print):
        """Test uses plain format when LOGGER_CONSOLE_FORMAT is not 'pretty'."""
        apply_env({
            "GCP_PROJECT": None,
            "LOGGER_TARGET": "console",
            "LOGGER_CONSOLE_FORMAT": "plain",
        })
        log = fresh_logger()
        log.info("test message", None, {"key": "value"})
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "test message" in call_args
        assert "key" in call_args and "value" in call_args
        # Should not have emoji
        assert "⚪️" not in call_args


class TestMultiBackend:
    """Tests for multi-backend (GCP + console)."""

    original_env: Dict[EnvKey, Optional[str]]

    @classmethod
    def setup_class(cls):
        """Save original environment."""
        cls.original_env = snapshot_env()

    def setup_method(self):
        """Set up test environment with mocked GCP."""
        apply_env({
            "GCP_PROJECT": "test-project",
            "LOGGER_TARGET": "gcp,console",
            "LOGGER_CONSOLE_FORMAT": None,
            "ENVIRONMENT": None,
            "SERVICE": None,
            "VERSION": None,
        })

    def teardown_method(self):
        """Restore original environment."""
        restore_env(self.original_env)

    @classmethod
    def teardown_class(cls):
        """Restore original environment."""
        restore_env(cls.original_env)

    @patch("builtins.print")
    def test_writes_to_both_gcp_and_console_on_info(self, mock_print):
        """Test writes to both GCP and console on info."""
        mock_logger = MagicMock()
        log = fresh_logger(gcp_logger_override=mock_logger)
        log.info("dual write")

        # Check console was called
        mock_print.assert_called()
        # Check GCP was called
        assert mock_logger.log_struct.called

    @patch("builtins.print")
    def test_writes_to_both_gcp_and_console_on_error(self, mock_print):
        """Test writes to both GCP and console on error."""
        mock_logger = MagicMock()
        log = fresh_logger(gcp_logger_override=mock_logger)
        log.error("something broke")

        # Check console was called
        mock_print.assert_called()
        # Check GCP was called
        assert mock_logger.log_struct.called

    @patch("builtins.print")
    def test_order_in_logger_target_does_not_matter(self, mock_print):
        """Test order in LOGGER_TARGET does not matter (console,gcp)."""
        apply_env({"LOGGER_TARGET": "console,gcp"})
        mock_logger = MagicMock()
        log = fresh_logger(gcp_logger_override=mock_logger)
        log.warning("order check")

        # Check console was called
        mock_print.assert_called()
        # Check GCP was called
        assert mock_logger.log_struct.called


class TestGcpBackendLabels:
    """Tests for GCP backend label handling."""

    original_env: Dict[EnvKey, Optional[str]]

    @classmethod
    def setup_class(cls):
        """Save original environment."""
        cls.original_env = snapshot_env()

    def setup_method(self):
        """Set up test environment with mocked GCP."""
        apply_env({
            "GCP_PROJECT": "test-project",
            "LOGGER_TARGET": None,
            "LOGGER_CONSOLE_FORMAT": None,
            "ENVIRONMENT": None,
            "SERVICE": None,
            "VERSION": None,
        })

    def teardown_method(self):
        """Restore original environment."""
        restore_env(self.original_env)

    @classmethod
    def teardown_class(cls):
        """Restore original environment."""
        restore_env(cls.original_env)

    def test_attaches_all_labels_when_env_vars_set(self):
        """Test attaches all labels when ENVIRONMENT, SERVICE, and VERSION are set."""
        os.environ["ENVIRONMENT"] = "production"
        os.environ["SERVICE"] = "my-service"
        os.environ["VERSION"] = "1.2.3"
        mock_logger = MagicMock()
        log = fresh_logger(gcp_logger_override=mock_logger)
        log.info("hello")

        # Check that log_struct was called with correct labels
        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels", {})
        assert labels.get("environment") == "production"
        assert labels.get("service") == "my-service"
        assert labels.get("version") == "1.2.3"

        # Cleanup
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("SERVICE", None)
        os.environ.pop("VERSION", None)

    def test_attaches_only_present_labels(self):
        """Test attaches only present labels when some vars are unset."""
        os.environ["SERVICE"] = "my-service"
        mock_logger = MagicMock()
        log = fresh_logger(gcp_logger_override=mock_logger)
        log.info("hello")

        # Check that log_struct was called with correct labels
        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels", {})
        assert labels.get("service") == "my-service"
        assert "environment" not in labels
        assert "version" not in labels

        # Cleanup
        os.environ.pop("SERVICE", None)

    def test_omits_labels_when_no_label_vars_set(self):
        """Test omits labels entirely when no label vars are set."""
        mock_logger = MagicMock()
        log = fresh_logger(gcp_logger_override=mock_logger)
        log.info("hello")

        # Check that log_struct was called
        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels")
        # Labels should be None or empty when no env vars are set
        assert labels is None or labels == {}

    def test_attaches_event_as_label_when_provided(self):
        """Test event string is attached as labels.event in GCP."""
        mock_logger = MagicMock()
        log = fresh_logger("payments", gcp_logger_override=mock_logger)
        log.info("charge processed", "charge_processed", {"amount": 99.95})

        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels", {})
        assert labels.get("scope") == "payments"
        assert labels.get("event") == "charge_processed"

    def test_attaches_scope_label_from_factory_argument(self):
        """Test attaches scope label from factory argument."""
        mock_logger = MagicMock()
        log = fresh_logger("my-scope", gcp_logger_override=mock_logger)
        log.info("hello")

        # Check that log_struct was called with scope label
        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels", {})
        assert labels.get("scope") == "my-scope"

    def test_attaches_per_call_labels(self):
        """Test attaches per-call labels from fourth argument."""
        mock_logger = MagicMock()
        log = fresh_logger(gcp_logger_override=mock_logger)
        log.info("hello", None, None, {"requestId": "req-1"})

        # Check that log_struct was called with per-call labels
        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels", {})
        assert labels.get("requestId") == "req-1"

    def test_merges_scope_and_per_call_labels(self):
        """Test merges scope and per-call labels."""
        mock_logger = MagicMock()
        log = fresh_logger("api", gcp_logger_override=mock_logger)
        log.info("hello", None, None, {"traceId": "t-1"})

        # Check that log_struct was called with merged labels
        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels", {})
        assert labels.get("scope") == "api"
        assert labels.get("traceId") == "t-1"

    def test_merges_env_labels_scope_and_per_call_labels(self):
        """Test merges env labels, scope, and per-call labels."""
        os.environ["ENVIRONMENT"] = "staging"
        mock_logger = MagicMock()
        log = fresh_logger("worker", gcp_logger_override=mock_logger)
        log.info("hello", None, None, {"jobId": "j-99"})

        # Check that log_struct was called with all merged labels
        assert mock_logger.log_struct.called
        call_kwargs = mock_logger.log_struct.call_args[1]
        labels = call_kwargs.get("labels", {})
        assert labels.get("environment") == "staging"
        assert labels.get("scope") == "worker"
        assert labels.get("jobId") == "j-99"

        # Cleanup
        os.environ.pop("ENVIRONMENT", None)
