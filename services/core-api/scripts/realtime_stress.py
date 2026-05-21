from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import subprocess
import time
import wave
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack
from av import AudioFrame


ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT_DIR.parents[1]
DEFAULT_FIXTURE = ROOT_DIR / "testdata" / "audio" / "user_mic_case_04_clip_story_check.wav"
ARTIFACT_DIR = ROOT_DIR / ".tmp"
EVENT_NAMES = {
    "ten_started",
    "stt_result",
    "stt_result_suppressed",
    "stt_error",
    "assistant_stream",
    "assistant_final",
    "llm_error",
    "assistant_audio_meta",
    "session_ended",
}


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value!r}")


def now_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


async def async_http_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url, headers=headers, json=body)
    try:
        payload = response.json() if response.content else None
    except ValueError:
        payload = {"detail": "HTTP response body was not JSON"}
    return response.status_code, payload


def find_login_json(path_arg: str) -> Path:
    candidates = [
        Path(path_arg),
        ROOT_DIR / path_arg,
        REPO_ROOT / path_arg,
        REPO_ROOT / "login.json",
        ROOT_DIR / "login.json",
    ]
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.exists():
            return resolved
    raise FileNotFoundError("login.json not found; pass --login-json")


def load_login_payload(path_arg: str) -> dict[str, Any]:
    path = find_login_json(path_arg)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("login payload must be a JSON object")
    return payload


async def login(core_url: str, login_payload: dict[str, Any]) -> str:
    status, payload = await async_http_json(
        "POST",
        f"{core_url}/api/v1/auth/login",
        body=login_payload,
        timeout=10,
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if status != 200 or not token:
        raise RuntimeError(f"login failed status={status} token_present={bool(token)}")
    return str(token)


async def create_session(core_url: str, token: str) -> str:
    status, payload = await async_http_json(
        "POST",
        f"{core_url}/api/v1/sessions",
        token=token,
        body={},
        timeout=10,
    )
    session_id = payload.get("id") or payload.get("session_id") if isinstance(payload, dict) else None
    if status not in {200, 201} or not session_id:
        raise RuntimeError(f"session creation failed status={status}")
    return str(session_id)


async def get_health(ten_url: str) -> tuple[int, Any]:
    return await async_http_json("GET", f"{ten_url}/healthz", timeout=5)


async def get_rtc_health(ten_url: str) -> tuple[int, Any]:
    return await async_http_json("GET", f"{ten_url}/rtc/health", timeout=5)


async def send_cmd(
    ten_url: str,
    token: str,
    session_id: str,
    cmd: str,
    *,
    source: str = "stress_harness",
) -> tuple[int, Any]:
    return await async_http_json(
        "POST",
        f"{ten_url}/rtc/cmd",
        token=token,
        body={"session_id": session_id, "cmd": cmd, "source": source},
        timeout=5,
    )


class SyntheticAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.sample_rate = 48000
        self.frame_samples = 960
        self.time_base = Fraction(1, self.sample_rate)
        self.next_pts = 0
        self.started_at: float | None = None
        self.fixture_samples = self._load_fixture() if mode in {"short_english", "long_audio"} else None
        self.fixture_offset = 0
        self.rng = random.Random(20260521)

    def _load_fixture(self) -> np.ndarray | None:
        if not DEFAULT_FIXTURE.exists():
            return None
        with wave.open(str(DEFAULT_FIXTURE), "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16)
        if channels > 1:
            samples = samples[: (samples.size // channels) * channels]
            samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
        if sample_rate != self.sample_rate:
            samples = self._linear_resample(samples, sample_rate, self.sample_rate)
        if self.mode == "short_english":
            samples = samples[: self.sample_rate * 4]
        return samples

    @staticmethod
    def _linear_resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if samples.size == 0 or source_rate == target_rate:
            return samples
        duration = samples.size / float(source_rate)
        target_size = max(int(duration * target_rate), 1)
        x_old = np.linspace(0.0, duration, num=samples.size, endpoint=False)
        x_new = np.linspace(0.0, duration, num=target_size, endpoint=False)
        return np.interp(x_new, x_old, samples).astype(np.int16)

    async def recv(self) -> AudioFrame:
        if self.started_at is None:
            self.started_at = time.perf_counter()
        target_time = self.started_at + self.next_pts / float(self.sample_rate)
        sleep_for = target_time - time.perf_counter()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

        pcm = self._next_pcm()
        frame = AudioFrame(format="s16", layout="mono", samples=pcm.size)
        frame.planes[0].update(pcm.tobytes())
        frame.sample_rate = self.sample_rate
        frame.pts = self.next_pts
        frame.time_base = self.time_base
        self.next_pts += pcm.size
        return frame

    def _next_pcm(self) -> np.ndarray:
        if self.fixture_samples is not None and self.fixture_offset < self.fixture_samples.size:
            chunk = self.fixture_samples[self.fixture_offset : self.fixture_offset + self.frame_samples]
            self.fixture_offset += chunk.size
            if chunk.size < self.frame_samples:
                chunk = np.pad(chunk, (0, self.frame_samples - chunk.size))
            return chunk.astype(np.int16, copy=False)

        if self.mode == "noise":
            return np.array(
                [self.rng.randint(-450, 450) for _ in range(self.frame_samples)],
                dtype=np.int16,
            )
        if self.mode == "long_audio":
            values = [
                int(1200 * math.sin(2 * math.pi * 180 * (self.next_pts + i) / self.sample_rate))
                for i in range(self.frame_samples)
            ]
            return np.array(values, dtype=np.int16)
        return np.zeros(self.frame_samples, dtype=np.int16)


@dataclass
class LoopMetrics:
    loop: int
    session_id: str | None = None
    offer_status: int | None = None
    datachannel_open_ms: float | None = None
    first_stt_ms: float | None = None
    final_stt_ms: float | None = None
    assistant_first_ms: float | None = None
    assistant_final_ms: float | None = None
    first_tts_meta_ms: float | None = None
    suppress_reason: str | None = None
    stt_error: str | None = None
    llm_error: str | None = None
    health_before_active_sessions: int | None = None
    health_during_active_sessions: int | None = None
    health_during_queued_frames: int | None = None
    health_during_connection_state: str | None = None
    health_during_ice_connection_state: str | None = None
    health_during_tasks: int | None = None
    health_after_active_sessions: int | None = None
    health_after_remaining_sessions: int | None = None
    health_after_queued_frames: int | None = None
    events: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def extract_active_sessions(payload: Any) -> int | None:
    return payload.get("active_sessions") if isinstance(payload, dict) else None


def extract_last_close(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    last_close = payload.get("last_close")
    return last_close if isinstance(last_close, dict) else None


def extract_first_session(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return None
    session = sessions[0]
    return session if isinstance(session, dict) else None


def parse_run_ten_cpu(snapshot: dict[str, Any]) -> float | None:
    processes = str(snapshot.get("processes") or "")
    values: list[float] = []
    for line in processes.splitlines():
        if "run_ten.py" not in line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            values.append(float(parts[1]))
        except ValueError:
            continue
    return max(values) if values else None


def process_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    commands = {
        "processes": "ps -o pid,pcpu,pmem,etime,cmd -p $(pgrep -f 'run_ten.py|uvicorn src.main' | paste -sd, -) 2>/dev/null || true",
        "gpu": "timeout 5s nvidia-smi --query-gpu=temperature.gpu,memory.used,utilization.gpu --format=csv,noheader,nounits 2>/dev/null || true",
    }
    for key, command in commands.items():
        try:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=7,
            )
            snapshot[key] = completed.stdout.strip()
        except Exception as exc:
            snapshot[key] = f"unavailable:{type(exc).__name__}"
    return snapshot


async def run_loop(args: argparse.Namespace, token: str, loop_index: int) -> LoopMetrics:
    metrics = LoopMetrics(loop=loop_index)
    started_at = time.perf_counter()
    pc = RTCPeerConnection()
    control = pc.createDataChannel("control")
    opened = asyncio.Event()
    terminal_event = asyncio.Event()

    def record_event(event_name: str, data: dict[str, Any]) -> None:
        metrics.events[event_name] = metrics.events.get(event_name, 0) + 1
        elapsed = now_ms(started_at)
        if event_name == "stt_result":
            metrics.first_stt_ms = metrics.first_stt_ms or elapsed
            if data.get("is_final"):
                metrics.final_stt_ms = metrics.final_stt_ms or elapsed
                if not args.expect_response:
                    terminal_event.set()
        elif event_name == "stt_result_suppressed":
            metrics.suppress_reason = str(data.get("reason") or "")
            terminal_event.set()
        elif event_name == "stt_error":
            metrics.stt_error = str(data.get("reason") or data.get("message") or "")
            terminal_event.set()
        elif event_name == "assistant_stream":
            metrics.assistant_first_ms = metrics.assistant_first_ms or elapsed
        elif event_name == "assistant_final":
            metrics.assistant_final_ms = metrics.assistant_final_ms or elapsed
            if not args.tts_enabled:
                terminal_event.set()
        elif event_name == "llm_error":
            metrics.llm_error = str(data.get("message") or "llm_error")
            terminal_event.set()
        elif event_name == "assistant_audio_meta":
            metrics.first_tts_meta_ms = metrics.first_tts_meta_ms or elapsed
        elif event_name == "session_ended":
            terminal_event.set()

    @control.on("open")
    def _on_open() -> None:
        metrics.datachannel_open_ms = now_ms(started_at)
        opened.set()

    @control.on("message")
    def _on_message(message: Any) -> None:
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")
        if not isinstance(message, str):
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        event_name = str(data.get("event") or "")
        if event_name in EVENT_NAMES:
            record_event(event_name, data)

    try:
        status, health_before = await get_rtc_health(args.ten_url)
        if status != 200:
            raise RuntimeError(f"rtc health before failed status={status}")
        metrics.health_before_active_sessions = extract_active_sessions(health_before)

        metrics.session_id = await create_session(args.core_url, token)
        pc.addTrack(SyntheticAudioTrack(args.mode))
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        body = {
            "type": pc.localDescription.type,
            "sdp": pc.localDescription.sdp,
            "session_id": metrics.session_id,
            "stt_only": args.stt_only,
            "tts_enabled": args.tts_enabled,
        }
        metrics.offer_status, answer_payload = await async_http_json(
            "POST",
            f"{args.ten_url}/rtc/offer",
            token=token,
            body=body,
            timeout=15,
        )
        if metrics.offer_status != 200:
            raise RuntimeError(f"offer failed status={metrics.offer_status}")
        answer = answer_payload.get("answer") if isinstance(answer_payload, dict) else None
        if not isinstance(answer, dict):
            raise RuntimeError("offer response missing answer")
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

        await asyncio.wait_for(opened.wait(), timeout=10)
        status, health_during = await get_rtc_health(args.ten_url)
        if status == 200:
            metrics.health_during_active_sessions = extract_active_sessions(health_during)
            session_health = extract_first_session(health_during)
            if session_health:
                metrics.health_during_queued_frames = session_health.get("queued_frames")
                metrics.health_during_connection_state = session_health.get("connection_state")
                metrics.health_during_ice_connection_state = session_health.get("ice_connection_state")
                metrics.health_during_tasks = session_health.get("tasks")
        if args.mode != "rapid_disconnect":
            await asyncio.sleep(max(args.flush_after_seconds, 0.0))
            control.send(
                json.dumps(
                    {
                        "cmd": "FLUSH",
                        "source": "stress_harness",
                        "suppress_response": False,
                    }
                )
            )
            remaining = max(args.disconnect_after_seconds - args.flush_after_seconds, 0.5)
            with contextlib_suppress_timeout():
                await asyncio.wait_for(terminal_event.wait(), timeout=remaining)
        else:
            await asyncio.sleep(min(args.flush_after_seconds, 0.5))

    except Exception as exc:
        metrics.error = f"{type(exc).__name__}:{exc}"
        if args.fail_fast:
            raise
    finally:
        with contextlib_suppress_all():
            await pc.close()
        await asyncio.sleep(1.0)
        status, health_after = await get_rtc_health(args.ten_url)
        if status == 200:
            metrics.health_after_active_sessions = extract_active_sessions(health_after)
            last_close = extract_last_close(health_after)
            if last_close:
                metrics.health_after_remaining_sessions = last_close.get("remaining_sessions")
                metrics.health_after_queued_frames = last_close.get("queued_frames")

    return metrics


class contextlib_suppress_all:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: Any) -> bool:
        return True


class contextlib_suppress_timeout:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, _exc: Any, _tb: Any) -> bool:
        return exc_type is asyncio.TimeoutError


def print_table(metrics: list[LoopMetrics]) -> None:
    print(
        "loop session offer dc_ms stt_final_ms assistant_final_ms tts_meta_ms "
        "before during after remaining queued suppress stt_error llm_error error"
    )
    for item in metrics:
        print(
            item.loop,
            item.session_id or "-",
            item.offer_status if item.offer_status is not None else "-",
            item.datachannel_open_ms if item.datachannel_open_ms is not None else "-",
            item.final_stt_ms if item.final_stt_ms is not None else "-",
            item.assistant_final_ms if item.assistant_final_ms is not None else "-",
            item.first_tts_meta_ms if item.first_tts_meta_ms is not None else "-",
            item.health_before_active_sessions if item.health_before_active_sessions is not None else "-",
            item.health_during_active_sessions if item.health_during_active_sessions is not None else "-",
            item.health_after_active_sessions if item.health_after_active_sessions is not None else "-",
            item.health_after_remaining_sessions if item.health_after_remaining_sessions is not None else "-",
            item.health_after_queued_frames if item.health_after_queued_frames is not None else "-",
            item.suppress_reason or "-",
            item.stt_error or "-",
            item.llm_error or "-",
            item.error or "-",
        )


def evaluate_failures(metrics: list[LoopMetrics], healthz_ok: bool) -> list[str]:
    failures: list[str] = []
    if not healthz_ok:
        failures.append("healthz failed")
    for item in metrics:
        if item.offer_status != 200:
            failures.append(f"loop {item.loop}: offer failed")
        if item.datachannel_open_ms is None:
            failures.append(f"loop {item.loop}: datachannel did not open")
        if item.health_after_active_sessions != 0:
            failures.append(f"loop {item.loop}: active_sessions did not return to 0")
        if item.health_after_remaining_sessions not in {0, None}:
            failures.append(f"loop {item.loop}: remaining_sessions is not 0")
        if item.health_during_active_sessions not in {1, None}:
            failures.append(f"loop {item.loop}: active_sessions was not 1 during session")
        if item.stt_error:
            failures.append(f"loop {item.loop}: stt_error")
        if item.llm_error:
            failures.append(f"loop {item.loop}: llm_error")
        if item.error:
            failures.append(f"loop {item.loop}: {item.error}")
    return failures


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Stress Core API + TEN WebRTC runtime.")
    parser.add_argument("--core-url", default="http://127.0.0.1:8000")
    parser.add_argument("--ten-url", default="http://127.0.0.1:8080")
    parser.add_argument("--login-json", default="../../login.json")
    parser.add_argument("--loops", type=int, default=5)
    parser.add_argument(
        "--mode",
        choices=["short_english", "silence", "noise", "long_audio", "rapid_disconnect"],
        default="short_english",
    )
    parser.add_argument("--tts-enabled", type=parse_bool, default=True)
    parser.add_argument("--stt-only", type=parse_bool, default=False)
    parser.add_argument("--flush-after-seconds", type=float, default=2.5)
    parser.add_argument("--disconnect-after-seconds", type=float, default=8.0)
    parser.add_argument("--cooldown-seconds", type=float, default=30.0)
    parser.add_argument("--max-idle-cpu", type=float, default=50.0)
    parser.add_argument("--expect-response", type=parse_bool, default=True)
    parser.add_argument("--fail-fast", type=parse_bool, default=True)
    args = parser.parse_args()

    ARTIFACT_DIR.mkdir(exist_ok=True)
    started_wall = time.strftime("%Y%m%d_%H%M%S")
    artifact_path = ARTIFACT_DIR / f"realtime_stress_{started_wall}.json"

    login_payload = load_login_payload(args.login_json)
    token = await login(args.core_url, login_payload)
    print("login_status 200")
    print("token_present True")

    health_status, _health = await get_health(args.ten_url)
    healthz_ok = health_status == 200
    print("healthz_status", health_status)

    snapshots = {
        "before": process_snapshot(),
        "after_each": [],
        "after": None,
        "cooldown_before": None,
        "cooldown_after": None,
    }
    metrics: list[LoopMetrics] = []
    for loop_index in range(1, args.loops + 1):
        item = await run_loop(args, token, loop_index)
        metrics.append(item)
        snapshots["after_each"].append(process_snapshot())
        print_table([item])
        if args.fail_fast and item.error:
            break

    snapshots["after"] = process_snapshot()

    cooldown_before_healthz_status, cooldown_before_healthz = await get_health(args.ten_url)
    cooldown_before_rtc_status, cooldown_before_rtc = await get_rtc_health(args.ten_url)
    snapshots["cooldown_before"] = {
        "healthz_status": cooldown_before_healthz_status,
        "healthz": cooldown_before_healthz,
        "rtc_health_status": cooldown_before_rtc_status,
        "rtc_health": cooldown_before_rtc,
        "process": process_snapshot(),
    }

    if args.cooldown_seconds > 0:
        await asyncio.sleep(args.cooldown_seconds)

    cooldown_after_healthz_status, cooldown_after_healthz = await get_health(args.ten_url)
    cooldown_after_rtc_status, cooldown_after_rtc = await get_rtc_health(args.ten_url)
    snapshots["cooldown_after"] = {
        "healthz_status": cooldown_after_healthz_status,
        "healthz": cooldown_after_healthz,
        "rtc_health_status": cooldown_after_rtc_status,
        "rtc_health": cooldown_after_rtc,
        "process": process_snapshot(),
    }

    failures = evaluate_failures(metrics, healthz_ok)
    cooldown_after_cpu = parse_run_ten_cpu(snapshots["cooldown_after"]["process"])
    cooldown_after_active_sessions = (
        extract_active_sessions(cooldown_after_rtc)
        if cooldown_after_rtc_status == 200
        else None
    )
    if cooldown_after_healthz_status != 200:
        failures.append(f"healthz failed after cooldown status={cooldown_after_healthz_status}")
    if cooldown_after_active_sessions != 0:
        failures.append(
            "active_sessions did not return to 0 after cooldown "
            f"active_sessions={cooldown_after_active_sessions}"
        )
    if cooldown_after_cpu is not None and cooldown_after_cpu >= args.max_idle_cpu:
        failures.append(
            "run_ten.py CPU remained high after cooldown "
            f"cpu={cooldown_after_cpu:.1f} max_idle_cpu={args.max_idle_cpu:.1f}"
        )

    print_table(metrics)
    print(
        "cooldown_summary",
        json.dumps(
            {
                "healthz_after_cooldown": cooldown_after_healthz_status,
                "active_sessions_after_cooldown": cooldown_after_active_sessions,
                "run_ten_cpu_after_cooldown": cooldown_after_cpu,
            },
            ensure_ascii=False,
        ),
    )
    print("summary", json.dumps({"loops": len(metrics), "failures": failures}, ensure_ascii=False))

    artifact = {
        "args": {
            key: value
            for key, value in vars(args).items()
            if key != "login_json"
        },
        "metrics": [asdict(item) for item in metrics],
        "snapshots": snapshots,
        "failures": failures,
    }
    artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print("artifact_path", artifact_path)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
