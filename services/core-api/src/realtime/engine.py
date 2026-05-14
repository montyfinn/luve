from __future__ import annotations

from typing import Protocol

from src.realtime.contracts import AudioChunk, RuntimeCommand


class RealtimeConversationEngine(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def handle_audio(self, chunk: AudioChunk) -> None: ...

    async def handle_command(self, command: RuntimeCommand) -> None: ...
