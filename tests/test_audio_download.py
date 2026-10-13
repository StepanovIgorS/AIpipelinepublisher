from unittest.mock import ANY, call, patch

import pytest
from worker.enums import TaskStatus
from worker.models import VideoContext
from worker.tasks import video
from yt_dlp.utils import DownloadError


def test_download_video_raises_exception_on_free_user():
    with (
        patch("worker.tasks.video.yt_dlp.YoutubeDL") as mock_ydl,
        patch("worker.tasks.video.update_status") as mock_status,
        patch("worker.tasks.video.fail_task") as mock_fail,
    ):
        fake_ydl = mock_ydl.return_value.__enter__.return_value
        fake_ydl.extract_info.return_value = {"duration": 18001}

        with pytest.raises(DownloadError):
            video.download_video.run(
                123, "test-uuid", "https://example.com", "youtube", False
            )
        mock_fail.assert_called_once_with(
            123, "test-uuid", "Invalid link (duration)", ANY
        )
        mock_status.assert_called_once_with("test-uuid", TaskStatus.downloading)
        mock_ydl.assert_called_once()


def test_download_video_raises_exception_on_none_duration():
    with (
        patch("worker.tasks.video.yt_dlp.YoutubeDL") as mock_ydl,
        patch("worker.tasks.video.update_status") as mock_status,
        patch("worker.tasks.video.fail_task") as mock_fail,
    ):
        fake_ydl = mock_ydl.return_value.__enter__.return_value
        fake_ydl.extract_info.return_value = {"duration": None}

        with pytest.raises(DownloadError):
            video.download_video.run(
                123, "test-uuid", "https://example.com", "youtube", False
            )
        mock_fail.assert_called_once_with(123, "test-uuid", "Invalid link (duration)")
        mock_status.assert_called_once_with("test-uuid", TaskStatus.downloading)
        mock_ydl.assert_called_once()
        fake_ydl.extract_info.assert_called_once_with(
            "https://example.com", download=False
        )


def test_download_video_raises_exception_on_extract_info():
    with (
        patch("worker.tasks.video.yt_dlp.YoutubeDL") as mock_ydl,
        patch("worker.tasks.video.update_status") as mock_status,
        patch("worker.tasks.video.fail_task") as mock_fail,
    ):
        fake_ydl = mock_ydl.return_value.__enter__.return_value
        fake_ydl.extract_info.side_effect = DownloadError("test-msg")

        with pytest.raises(DownloadError):
            video.download_video.run(
                123, "test-uuid", "https://example.com", "youtube", False
            )

        mock_fail.assert_called_once_with(123, "test-uuid", "test-msg")
        mock_status.assert_called_once_with("test-uuid", TaskStatus.downloading)
        mock_ydl.assert_called_once()
        fake_ydl.extract_info.assert_called_once_with(
            "https://example.com", download=False
        )


def test_download_video_success(tmp_path):
    with (
        patch("worker.tasks.video.yt_dlp.YoutubeDL") as mock_ydl,
        patch("worker.tasks.video.update_status") as mock_status,
        patch("worker.tasks.video.fail_task") as mock_fail,
        patch("worker.tasks.video.Cache.get_transcription") as mock_get_transcription,
    ):
        fake_ydl = mock_ydl.return_value.__enter__.return_value
        mock_get_transcription.return_value = None
        audio_path = tmp_path / "audio.mp3"
        audio_path.touch()
        fake_ydl.extract_info.side_effect = [
            {
                "id": "video-123",
                "title": "test title",
                "description": "test description",
                "duration": 1200,
            },
            {
                "id": "video-123",
                "title": "test title",
                "description": "test description",
                "requested_downloads": [{"filepath": str(audio_path)}],
            },
        ]
        actual_context = VideoContext(
            **video.download_video.run(
                123, "test-uuid", "https://example.com", "youtube", False
            )
        )
        context = VideoContext(
            context_type="video",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="video-123",
            audio_path=str(audio_path),
            transcription_path=None,
        )
        assert mock_ydl.call_count == 2
        mock_status.assert_called_once_with("test-uuid", TaskStatus.downloading)
        mock_fail.assert_not_called()
        fake_ydl.extract_info.assert_has_calls(
            [
                call("https://example.com", download=False),
                call("https://example.com", download=True),
            ]
        )
        mock_get_transcription.assert_called_once_with("video-123")
        assert actual_context == context
