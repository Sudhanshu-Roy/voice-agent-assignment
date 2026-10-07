"""Tests for LiveKit browser-call token endpoint."""

import os
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


class TestLiveKitToken:
    def test_token_requires_livekit_env(self):
        with patch.dict(
            os.environ,
            {
                "LIVEKIT_URL": "",
                "LIVEKIT_API_KEY": "",
                "LIVEKIT_API_SECRET": "",
            },
            clear=False,
        ):
            response = client.post("/api/livekit/token")
            assert response.status_code == 503

    def test_token_success(self):
        fake_token = MagicMock()
        fake_token.with_identity.return_value = fake_token
        fake_token.with_name.return_value = fake_token
        fake_token.with_grants.return_value = fake_token
        fake_token.with_room_config.return_value = fake_token
        fake_token.to_jwt.return_value = "fake.jwt.token"

        with patch.dict(
            os.environ,
            {
                "LIVEKIT_URL": "wss://example.livekit.cloud",
                "LIVEKIT_API_KEY": "key",
                "LIVEKIT_API_SECRET": "secret",
                "AGENT_NAME": "vaiu-phone-agent",
            },
            clear=False,
        ):
            with patch("livekit.api.AccessToken", return_value=fake_token):
                response = client.post("/api/livekit/token")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["serverUrl"] == "wss://example.livekit.cloud"
        assert data["token"] == "fake.jwt.token"
        assert data["roomName"].startswith("phone-")
        assert data["agentName"] == "vaiu-phone-agent"
        assert data["participantIdentity"].startswith("caller-")
