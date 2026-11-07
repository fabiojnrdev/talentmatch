import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["API_KEYS"] = "tester:secret-a,other:secret-b"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["LLM_MAX_ATTEMPTS"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app import db, models  # noqa: E402,F401
from app.db import Base  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    engine = db.get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture
def session():
    with db.session_scope() as s:
        yield s


AUTH = {"X-API-Key": "secret-a"}
OTHER = {"X-API-Key": "secret-b"}
