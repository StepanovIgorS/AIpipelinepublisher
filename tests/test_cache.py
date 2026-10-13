import pytest
import os
import time

import worker.cache as cache
from worker.models import VideoContext, VideoCache

@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(cache, "ARTICLES_DIR", tmp_path / "articles")
    cache.Cache.init()

    return {"trans_dir": tmp_path / "transcripts", "articles_dir": tmp_path / "articles"}


def test_save_load_cache(tmp_cache_dir):
    cache.Cache.save_transcription(VideoContext(context_type="video", uuid="test-123", user_id=1, title="Test Title", description="Test Description", platform="test-platform", platform_id="test-platform-id", audio_path="test-audio.mp3", transcription_path="test-transcription.txt"), "Test Transcription")
    test_cache = VideoCache(platform_id="test-platform-id", title="Test Title", description="Test Description", transcription="Test Transcription")

    saved_cache = cache.Cache.get_transcription("test-platform-id")
    assert saved_cache is not None
    assert saved_cache == test_cache

def test_cache_miss_returns_none(tmp_cache_dir):
    saved_cache = cache.Cache.get_transcription("test-platform-id")
    assert saved_cache is None


def test_cache_cleanup_removes_expired_file(tmp_cache_dir):
    (tmp_cache_dir["trans_dir"] / "test-transcription.txt").touch()
    file_stat = (tmp_cache_dir["trans_dir"] / "test-transcription.txt").stat()
    current_mtime = file_stat.st_mtime

    target_atime = time.time() - 150
    os.utime(tmp_cache_dir["trans_dir"] / "test-transcription.txt", (target_atime, current_mtime))
    cache.Cache.cleanup_directory(tmp_cache_dir["trans_dir"], 120)
    assert not (tmp_cache_dir["trans_dir"] / "test-transcription.txt").exists()

def test_cache_cleanup_keeps_fresh_file(tmp_cache_dir):
    (tmp_cache_dir["trans_dir"] / "test-transcription.txt").touch()
    file_stat = (tmp_cache_dir["trans_dir"] / "test-transcription.txt").stat()
    current_mtime = file_stat.st_mtime

    target_atime = time.time() - 100
    os.utime(tmp_cache_dir["trans_dir"] / "test-transcription.txt", (target_atime, current_mtime))
    cache.Cache.cleanup_directory(tmp_cache_dir["trans_dir"], 120)
    assert (tmp_cache_dir["trans_dir"] / "test-transcription.txt").exists()

def test_cache_empty_cache(tmp_cache_dir):
    cache.Cache.cleanup_directory(tmp_cache_dir["trans_dir"], 120)