from dataclasses import dataclass


@dataclass
class Context:
    context_type: str
    uuid: str
    user_id: int
    title: str
    description: str | None
    platform: str
    platform_id: str


@dataclass
class VideoContext(Context):
    audio_path: str
    transcription_path: str | None = None

    @property
    def has_transcription(self):
        return self.transcription_path is not None


@dataclass
class ArticleContext(Context):
    article_path: str


@dataclass
class VideoCache:
    platform_id: str
    title: str
    description: str
    transcription: str
