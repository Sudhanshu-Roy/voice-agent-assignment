"""
Integration tests for FastAPI phone collection endpoints.
Tests /health, POST /api/phone, GET /api/phone, GET /api/phone/stats,
and DELETE /api/phone/{id}.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.database import Base, get_db

# Create an in-memory SQLite database specifically for isolated API tests
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


client = TestClient(app)


class TestPhoneAPI:
    """Test suite for backend endpoints."""

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_create_valid_phone_record_english(self):
        payload = {
            "rawTranscript": "nine eight seven six five four three two one zero",
            "parsedNumber": "9876543210",
            "language": "en"
        }
        response = client.post("/api/phone", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Phone number saved successfully"
        assert data["data"]["parsedNumber"] == "9876543210"
        assert data["data"]["language"] == "en"
        assert "id" in data["data"]
        assert "collectedAt" in data["data"]

    def test_create_valid_phone_record_hindi(self):
        payload = {
            "rawTranscript": "nau aath saat chhe paanch chaar teen do ek shunya",
            "parsedNumber": "9876543210",
            "language": "hi"
        }
        response = client.post("/api/phone", json=payload)
        assert response.status_code == 201
        assert response.json()["data"]["language"] == "hi"

    def test_reject_invalid_phone_starting_digit(self):
        payload = {
            "rawTranscript": "five one two three four five six seven eight nine",
            "parsedNumber": "5123456789",  # Starts with 5
            "language": "en"
        }
        response = client.post("/api/phone", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False

    def test_reject_invalid_phone_length(self):
        payload = {
            "rawTranscript": "nine eight seven six five",
            "parsedNumber": "98765",  # 5 digits
            "language": "en"
        }
        response = client.post("/api/phone", json=payload)
        assert response.status_code == 422

    def test_reject_invalid_language(self):
        payload = {
            "rawTranscript": "nine eight seven six five four three two one zero",
            "parsedNumber": "9876543210",
            "language": "fr"  # Not en, hi, or mixed
        }
        response = client.post("/api/phone", json=payload)
        assert response.status_code == 422

    def test_list_phones_and_stats(self):
        # Insert 2 records
        client.post("/api/phone", json={
            "rawTranscript": "9876543210",
            "parsedNumber": "9876543210",
            "language": "en"
        })
        client.post("/api/phone", json={
            "rawTranscript": "nau aath saat 876543210",
            "parsedNumber": "9876543210",
            "language": "hi"
        })

        # Test list
        res = client.get("/api/phone")
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["total"] == 2
        assert len(body["data"]) == 2

        # Test filter by language
        res_hi = client.get("/api/phone?language=hi")
        assert res_hi.status_code == 200
        assert res_hi.json()["total"] == 1
        assert res_hi.json()["data"][0]["language"] == "hi"

        # Test search
        res_search = client.get("/api/phone?search=98765")
        assert res_search.json()["total"] == 2

        # Test stats
        res_stats = client.get("/api/phone/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["total"] == 2
        assert stats["english"] == 1
        assert stats["hindi"] == 1
        assert stats["mixed"] == 0

    def test_delete_phone_record(self):
        # Create record
        create_res = client.post("/api/phone", json={
            "rawTranscript": "9876543210",
            "parsedNumber": "9876543210",
            "language": "en"
        })
        record_id = create_res.json()["data"]["id"]

        # Delete record
        del_res = client.delete(f"/api/phone/{record_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # Verify not found after deletion
        del_again = client.delete(f"/api/phone/{record_id}")
        assert del_again.status_code == 404
