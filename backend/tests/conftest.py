import os

# Settings must exist before the app is imported. Tests use an in-memory SQLite DB.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"
os.environ["RESEND_API_KEY"] = ""
os.environ["TURNSTILE_SECRET_KEY"] = ""
os.environ["ADMIN_NOTIFY_EMAIL"] = "owner@example.com"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole
from app.security import hash_password

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False)


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sent_emails(monkeypatch):
    """Capture outgoing emails instead of printing them."""
    sent = []

    def fake_send(to, subject, body_html):
        sent.append({"to": to, "subject": subject, "body": body_html})

    monkeypatch.setattr("app.emailer._send", fake_send)
    return sent


@pytest.fixture
def client(sent_emails):
    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(db, email, *, role=UserRole.customer, verified=True, password="password123"):
    user = User(
        name=email.split("@")[0].title(),
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_email_verified=verified,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, email, password="password123"):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
def admin_client(client, db):
    make_user(db, "admin@example.com", role=UserRole.admin)
    login(client, "admin@example.com")
    return client


@pytest.fixture
def customer_client(client, db):
    make_user(db, "ram@example.com")
    login(client, "ram@example.com")
    return client
