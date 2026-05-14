from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


PCM16_MONO_16KHZ_SAMPLE_RATE = 16000
PCM16_MONO_16KHZ_CHANNELS = 1
PCM16_SAMPLE_FORMAT = "s16le"


class OfferRequest(BaseModel):
    type: str = Field(description="SDP type, expected 'offer'")
    sdp: str = Field(description="SDP offer content")
    session_id: str | None = Field(default=None)
    stt_only: bool = Field(default=False)
    tts_enabled: bool = Field(default=True)


class OfferResponse(BaseModel):
    session_id: str
    answer: dict[str, Any]


class IceRequest(BaseModel):
    session_id: str
    candidate: dict[str, Any]


class CmdRequest(BaseModel):
    session_id: str
    cmd: str
    source: str | None = None


class AudioChunk(BaseModel):
    session_id: str | None = None
    sequence_number: int = 0
    pcm16le: bytes
    sample_rate: int = PCM16_MONO_16KHZ_SAMPLE_RATE
    channels: int = PCM16_MONO_16KHZ_CHANNELS
    sample_format: str = PCM16_SAMPLE_FORMAT

    def to_ten_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "sequence_number": self.sequence_number,
            "data": self.pcm16le,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_format": self.sample_format,
        }


class RuntimeCommand(BaseModel):
    session_id: str | None = None
    command: str
    stt_only: bool | None = None
    tts_enabled: bool | None = None
    suppress_response: bool | None = None
    source: str | None = None

    def to_ten_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": self.session_id,
            "command": self.command.strip().upper(),
        }
        for key in ("stt_only", "tts_enabled", "suppress_response", "source"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


class RuntimeEvent(BaseModel):
    event: str
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_wire_payload(self) -> dict[str, Any]:
        body = {"event": self.event, **self.payload}
        if self.session_id is not None:
            body["session_id"] = self.session_id
        return body
