"""Integration tests for the logger module with actual GCP Cloud Logging."""

import importlib
import os
import sys
import time
from typing import Any, Dict, Optional

import pytest
from google.cloud import logging as cloud_logging

PROJECT = "logickernel-logger"
LOG_NAME = "app"


def poll_for_entry(
    test_id: str,
    severity: str,
    attempts: int = 10,
    interval_ms: int = 5000,
) -> Optional[Dict[str, Any]]:
    """Poll until an entry containing test_id appears in Cloud Logging.
    
    No startTime filter — testIds are unique per run (contain timestamp), so old
    entries from previous runs can never accidentally match.
    """
    logging_client = cloud_logging.Client(project=PROJECT)
    filter_str = f'logName="projects/{PROJECT}/logs/{LOG_NAME}" AND severity="{severity}"'

    for _ in range(attempts):
        time.sleep(interval_ms / 1000.0)
        entries = logging_client.list_entries(filter_=filter_str, page_size=20, order_by="timestamp desc")
        for entry in entries:
            data = entry.payload if hasattr(entry, "payload") else entry.data
            if isinstance(data, str):
                if test_id in data:
                    return {
                        "data": data,
                        "metadata": {
                            "severity": entry.severity,
                            "labels": entry.labels if hasattr(entry, "labels") else None,
                        },
                    }
            elif isinstance(data, dict):
                data_str = str(data)
                if test_id in data_str:
                    return {
                        "data": data,
                        "metadata": {
                            "severity": entry.severity,
                            "labels": entry.labels if hasattr(entry, "labels") else None,
                        },
                    }
    return None


class TestGcpBackendIntegration:
    """Integration tests for GCP backend."""

    saved_env: Dict[str, Optional[str]]

    @classmethod
    def setup_class(cls):
        """Save and set up environment for GCP tests."""
        cls.saved_env = {}
        for k in ["GCP_PROJECT", "LOGGER_NAME", "LOGGER_TARGET"]:
            cls.saved_env[k] = os.environ.get(k)
        os.environ["GCP_PROJECT"] = PROJECT
        os.environ["LOGGER_NAME"] = LOG_NAME
        os.environ["LOGGER_TARGET"] = "gcp"

    @classmethod
    def teardown_class(cls):
        """Restore original environment."""
        for k, v in cls.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def smoke_test(self, severity: str, log_method_name: str):
        """Run a smoke test for a specific severity level."""
        # Reload module
        if "logger" in sys.modules:
            del sys.modules["logger"]
        if "src.logger" in sys.modules:
            del sys.modules["src.logger"]
        if "src" in sys.modules:
            del sys.modules["src"]
        
        # Add src to path if not already there
        import os
        src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        import logger
        importlib.reload(logger)
        
        log = logger.logger()
        test_id = f"it-{severity.lower()}-{int(time.time() * 1000)}"
        message = f"smoke: {severity.lower()} [{test_id}]"
        
        # Call the appropriate log method
        log_method = getattr(log, log_method_name)
        log_method(message)
        
        # Poll for the entry
        entry = poll_for_entry(test_id, severity)
        assert entry is not None, f"no {severity} entry arrived within timeout"
        assert entry["data"] == message or (isinstance(entry["data"], dict) and entry["data"].get("message") == message)
        # Check severity (may be string or enum)
        entry_severity = entry["metadata"]["severity"]
        if hasattr(entry_severity, "name"):
            assert entry_severity.name == severity
        else:
            assert str(entry_severity) == severity

    @pytest.mark.timeout(60)
    def test_writes_debug_entry_to_cloud_logging(self):
        """Test writes DEBUG entry to Cloud Logging."""
        self.smoke_test("DEBUG", "debug")

    @pytest.mark.timeout(60)
    def test_writes_info_entry_to_cloud_logging(self):
        """Test writes INFO entry to Cloud Logging."""
        self.smoke_test("INFO", "info")

    @pytest.mark.timeout(60)
    def test_writes_notice_entry_to_cloud_logging(self):
        """Test writes NOTICE entry to Cloud Logging."""
        self.smoke_test("NOTICE", "notice")

    @pytest.mark.timeout(60)
    def test_writes_warning_entry_to_cloud_logging(self):
        """Test writes WARNING entry to Cloud Logging."""
        self.smoke_test("WARNING", "warning")

    @pytest.mark.timeout(60)
    def test_writes_error_entry_to_cloud_logging(self):
        """Test writes ERROR entry to Cloud Logging."""
        self.smoke_test("ERROR", "error")

    @pytest.mark.timeout(60)
    def test_writes_critical_entry_to_cloud_logging(self):
        """Test writes CRITICAL entry to Cloud Logging."""
        self.smoke_test("CRITICAL", "critical")

    @pytest.mark.timeout(60)
    def test_writes_alert_entry_to_cloud_logging(self):
        """Test writes ALERT entry to Cloud Logging."""
        self.smoke_test("ALERT", "alert")

    @pytest.mark.timeout(60)
    def test_writes_emergency_entry_to_cloud_logging(self):
        """Test writes EMERGENCY entry to Cloud Logging."""
        self.smoke_test("EMERGENCY", "emergency")

    @pytest.mark.timeout(60)
    def test_sends_string_plus_payload_as_json_payload(self):
        """Test sends string + payload as jsonPayload with merged fields."""
        # Reload module
        if "logger" in sys.modules:
            del sys.modules["logger"]
        if "src.logger" in sys.modules:
            del sys.modules["src.logger"]
        if "src" in sys.modules:
            del sys.modules["src"]
        
        # Add src to path if not already there
        import os
        src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        import logger
        importlib.reload(logger)
        
        log = logger.logger()
        test_id = f"it-json-{int(time.time() * 1000)}"
        message = f"json payload smoke [{test_id}]"
        log.info(message, {"requestId": "req-001", "userId": "usr-42"})
        
        entry = poll_for_entry(test_id, "INFO")
        assert entry is not None, "no INFO entry arrived within timeout"
        assert isinstance(entry["data"], dict)
        data = entry["data"]
        assert data.get("message") == message
        assert data.get("requestId") == "req-001"
        assert data.get("userId") == "usr-42"


class TestGcpBackendIntegrationLabels:
    """Integration tests for GCP backend label handling."""

    saved_env: Dict[str, Optional[str]]

    @classmethod
    def setup_class(cls):
        """Save and set up environment for GCP tests."""
        cls.saved_env = {}
        for k in ["GCP_PROJECT", "LOGGER_NAME", "LOGGER_TARGET", "ENVIRONMENT", "SERVICE", "VERSION"]:
            cls.saved_env[k] = os.environ.get(k)
        os.environ["GCP_PROJECT"] = PROJECT
        os.environ["LOGGER_NAME"] = LOG_NAME
        os.environ["LOGGER_TARGET"] = "gcp"

    @classmethod
    def teardown_class(cls):
        """Restore original environment."""
        for k, v in cls.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def setup_method(self):
        """Clean up label environment variables."""
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("SERVICE", None)
        os.environ.pop("VERSION", None)

    def label_test(self, env_overrides: Dict[str, str], expected_labels: Dict[str, str]):
        """Run a label test with environment overrides."""
        for k, v in env_overrides.items():
            os.environ[k] = v

        # Reload module
        if "logger" in sys.modules:
            del sys.modules["logger"]
        if "src.logger" in sys.modules:
            del sys.modules["src.logger"]
        if "src" in sys.modules:
            del sys.modules["src"]
        
        # Add src to path if not already there
        import os
        src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        import logger
        importlib.reload(logger)
        
        log = logger.logger()
        test_id = f"it-label-{'-'.join(env_overrides.keys())}-{int(time.time() * 1000)}"
        log.info(f"label smoke [{test_id}]")
        
        entry = poll_for_entry(test_id, "INFO")
        assert entry is not None, "no INFO entry arrived within timeout"
        
        labels = entry["metadata"].get("labels", {})
        for k, v in expected_labels.items():
            assert labels.get(k) == v, f'label "{k}" missing or wrong'

        # Cleanup
        for k in env_overrides.keys():
            os.environ.pop(k, None)

    @pytest.mark.timeout(60)
    def test_attaches_environment_label(self):
        """Test attaches environment label."""
        self.label_test({"ENVIRONMENT": "staging"}, {"environment": "staging"})

    @pytest.mark.timeout(60)
    def test_attaches_service_label(self):
        """Test attaches service label."""
        self.label_test({"SERVICE": "my-service"}, {"service": "my-service"})

    @pytest.mark.timeout(60)
    def test_attaches_version_label(self):
        """Test attaches version label."""
        self.label_test({"VERSION": "1.2.3"}, {"version": "1.2.3"})

    @pytest.mark.timeout(60)
    def test_attaches_all_three_labels_together(self):
        """Test attaches all three labels together."""
        self.label_test(
            {"ENVIRONMENT": "production", "SERVICE": "my-service", "VERSION": "1.2.3"},
            {"environment": "production", "service": "my-service", "version": "1.2.3"},
        )

    @pytest.mark.timeout(60)
    def test_attaches_scope_label(self):
        """Test attaches scope label."""
        # Reload module
        if "logger" in sys.modules:
            del sys.modules["logger"]
        if "src.logger" in sys.modules:
            del sys.modules["src.logger"]
        if "src" in sys.modules:
            del sys.modules["src"]
        
        # Add src to path if not already there
        import os
        src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        import logger
        importlib.reload(logger)
        
        log = logger.logger("test-scope")
        test_id = f"it-scope-{int(time.time() * 1000)}"
        log.info(f"scope smoke [{test_id}]")
        
        entry = poll_for_entry(test_id, "INFO")
        assert entry is not None, "no INFO entry arrived within timeout"
        labels = entry["metadata"].get("labels", {})
        assert labels.get("scope") == "test-scope", 'label "scope" missing or wrong'

    @pytest.mark.timeout(60)
    def test_merges_scope_and_per_call_labels(self):
        """Test merges scope and per-call labels."""
        # Reload module
        if "logger" in sys.modules:
            del sys.modules["logger"]
        if "src.logger" in sys.modules:
            del sys.modules["src.logger"]
        if "src" in sys.modules:
            del sys.modules["src"]
        
        # Add src to path if not already there
        import os
        src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        import logger
        importlib.reload(logger)
        
        log = logger.logger("api")
        test_id = f"it-scope-percall-{int(time.time() * 1000)}"
        log.info(f"scope+percall smoke [{test_id}]", None, {"traceId": "t-1"})  # payload=None, labels={"traceId": "t-1"}
        
        entry = poll_for_entry(test_id, "INFO")
        assert entry is not None, "no INFO entry arrived within timeout"
        labels = entry["metadata"].get("labels", {})
        assert labels.get("scope") == "api"
        assert labels.get("traceId") == "t-1"
