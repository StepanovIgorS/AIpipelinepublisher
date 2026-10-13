import pytest
from worker.models import ArticleContext, VideoContext
from worker.utils import get_context_from_dict


def test_context_from_dict_returns_videocontext():
    data = {
        "context_type": "video",
        "uuid": "test-123",
        "user_id": 1,
        "title": "Test Title",
        "description": "Test Description",
        "platform": "test-platform",
        "platform_id": "test-platform-id",
        "audio_path": "test-audio.mp3",
        "transcription_path": "test-transcription.txt",
    }
    context = get_context_from_dict(data)
    assert isinstance(context, VideoContext)
    assert context == VideoContext(**data)


def test_context_from_dict_returns_articlecontext():
    data = {
        "context_type": "article",
        "uuid": "test-123",
        "user_id": 1,
        "title": "Test Title",
        "description": "Test Description",
        "platform": "test-platform",
        "platform_id": "test-platform-id",
        "article_path": "test-article.txt",
    }
    context = get_context_from_dict(data)
    assert isinstance(context, ArticleContext)
    assert context == ArticleContext(**data)


def test_context_from_dict_raises_value_error():
    data = {
        "context_type": "unknown",
    }
    with pytest.raises(ValueError):
        get_context_from_dict(data)


def test_context_from_dict_raises_type_error():
    data = {
        "context_type": "video",
        "user_id": 1,
        "title": "Test Title",
        "description": "Test Description",
        "platform": "test-platform",
        "platform_id": "test-platform-id",
        "audio_path": "test-audio.mp3",
        "transcription_path": "test-transcription.txt",
    }
    with pytest.raises(TypeError):
        get_context_from_dict(data)
