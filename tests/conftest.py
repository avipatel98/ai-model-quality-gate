import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make src/ importable without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.app import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Single TestClient reused across all tests in the session."""
    with TestClient(app) as c:
        yield c
