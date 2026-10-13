import math
import os

from collections.abc import Iterator
from io import BytesIO
from typing import BinaryIO


MAX_AUDIO_SIZE = 24 * 1024 * 1024


def prepare_audio(file: BinaryIO) -> Iterator[BinaryIO]:
    size = os.fstat(file.fileno()).st_size
    if size <= MAX_AUDIO_SIZE:
        yield file
        return
    count = math.ceil(size / MAX_AUDIO_SIZE)
    for i in range(count):
        yield BytesIO(file.read(MAX_AUDIO_SIZE))
