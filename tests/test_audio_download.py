from unittest.mock import ANY, call, patch

import pytest
from worker.enums import TaskStatus
from worker.models import VideoCache, VideoContext
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
        assert fake_ydl.extract_info.call_args_list == [
            call("https://example.com", download=False),
            call("https://example.com", download=True),
        ]
        mock_get_transcription.assert_called_once_with("video-123")
        assert actual_context == context


def test_download_video_via_cache_success(tmp_path, monkeypatch):
    with (
        patch("worker.tasks.video.yt_dlp.YoutubeDL") as mock_ydl,
        patch("worker.tasks.video.update_status") as mock_status,
        patch("worker.tasks.video.fail_task") as mock_fail,
        patch("worker.tasks.video.Cache.get_transcription") as mock_get_transcription,
    ):
        monkeypatch.setattr(video, "TMP_DIR", tmp_path)
        fake_ydl = mock_ydl.return_value.__enter__.return_value
        fake_ydl.extract_info.return_value = {
            "id": "video-123",
            "title": "test title",
            "description": "test description",
            "duration": 1200,
        }
        mock_get_transcription.return_value = VideoCache(
            platform_id="video-123",
            title="test title",
            description="test description",
            transcription="test transcription",
        )

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
            audio_path="",
            transcription_path=str(tmp_path / "test-uuid.txt"),
        )
        mock_ydl.assert_called_once()
        fake_ydl.extract_info.assert_called_once_with(
            "https://example.com", download=False
        )
        mock_fail.assert_not_called()
        mock_status.assert_called_once_with("test-uuid", TaskStatus.downloading)
        mock_get_transcription.assert_called_once_with("video-123")
        assert (tmp_path / "test-uuid.txt").read_text() == "test transcription"
        assert context == actual_context
