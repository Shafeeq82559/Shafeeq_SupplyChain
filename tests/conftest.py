import os
import tempfile

# Tests run fully offline and deterministic: rule/template fallbacks instead of LLM calls,
# and feedback goes to a throwaway database.
os.environ["LLM_ENABLED"] = "false"
os.environ["FEEDBACK_DB"] = os.path.join(tempfile.mkdtemp(), "test_feedback.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def profile():
    return {"disruption_type": "Natural Disaster", "industry": "Electronics", "supplier_tier": 1,
            "supplier_region": "Asia-Pacific", "supplier_size": "Medium", "has_backup_supplier": False,
            "disruption_severity": 4}
