"""pytest configuration and shared fixtures."""
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "network: tests that make real network requests (may be slow or fail offline)"
    )
    config.addinivalue_line(
        "markers", "slow: tests that are expected to take >5s"
    )
