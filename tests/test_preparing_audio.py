import worker.audio as audio


def test_audio_lower_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MAX_AUDIO_SIZE", 4)
    content = b"abc"
    file_path = tmp_path / "test.bin"
    file_path.write_bytes(content)
    with file_path.open("rb") as f:
        prepared = [chunk.read() for chunk in audio.prepare_audio(f)]
    assert len(prepared) == 1
    assert prepared[0] == content

def test_audio_bigger_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MAX_AUDIO_SIZE", 4)
    content = b"abcdefghij"
    file_path = tmp_path / "test.bin"
    file_path.write_bytes(content)
    with file_path.open("rb") as f:
        prepared = [chunk.read() for chunk in audio.prepare_audio(f)]
        refurbished_content = b"".join([i for i in prepared])
    assert len(prepared) == 3
    assert refurbished_content == content
    assert all(len(chunk) <= 4 for chunk in prepared)

def test_audio_equals_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MAX_AUDIO_SIZE", 4)
    content = b"abcd"
    file_path = tmp_path / "test.bin"
    file_path.write_bytes(content)
    with file_path.open("rb") as f:
        prepared = [chunk.read() for chunk in audio.prepare_audio(f)]
    assert len(prepared) == 1
    assert prepared[0] == content