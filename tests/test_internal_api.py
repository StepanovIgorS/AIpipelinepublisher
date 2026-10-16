from unittest.mock import patch, call, ANY

from api.main import app
from api.model import TaskStatus

from fastapi.testclient import TestClient


client = TestClient(app)


def test_download_status_success():
    with patch("api.main.db.execute") as mock_execute:
        response = client.post("/internal/status/1", headers={"X-Internal-Token": "test-internal-token"}, json={"status": TaskStatus.downloading})

        assert response.status_code == 200
        mock_execute.assert_awaited_with(ANY, TaskStatus.downloading, "1")
        assert response.json() == {"status": "ok"}

def test_download_status_raises_401_unauthorized():
    with patch("api.main.db.execute") as mock_execute:
        response = client.post("/internal/status/1", json={"status": TaskStatus.downloading})

        assert response.status_code == 401
        mock_execute.assert_not_awaited()

def test_download_status_success_on_error_msg():
    with patch("api.main.db.execute") as mock_execute:
        response = client.post("/internal/status/1", headers={"X-Internal-Token": "test-internal-token"}, json={"status": TaskStatus.error, "error": "test-error"})

        assert response.status_code == 200
        mock_execute.assert_awaited_once_with(ANY, TaskStatus.error, "test-error", "1")
        assert response.json() == {"status": "ok"}

def test_webhook_status_raises_401_unauthorized():
    with (
        patch("api.main.types.Update.model_validate") as mock_validate,
        patch("api.main.dp.feed_update") as mock_update
    ):
        response = client.post("/webhook", json={None: None})

        assert response.status_code == 401
        mock_validate.assert_not_called()
        mock_update.assert_not_awaited()


def test_complete_success():
    with patch("api.main.db.execute") as mock_execute:
        response = client.post("/internal/complete/1", headers={"X-Internal-Token": "test-internal-token"}, json={"status": TaskStatus.downloading})

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_execute.assert_has_awaits([
            call(ANY, TaskStatus.completed, "1"),
            call(ANY, "1"),
        ])

def test_complete_raises_401_unauthorized():
    with patch("api.main.db.execute") as mock_execute:
        response = client.post("/internal/complete/1", json={"status": TaskStatus.downloading})

        assert response.status_code == 401
        mock_execute.assert_not_awaited()