import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from main import app, get_db, init_db

@pytest.fixture(scope="module")
def test_db():
    # Create a temporary file for the test database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    init_db(db_path)
    yield db_path

    # Clean up the test database file
    os.unlink(db_path)

@pytest.fixture(scope="module")
def client(test_db):
    # Override dependency to use the test database within the app context.
    app.dependency_overrides[get_db] = lambda: get_db(test_db)
    os.environ['env'] = 'dev'
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def db(test_db):
    # Provide a fresh database connection for each test function.
    db = get_db(test_db)
    yield db
    db.close()

def test_create_link(db, client):
    response = client.post("/links", json={
        "original_url": "https://www.example.com/",
        "short_code": "abc123"
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Short link created successfully"}

    cursor = db.cursor()
    cursor.execute("SELECT * FROM links WHERE short_code = 'abc123'")
    link = cursor.fetchone()
    assert link is not None, "Link should be present in the database."
    assert link["original_url"] == "https://www.example.com/"
    assert link["short_code"] == "abc123"

def test_get_links(db, client):
    response = client.get("/links")
    assert response.status_code == 200
    links = response.json()["links"]
    assert len(links) == 1, "Should return exactly one link."
    link = links[0]
    assert "id" in link and "original_url" in link and "short_code" in link

def test_redirect_link(db, client):
    # Attempt to redirect
    response = client.get("/abc123", follow_redirects=False)
    assert response.status_code == 307, "Should get a redirect response"
    assert response.headers["location"] == "https://www.example.com/", "Redirect location should match"

    cursor = db.cursor()
    cursor.execute("SELECT * FROM click_tracking WHERE link_id = (SELECT id FROM links WHERE short_code = 'abc123')")
    click_tracking = cursor.fetchone()
    assert click_tracking is not None

def test_redirect_invalid_link(client):
    response = client.get("/invalid")
    assert response.status_code == 404
    assert response.json() == {"detail": "Short link not found or expired"}

def test_add_link_tag(db, client):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM links WHERE short_code = 'abc123'")
    link_id = cursor.fetchone()["id"]

    response = client.post(f"/links/{link_id}/tags", json={
        "tag": "test-tag"
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Tag added to the short link successfully"}

    cursor.execute("SELECT * FROM link_tags WHERE link_id = ? AND tag = 'test-tag'", (link_id,))
    link_tag = cursor.fetchone()
    assert link_tag is not None, "Tag should be associated with the link."

def test_get_link_tags(db, client):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM links WHERE short_code = 'abc123'")
    link_id = cursor.fetchone()["id"]

    response = client.get(f"/links/{link_id}/tags")
    assert response.status_code == 200
    tags = response.json()["tags"]
    assert "test-tag" in tags, "Tag should be retrievable for the link."

def test_inactive_link(db, client):
    # Test accessing an inactive link
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO links (original_url, short_code, is_active)
        VALUES (?, ?, FALSE)
    """, ("https://www.example.com", "inactive123"))
    db.commit()

    response = client.get("/inactive123")
    assert response.status_code == 404
    assert response.json() == {"detail": "Short link not found or expired"}

def test_input_validation(db, client):
    # Test the application's response to invalid input
    response = client.post("/links", json={
        "original_url": "not_a_url",
        "short_code": ""
    })
    assert response.status_code == 422  # Assuming your API uses typical HTTP status codes for input validation

def test_case_sensitivity(db, client):
    # Test the case sensitivity of short codes
    response = client.post("/links", json={
        "original_url": "https://www.example.com",
        "short_code": "Case123"
    })
    db.commit()
    response_lower = client.get("/case123")
    response_upper = client.get("/CASE123")
    assert response_lower.status_code == 404
    assert response_upper.status_code == 404
    assert response_lower.status_code == response_upper.status_code == 404  # or 404 if case-sensitive
