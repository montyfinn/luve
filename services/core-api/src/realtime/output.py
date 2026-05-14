from __future__ import annotations

from typing import Protocol

from src.realtime.contracts import AudioChunk, RuntimeEvent


class RuntimeOutput(Protocol):
    async def send_audio(self, chunk: AudioChunk) -> None: ...

    async def send_event(self, event: RuntimeEvent) -> None: ...

    async def send_log(self, message: str) -> None: ...

