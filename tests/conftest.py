import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import src.storage.database as db_module
from src.storage.models import Base
import src.execution.executor
import src.risk.manager
import src.main
import src.storage.models

@pytest.fixture(autouse=True)
def isolated_test_db(monkeypatch):
    # Use in-memory SQLite for all tests
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Patch the SessionLocal everywhere it's used
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(src.execution.executor, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(src.risk.manager, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(src.main, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(src.main, "engine", engine)
    monkeypatch.setattr(src.storage.models, "Base", Base)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
