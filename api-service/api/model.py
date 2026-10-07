from dataclasses import dataclass
from enum import StrEnum

from aiogram.fsm.state import State, StatesGroup
from pydantic import BaseModel


class Settings(StatesGroup):
    platform = State()
    audience = State()
    length = State()
    prompt = State()


class Payments(StatesGroup):
    choosing_subscription = State()
    pending = State()


class Platform(StrEnum):
    VK = "vk"
    TELEGRAM = "telegram"


class Length(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass
class UserSettings:
    platform: Platform
    audience: str
    length: Length
    prompt: str

    def build_summary_prompt(self) -> str:
        return f"""
        <platform>{self.platform}</platform>
        <audience>{self.audience}</audience>
        <length>{self.length}</length>
        <prompt>{self.prompt}</prompt>
        """


class TaskStatus(StrEnum):
    pending = "pending"
    downloading = "downloading"
    transcribing = "transcribing"
    summarizing = "summarizing"
    error = "error"
    completed = "completed"

class UpdateStatusRequest(BaseModel):
    status: TaskStatus
    error: str | None = None
