from __future__ import annotations

import asyncio
import gc
import logging
import subprocess
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel

from src.core.config import settings
from src.media.buffer import AudioBuffer
from src.schemas.ai_logic import STTAnalysis, WordPoint


logger = logging.getLogger(__name__)


class STTProcessingError(RuntimeError):
    """Controlled STT runtime failure that can be surfaced to realtime clients."""


@dataclass(frozen=True)
class RuntimeConfig:
    device: str
    compute_type: str


@dataclass(frozen=True)
class GpuHealth:
    requires_reset: bool
    nvidia_smi_available: bool
    nvidia_smi_error: str
    ctranslate2_cuda_devices: int | None
    torch_cuda_available: bool | None
    torch_cuda_device_count: int | None
    torch_cuda_error: str


class WhisperInference:
    _instance: "WhisperInference | None" = None
    _instance_lock = asyncio.Lock()

    def __init__(
        self,
        *,
        model_size: str = "small.en",
        preferred_device: str = "cuda",
        preferred_compute_type: str = "int8_float16",
        beam_size: int = 3,
    ) -> None:
        if beam_size <= 0:
            raise ValueError("beam_size must be > 0")

        self._model_size = model_size
        self._preferred_device = preferred_device
        self._preferred_compute_type = (
            "int8_float16" if preferred_compute_type == "float16" else preferred_compute_type
        )
        self._beam_size = beam_size

        self._model: WhisperModel | None = None
        self._runtime_config: RuntimeConfig | None = None

        self._model_lock = asyncio.Lock()
        self._inference_lock = asyncio.Lock()

    @classmethod
    async def get_instance(
        cls,
        *,
        model_size: str = "small.en",
        preferred_device: str = "cuda",
        preferred_compute_type: str = "int8_float16",
        beam_size: int = 3,
    ) -> "WhisperInference":
        async with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(
                    model_size=model_size,
                    preferred_device=preferred_device,
                    preferred_compute_type=preferred_compute_type,
                    beam_size=beam_size,
                )
        return cls._instance

    async def load_model(self) -> None:
        async with self._model_lock:
            if self._model is not None:
                return

            runtime = self._resolve_runtime_config()
            logger.info(
                "stt.model.loading model=%s device=%s compute_type=%s",
                self._model_size,
                runtime.device,
                runtime.compute_type,
            )

            try:
                self._model = await asyncio.to_thread(
                    WhisperModel,
                    self._model_size,
                    device=runtime.device,
                    compute_type=runtime.compute_type,
                )
                self._runtime_config = runtime
            except Exception as exc:
                if runtime.device == "cuda":
                    logger.warning(
                        "stt.model.cuda_failed; falling back to CPU. Error: %s",
                        exc,
                    )
                    # Fallback to CPU
                    self._model = await asyncio.to_thread(
                        WhisperModel,
                        self._model_size,
                        device="cpu",
                        compute_type="int8",
                    )
                    self._runtime_config = RuntimeConfig(device="cpu", compute_type="int8")
                else:
                    raise

    async def unload_model(self) -> None:
        async with self._model_lock:
            if self._model is None:
                return

            self._model = None
            self._runtime_config = None

        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            logger.debug("stt.model.unload torch cleanup skipped", exc_info=True)

    async def transcribe_buffer(
        self,
        audio_buffer: AudioBuffer,
        *,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> STTAnalysis:
        audio_bytes = await audio_buffer.get_flat_audio()
        return await self.transcribe_audio_bytes(
            audio_bytes,
            language=language,
            initial_prompt=initial_prompt,
        )

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        *,
        language: str | None = None,
        initial_prompt: str | None = None,
        beam_size: int | None = None,
        word_timestamps: bool = True,
        vad_filter: bool = True,
        condition_on_previous_text: bool = False,
    ) -> STTAnalysis:
        if not audio_bytes:
            return STTAnalysis(raw_text="", all_words=[])

        await self.load_model()
        audio_array = self._pcm16le_to_float32(audio_bytes)

        async with self._inference_lock:
            try:
                segments = await asyncio.to_thread(
                    self._run_transcription,
                    audio_array,
                    language,
                    initial_prompt,
                    beam_size,
                    word_timestamps,
                    vad_filter,
                    condition_on_previous_text,
                )
            except RuntimeError as exc:
                if not self._is_cuda_runtime_error(exc):
                    raise

                logger.warning(
                    "stt.cuda.failure; retrying on CPU fallback=%s error=%s",
                    settings.stt_enable_cuda_fallback_to_cpu,
                    exc,
                )
                if not settings.stt_enable_cuda_fallback_to_cpu:
                    raise STTProcessingError("stt_cuda_runtime_error") from exc

                try:
                    await self._switch_to_cpu_fallback_model()
                    segments = await asyncio.to_thread(
                        self._run_transcription,
                        audio_array,
                        language,
                        initial_prompt,
                        beam_size,
                        word_timestamps,
                        vad_filter,
                        condition_on_previous_text,
                    )
                except Exception as retry_exc:
                    raise STTProcessingError("stt_cpu_fallback_failed") from retry_exc

        return self._map_segments_to_schema(segments)

    def estimate_vram_usage_mb(self) -> tuple[int, int]:
        if self._runtime_config and self._runtime_config.device != "cuda":
            return (0, 0)
        if self._runtime_config is None and self._preferred_device != "cuda":
            return (0, 0)

        normalized = self._model_size.lower()
        if normalized.startswith("medium"):
            return (2200, 3600)
        if normalized.startswith("small"):
            return (900, 1500)
        if normalized.startswith("base"):
            return (500, 900)
        return (1200, 2800)

    @property
    def runtime(self) -> RuntimeConfig | None:
        return self._runtime_config

    async def _switch_to_cpu_fallback_model(self) -> None:
        async with self._model_lock:
            self._model = None
            self._runtime_config = None

            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                logger.debug("stt.cuda.failure torch cleanup skipped", exc_info=True)

            logger.warning(
                "stt.model.loading_cpu_fallback model=%s device=cpu compute_type=int8",
                self._model_size,
            )
            self._model = await asyncio.to_thread(
                WhisperModel,
                self._model_size,
                device="cpu",
                compute_type="int8",
            )
            self._runtime_config = RuntimeConfig(device="cpu", compute_type="int8")

    @staticmethod
    def _pcm16le_to_float32(audio_bytes: bytes) -> np.ndarray:
        pcm = np.frombuffer(audio_bytes, dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0

    @staticmethod
    def _is_cuda_runtime_error(exc: RuntimeError) -> bool:
        message = str(exc).lower()
        return "cuda failed" in message or "cuda error" in message

    def _run_transcription(
        self,
        audio_array: np.ndarray,
        language: str | None,
        initial_prompt: str | None,
        beam_size: int | None,
        word_timestamps: bool,
        vad_filter: bool,
        condition_on_previous_text: bool,
    ):
        if self._model is None:
            raise RuntimeError("Whisper model is not loaded")
        decode_beam_size = beam_size if beam_size is not None and beam_size > 0 else self._beam_size
        segments, _info = self._model.transcribe(
            audio_array,
            beam_size=decode_beam_size,
            word_timestamps=word_timestamps,
            language="en",          # Ép cứng AI luôn nghe tiếng Anh
            vad_filter=vad_filter,  # Internal VAD is a cleanup pass, not end-of-utterance detection.
            condition_on_previous_text=condition_on_previous_text,
            initial_prompt=initial_prompt,
        )
        return list(segments)

    @staticmethod
    def _map_segments_to_schema(segments: list) -> STTAnalysis:
        raw_text_parts: list[str] = []
        word_points: list[WordPoint] = []
        avg_logprobs: list[float] = []
        no_speech_probs: list[float] = []
        compression_ratios: list[float] = []

        for segment in segments:
            segment_text = (getattr(segment, "text", "") or "").strip()
            if segment_text:
                raw_text_parts.append(segment_text)

            avg_logprob = getattr(segment, "avg_logprob", None)
            if isinstance(avg_logprob, (int, float)):
                avg_logprobs.append(float(avg_logprob))

            no_speech_prob = getattr(segment, "no_speech_prob", None)
            if isinstance(no_speech_prob, (int, float)):
                no_speech_probs.append(float(no_speech_prob))

            compression_ratio = getattr(segment, "compression_ratio", None)
            if isinstance(compression_ratio, (int, float)):
                compression_ratios.append(float(compression_ratio))

            words = getattr(segment, "words", None) or []
            for word in words:
                token = (getattr(word, "word", "") or "").strip()
                if not token:
                    continue

                probability = getattr(word, "probability", 0.0)
                confidence = float(np.clip(probability, 0.0, 1.0))
                start_s = float(getattr(word, "start", 0.0) or 0.0)
                end_s = float(getattr(word, "end", start_s) or start_s)

                word_points.append(
                    WordPoint(
                        word=token,
                        confidence=confidence,
                        start_ms=start_s,
                        end_ms=end_s,
                    )
                )

        return STTAnalysis(
            raw_text=" ".join(raw_text_parts).strip(),
            all_words=word_points,
            avg_logprob=float(np.mean(avg_logprobs)) if avg_logprobs else None,
            no_speech_prob=max(no_speech_probs) if no_speech_probs else None,
            compression_ratio=max(compression_ratios) if compression_ratios else None,
            segment_count=len(segments),
        )

    def _resolve_runtime_config(self) -> RuntimeConfig:
        if self._preferred_device != "cuda":
            return RuntimeConfig(device="cpu", compute_type="int8")

        gpu_health = self._probe_gpu_health()
        logger.info(
            "stt.gpu.health nvidia_smi_available=%s requires_reset=%s "
            "ctranslate2_cuda_devices=%s torch_cuda_available=%s "
            "torch_cuda_device_count=%s nvidia_smi_error=%r torch_cuda_error=%r",
            gpu_health.nvidia_smi_available,
            gpu_health.requires_reset,
            gpu_health.ctranslate2_cuda_devices,
            gpu_health.torch_cuda_available,
            gpu_health.torch_cuda_device_count,
            gpu_health.nvidia_smi_error,
            gpu_health.torch_cuda_error,
        )

        if gpu_health.requires_reset:
            logger.warning(
                "stt.model.cuda_requires_reset; using CPU int8. "
                "Host GPU/driver must be reset before CUDA STT can run."
            )
            return RuntimeConfig(device="cpu", compute_type="int8")

        if gpu_health.ctranslate2_cuda_devices and gpu_health.ctranslate2_cuda_devices > 0:
            return RuntimeConfig(
                device="cuda",
                compute_type=self._preferred_compute_type,
            )

        logger.warning("stt.model.cuda_unavailable; using CPU int8")
        return RuntimeConfig(device="cpu", compute_type="int8")

    @staticmethod
    def _probe_gpu_health() -> GpuHealth:
        nvidia_smi_available = False
        requires_reset = False
        nvidia_smi_error = ""
        ctranslate2_cuda_devices: int | None = None
        torch_cuda_available: bool | None = None
        torch_cuda_device_count: int | None = None
        torch_cuda_error = ""

        try:
            result = subprocess.run(
                ["nvidia-smi", "-q", "-d", "COMPUTE,PERFORMANCE,POWER"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            output = f"{result.stdout}\n{result.stderr}"
            nvidia_smi_available = result.returncode == 0
            requires_reset = "gpu requires reset" in output.lower()
            if result.returncode != 0:
                nvidia_smi_error = output.strip()[:300]
        except FileNotFoundError:
            nvidia_smi_error = "nvidia-smi not found"
        except subprocess.TimeoutExpired:
            nvidia_smi_error = "nvidia-smi timed out"
        except (subprocess.SubprocessError, OSError) as exc:
            nvidia_smi_error = f"{type(exc).__name__}: {exc}"

        try:
            import ctranslate2

            ctranslate2_cuda_devices = ctranslate2.get_cuda_device_count()
        except Exception as exc:
            logger.warning("stt.gpu.ctranslate2_probe_failed", exc_info=True)
            ctranslate2_cuda_devices = None

        try:
            import torch

            torch_cuda_device_count = torch.cuda.device_count()
            torch_cuda_available = torch.cuda.is_available()
        except Exception as exc:
            torch_cuda_error = f"{type(exc).__name__}: {exc}"

        return GpuHealth(
            requires_reset=requires_reset,
            nvidia_smi_available=nvidia_smi_available,
            nvidia_smi_error=nvidia_smi_error,
            ctranslate2_cuda_devices=ctranslate2_cuda_devices,
            torch_cuda_available=torch_cuda_available,
            torch_cuda_device_count=torch_cuda_device_count,
            torch_cuda_error=torch_cuda_error,
        )
