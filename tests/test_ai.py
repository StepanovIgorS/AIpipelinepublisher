import pytest

from dataclasses import asdict
from unittest.mock import patch, ANY, call
from types import SimpleNamespace
from httpx import Request

from openai import APITimeoutError

from worker.tasks import ai
from worker.models import VideoContext, ArticleContext
from worker.enums import TaskStatus


def fake_transcription_create(file, model, timeout):
    text = file.readline().decode("utf-8")
    return SimpleNamespace(text=text)


def fake_summary_create(model, messages):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="test summary result"))])


def test_ai_transcribe_success_without_cache(tmp_path, monkeypatch):
    with (
        patch("worker.tasks.ai.update_status") as mock_status,
        patch("worker.tasks.ai.client.audio.transcriptions.create") as mock_create,
        patch("worker.tasks.ai.Cache.save_transcription") as mock_cache_save
    ):
        monkeypatch.setattr(ai, "TMP_PATH", tmp_path)
        audio_file = tmp_path / "test-audio.mp3"
        audio_file.write_bytes(b"test audio data")
        mock_create.side_effect = fake_transcription_create
        transcription_file = tmp_path / "test-uuid.txt"

        context = VideoContext(
            context_type="video",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="test-platform-id",
            audio_path=str(tmp_path / "test-audio.mp3")
        )

        context_with_transcription = VideoContext(
            context_type="video",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="test-platform-id",
            audio_path=str(tmp_path / "test-audio.mp3"),
            transcription_path=str(tmp_path / "test-uuid.txt")
        )

        actual_context = VideoContext(**ai.ai_transcribe.run(asdict(context)))

        mock_status.assert_called_once_with("test-uuid", TaskStatus.transcribing)
        assert transcription_file.exists()
        assert transcription_file.read_text().strip() == "test audio data"
        mock_create.assert_called_once_with(file=ANY, model=ai.STT_MODEL, timeout=30)
        mock_cache_save.assert_called_once_with(context_with_transcription, transcription_file.read_text())
        assert context_with_transcription == actual_context


def test_ai_transcribe_success_with_cache(tmp_path, monkeypatch):
    with (
        patch("worker.tasks.ai.update_status") as mock_status,
        patch("worker.tasks.ai.client.audio.transcriptions.create") as mock_create,
        patch("worker.tasks.ai.Cache.save_transcription") as mock_cache_save
    ):
        transcription_file = tmp_path / "test-uuid.txt"
        transcription_file.write_text("test transcription")

        context = VideoContext(
            context_type="video",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="test-platform-id",
            audio_path=str(tmp_path / "test-audio.mp3"),
            transcription_path=str(tmp_path / "test-uuid.txt")
        )

        actual_context = VideoContext(**ai.ai_transcribe.run(asdict(context)))

        mock_status.assert_called_once_with("test-uuid", TaskStatus.transcribing)
        mock_create.assert_not_called()
        mock_cache_save.assert_not_called()
        assert actual_context == context


def test_ai_transcribe_raises_timeout_error(tmp_path, monkeypatch):
    with (
        patch("worker.tasks.ai.update_status") as mock_status,
        patch("worker.tasks.ai.client.audio.transcriptions.create") as mock_create,
        patch("worker.tasks.ai.Cache.save_transcription") as mock_cache_save,
        patch("worker.tasks.ai.fail_task") as mock_fail
    ):
        monkeypatch.setattr(ai, "TMP_PATH", tmp_path)
        audio_file = tmp_path / "test-audio.mp3"
        audio_file.write_bytes(b"test audio data")
        mock_create.side_effect = APITimeoutError(Request("", ""))

        context = VideoContext(
            context_type="video",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="test-platform-id",
            audio_path=str(tmp_path / "test-audio.mp3")
        )

        with pytest.raises(APITimeoutError):
            VideoContext(**ai.ai_transcribe.run(asdict(context)))

        mock_status.assert_has_calls([
            call("test-uuid", TaskStatus.transcribing),
            call("test-uuid", TaskStatus.error),
        ])
        mock_create.assert_called_once_with(file=ANY, model=ai.STT_MODEL, timeout=30)
        mock_cache_save.assert_not_called()
        mock_fail.assert_called_once_with(123, "test-uuid", "Transcription timeout", ANY)


def test_ai_summarize_video_success(tmp_path):
    with (
        patch("worker.tasks.ai.update_status") as mock_status,
        patch("worker.tasks.ai.client.chat.completions.create") as mock_create,
        patch("worker.tasks.ai.fail_task") as mock_fail,
        patch("worker.tasks.ai.TelegramNotifier.send_message") as mock_send_message,
        patch("worker.tasks.ai.complete") as mock_complete,
    ):
        transcription_path = tmp_path / "test-uuid.txt"
        transcription_path.write_text("test transcription")
        mock_create.side_effect = fake_summary_create

        context = VideoContext(
            context_type="video",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="test-platform-id",
            audio_path=str(tmp_path / "test-audio.mp3"),
            transcription_path=str(tmp_path / "test-uuid.txt")
        )

        ai.ai_summary.run(asdict(context), "test prompt")

        mock_status.assert_called_once_with("test-uuid", TaskStatus.summarizing)

        actual_messages = mock_create.call_args.kwargs["messages"]

        assert len(actual_messages) == 2
        assert actual_messages[0]["role"] == "system"
        assert actual_messages[0]["content"] == ai.SYSTEM_PROMPT

        assert actual_messages[1]["role"] == "user"
        user_content = actual_messages[1]["content"]

        assert "test prompt" in user_content
        assert "test title" in user_content
        assert "test description" in user_content
        assert "test transcription" in user_content

        mock_send_message.assert_called_once_with(123, "test summary result")
        mock_complete.assert_called_once_with(context)
        mock_fail.assert_not_called()


def test_ai_summarize_article_success(tmp_path):
    with (
        patch("worker.tasks.ai.update_status") as mock_status,
        patch("worker.tasks.ai.client.chat.completions.create") as mock_create,
        patch("worker.tasks.ai.fail_task") as mock_fail,
        patch("worker.tasks.ai.TelegramNotifier.send_message") as mock_send_message,
        patch("worker.tasks.ai.complete") as mock_complete,
    ):
        article = tmp_path / "test-uuid.txt"
        article.write_text("test article text")
        mock_create.side_effect = fake_summary_create

        context = ArticleContext(
            context_type="article",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="test-platform-id",
            article_path=str(tmp_path / "test-uuid.txt"),
        )

        ai.ai_summary.run(asdict(context), "test prompt")

        actual_messages = mock_create.call_args.kwargs["messages"]

        assert len(actual_messages) == 2
        assert actual_messages[0]["role"] == "system"
        assert actual_messages[0]["content"] == ai.SYSTEM_PROMPT

        assert actual_messages[1]["role"] == "user"
        user_content = actual_messages[1]["content"]

        assert "test prompt" in user_content
        assert "test title" in user_content
        assert "test description" in user_content
        assert "test article text" in user_content

        mock_status.assert_called_once_with("test-uuid", TaskStatus.summarizing)
        mock_create.assert_called_once_with(model=ai.TEXT_MODEL, messages=ANY)
        mock_send_message.assert_called_once_with(123, "test summary result")
        mock_complete.assert_called_once_with(context)
        mock_fail.assert_not_called()


def test_ai_summarize_raises_timeout_error(tmp_path):
    with (
        patch("worker.tasks.ai.update_status") as mock_status,
        patch("worker.tasks.ai.client.chat.completions.create") as mock_create,
        patch("worker.tasks.ai.fail_task") as mock_fail,
        patch("worker.tasks.ai.TelegramNotifier.send_message") as mock_send_message,
        patch("worker.tasks.ai.complete") as mock_complete,
        patch("worker.tasks.ai.build_summary_prompt") as mock_build_prompt,
        patch("worker.tasks.ai.cleanup") as mock_cleanup
    ):
        article = tmp_path / "test-uuid.txt"
        article.write_text("test article text")
        mock_create.side_effect = APITimeoutError(Request("", ""))

        context = ArticleContext(
            context_type="article",
            uuid="test-uuid",
            user_id=123,
            title="test title",
            description="test description",
            platform="youtube",
            platform_id="test-platform-id",
            article_path=str(tmp_path / "test-uuid.txt"),
        )

        with pytest.raises(APITimeoutError):
            ai.ai_summary.run(asdict(context), "test prompt")

        mock_build_prompt.assert_called_once_with("test prompt", context, "test article text")
        mock_status.assert_has_calls([
            call("test-uuid", TaskStatus.summarizing),
            call("test-uuid", TaskStatus.error),
        ])
        mock_fail.assert_called_once_with(123, "test-uuid", "Summary timeout", ANY)
        mock_cleanup.assert_called_once_with(context)
        mock_send_message.assert_not_called()
        mock_complete.assert_not_called()
