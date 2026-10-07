from enum import StrEnum


class TaskStatus(StrEnum):
    pending = "pending"
    downloading = "downloading"
    transcribing = "transcribing"
    summarizing = "summarizing"
    error = "error"
