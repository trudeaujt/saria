from fastapi.testclient import TestClient
from main import app, get_db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "postgresql://user:password@localhost/test_url_shortener"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_shorten_url():
    response = client.post("/shorten", params={"long_url": "https://www.example.com"})
    assert response.status_code == 200
    assert "short_url" in response.json()
    assert "long_url" in response.json()
    assert response.json()["long_url"] == "https://www.example.com"

def test_redirect_url():
    response = client.post("/shorten", params={"long_url": "https://www.example.com"})
    short_url = response.json()["short_url"]
    response = client.get(f"/{short_url}")
    assert response.status_code == 200
    assert response.json()["redirect_url"] == "https://www.example.com"

def test_invalid_short_url():
    response = client.get("/invalid")
    assert response.status_code == 404
    assert response.json()["detail"] == "URL not found"

def test_health_check():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_readiness_check():
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
