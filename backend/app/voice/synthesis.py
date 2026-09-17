"""Cancellable local Piper synthesis and sounddevice playback.

Piper is intentionally loaded only at the real boundary. Unit tests inject a voice and an output object,
while production requires the configured local ONNX model and its adjacent JSON configuration; no runtime
download or hosted speech provider can be selected accidentally.

Piper's synchronous ``next()`` runs in a Python worker thread and cannot be force-killed safely. Cancellation
therefore aborts the output immediately, marks the utterance cancelled, drops a chunk that returns afterward,
and closes the generator at the first safe boundary. This is a deliberate bounded library limitation; it does
not justify a process-per-utterance subsystem.
"""

import asyncio
import inspect
import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.constants.voice import VOICE_OUTPUT_CHANNELS, VOICE_OUTPUT_SAMPLE_RATE_HERTZ
from app.lib.exceptions import AerisError, UpstreamUnavailableError
from app.voice.speech import AuthoredSpeech

logger = logging.getLogger(__name__)


class SpeechSynthesisError(AerisError):
    """The local Piper model could not synthesize one utterance."""

    code = UpstreamUnavailableError.code
    status = UpstreamUnavailableError.status


class SpeechPlaybackError(AerisError):
    """The configured local output device could not play one utterance."""

    code = UpstreamUnavailableError.code
    status = UpstreamUnavailableError.status


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """One ordered mono PCM16 chunk emitted by Piper."""

    samples: bytes
    sample_rate: int = VOICE_OUTPUT_SAMPLE_RATE_HERTZ
    channels: int = VOICE_OUTPUT_CHANNELS
    sample_width: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.samples, bytes):
            raise TypeError("AudioChunk.samples must be PCM bytes")
        if len(self.samples) % 2:
            raise ValueError("PCM16 samples must contain an even number of bytes")
        if self.sample_rate <= 0 or self.channels <= 0 or self.sample_width <= 0:
            raise ValueError("AudioChunk format must be positive")

    @property
    def pcm(self) -> bytes:
        return self.samples

    @property
    def audio_int16_bytes(self) -> bytes:
        """Piper's native field name, retained for adapters that pass chunks onward."""
        return self.samples

    @property
    def sample_channels(self) -> int:
        return self.channels


class PiperSynthesizer:
    """Stream chunks from Piper's local ONNX runtime through an async generator."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        config_path: str | Path | None = None,
        *,
        speaker_id: int | None = None,
        length_scale: float | None = None,
        voice: Any = None,
        settings: Any = None,
    ) -> None:
        self.model_path = Path(model_path) if model_path is not None else None
        self.config_path = Path(config_path) if config_path is not None else None
        self.speaker_id = speaker_id
        self.length_scale = length_scale
        self._voice = voice
        self._settings = settings

    def _load_voice(self) -> Any:
        if self._voice is not None:
            return self._voice
        try:
            configured = self._settings
            if configured is None:
                from app.config import settings as configured

            model_path = self.model_path or configured.voice_synthesis_model_path
            config_path = self.config_path or configured.voice_synthesis_config_path
            speaker_id = configured.voice_synthesis_speaker_id if self.speaker_id is None else self.speaker_id
            length_scale = configured.voice_synthesis_length_scale if self.length_scale is None else self.length_scale
        except Exception as error:  # noqa: BLE001 - config/import failures are actionable synthesis failures
            raise SpeechSynthesisError(
                "Piper voice configuration is unavailable.",
                details={"upstream": "piper", "reason": str(error)},
            ) from error
        if not model_path.is_file() or not config_path.is_file():
            raise SpeechSynthesisError(
                "The configured Piper ONNX model or JSON configuration is missing.",
                details={"upstream": "piper", "modelPath": str(model_path), "configPath": str(config_path)},
            )
        try:
            from piper import PiperVoice

            load_params = inspect.signature(PiperVoice.load).parameters
            kwargs = {"config_path": str(config_path)} if "config_path" in load_params else {}
            self._voice = PiperVoice.load(str(model_path), **kwargs)
            self.speaker_id = speaker_id
            self.length_scale = length_scale
            return self._voice
        except Exception as error:  # noqa: BLE001 - piper load errors belong to this boundary
            raise SpeechSynthesisError(
                "The configured Piper voice could not be loaded.",
                details={"upstream": "piper", "reason": str(error)},
            ) from error

    def _piper_kwargs(self, synthesize: Any) -> dict[str, Any]:
        parameters = inspect.signature(synthesize).parameters
        kwargs: dict[str, Any] = {}
        if "syn_config" in parameters:
            try:
                from piper.config import SynthesisConfig

                config_params = inspect.signature(SynthesisConfig).parameters
                values = {
                    "speaker_id": self.speaker_id,
                    "length_scale": self.length_scale,
                }
                kwargs["syn_config"] = SynthesisConfig(**{key: value for key, value in values.items() if key in config_params and value is not None})
            except (ImportError, TypeError, ValueError):
                # Piper's minor releases expose the config class from different import locations. Its defaults
                # remain valid when an injected runtime does not expose the optional constructor.
                kwargs = {"syn_config": None}
        elif "speaker_id" in parameters or "length_scale" in parameters:
            if "speaker_id" in parameters and self.speaker_id is not None:
                kwargs["speaker_id"] = self.speaker_id
            if "length_scale" in parameters and self.length_scale is not None:
                kwargs["length_scale"] = self.length_scale
        elif any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
            kwargs = {"speaker_id": self.speaker_id, "length_scale": self.length_scale}
        return {key: value for key, value in kwargs.items() if value is not None}

    def _synthesise_iter_blocking(self, text: str, stop: threading.Event) -> Iterable[AudioChunk]:
        voice = self._load_voice()
        synthesize = getattr(voice, "synthesize", None)
        if synthesize is None:
            raise SpeechSynthesisError("The Piper voice does not expose a synthesize method.", details={"upstream": "piper"})
        try:
            generated: Iterable[Any] = synthesize(text, **self._piper_kwargs(synthesize))
            for item in generated:
                if stop.is_set():
                    return
                if isinstance(item, AudioChunk):
                    self._validate_piper_format(item)
                    yield item
                    continue
                yield self._audio_chunk(item)
        except SpeechSynthesisError:
            raise
        except Exception as error:  # noqa: BLE001 - one typed failure at the synthesis boundary
            raise SpeechSynthesisError(
                "Piper failed while synthesizing an utterance.",
                details={"upstream": "piper", "reason": str(error)},
            ) from error

    def _synthesise_blocking(self, text: str) -> list[AudioChunk]:
        """Materialize the stream for callers that explicitly need all audio at once."""
        return list(self._synthesise_iter_blocking(text, threading.Event()))

    def _generator_blocking(self, text: str) -> Iterable[Any]:
        voice = self._load_voice()
        synthesize = getattr(voice, "synthesize", None)
        if synthesize is None:
            raise SpeechSynthesisError("The Piper voice does not expose a synthesize method.", details={"upstream": "piper"})
        return synthesize(text, **self._piper_kwargs(synthesize))

    @staticmethod
    def _next_blocking(generator: Iterable[Any], stop: threading.Event) -> tuple[bool, Any]:
        try:
            return True, next(generator)
        except StopIteration:
            return False, None
        finally:
            # If cancellation arrived while Piper was in its non-killable next() call, close on that same
            # worker thread as soon as the call returns. Closing a live generator from the event loop races it.
            if stop.is_set():
                close = getattr(generator, "close", None)
                if close is not None:
                    close()

    @staticmethod
    def _close_blocking(generator: Iterable[Any]) -> None:
        close = getattr(generator, "close", None)
        if close is not None:
            close()

    @staticmethod
    def _observe_next_task(task: asyncio.Future[tuple[bool, Any]]) -> None:
        """Retrieve a detached worker exception after cancellation.

        ``chunks`` waits for Piper's worker task without propagating cancellation into it, so a cancellation
        can close the generator on the worker thread that owns it.  Once detached, asyncio will otherwise
        report a delayed ``next()`` failure as an unhandled task exception.  The worker's ``finally`` already
        closes the generator, so observing this task is the only event-loop callback needed here.
        """
        try:
            task.result()
        except asyncio.CancelledError:
            # A task cancelled before its worker starts has no exception to surface.
            return
        except Exception:
            # The synthesis boundary has already ended; the active speak task owns any user-facing error.
            logger.debug("Detached Piper next() task failed after utterance cancellation.", exc_info=True)

    @staticmethod
    def _audio_chunk(item: Any) -> AudioChunk:
        if isinstance(item, bytes):
            return AudioChunk(item)
        samples = getattr(item, "audio_int16_bytes", getattr(item, "audio_bytes", None))
        if samples is None and hasattr(item, "tobytes"):
            samples = item.tobytes()
        rate = int(getattr(item, "sample_rate", VOICE_OUTPUT_SAMPLE_RATE_HERTZ))
        channels = int(getattr(item, "sample_channels", getattr(item, "channels", getattr(item, "channel_count", VOICE_OUTPUT_CHANNELS))))
        sample_width = int(getattr(item, "sample_width", 2))
        if not isinstance(samples, bytes):
            raise TypeError("Piper yielded a non-byte audio chunk")
        chunk = AudioChunk(samples, rate, channels, sample_width)
        PiperSynthesizer._validate_piper_format(chunk)
        return chunk

    @staticmethod
    def _validate_piper_format(chunk: AudioChunk) -> None:
        if chunk.sample_rate != VOICE_OUTPUT_SAMPLE_RATE_HERTZ or chunk.channels != VOICE_OUTPUT_CHANNELS or chunk.sample_width != 2:
            raise SpeechSynthesisError(
                "Piper emitted audio outside the configured mono PCM16 format.",
                details={
                    "upstream": "piper",
                    "sampleRate": chunk.sample_rate,
                    "sampleChannels": chunk.channels,
                    "sampleWidth": chunk.sample_width,
                },
            )

    async def chunks(self, utterance: AuthoredSpeech | str) -> AsyncIterator[AudioChunk]:
        """Generate all model chunks off the event loop, yielding them in Piper order."""
        text = utterance.text if isinstance(utterance, AuthoredSpeech) else str(utterance).strip()
        if not text:
            raise SpeechSynthesisError("Cannot synthesize empty speech.", details={"upstream": "piper"})
        stop = threading.Event()
        generator: Iterable[Any] | None = None
        next_task: asyncio.Task[tuple[bool, Any]] | None = None
        try:
            generator = await asyncio.to_thread(self._generator_blocking, text)
            while not stop.is_set():
                next_task = asyncio.create_task(asyncio.to_thread(self._next_blocking, generator, stop))
                # Register immediately so a detached worker exception is observed before the task is retired.
                next_task.add_done_callback(self._observe_next_task)
                done, _ = await asyncio.wait((next_task,), return_when=asyncio.FIRST_COMPLETED)
                has_value, item = next(iter(done)).result()
                next_task = None
                if not has_value or stop.is_set():
                    return
                yield self._audio_chunk(item)
        except SpeechSynthesisError:
            raise
        except Exception as error:  # noqa: BLE001 - one typed failure at the synthesis boundary
            raise SpeechSynthesisError(
                "Piper failed while synthesizing an utterance.",
                details={"upstream": "piper", "reason": str(error)},
            ) from error
        finally:
            stop.set()
            if generator is not None:
                if next_task is None or next_task.done():
                    await asyncio.to_thread(self._close_blocking, generator)
                # A pending worker owns the live generator; its finally closes it safely when next() returns.


# The plan called this interface Kokoro before the accepted Piper ruling. Keep the name import-compatible
# for downstream adapters while making the actual runtime unambiguously Piper.
KokoroSynthesizer = PiperSynthesizer


class SpeechPlayer:
    """Play one utterance at a time from a recreatable ``output_factory``.

    A stream instance is deliberately not accepted: PortAudio streams become one-shot after abort, so a
    factory is required to make every interruption recoverable.
    """

    def __init__(
        self,
        *,
        output_factory: Callable[[], Any],
        sample_rate: int = VOICE_OUTPUT_SAMPLE_RATE_HERTZ,
        channels: int = VOICE_OUTPUT_CHANNELS,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self._output: Any = None
        self._output_factory = output_factory
        self._active: AuthoredSpeech | None = None
        self._interrupt_requested = False
        self._standby = False
        self._lock = asyncio.Lock()
        self._output_ready: asyncio.Event | None = None
        self._write_task: asyncio.Task[None] | None = None
        self._player_closed = False
        self._retiring_output: Any = None
        self._speak_task: asyncio.Task[Any] | None = None

    def _open_output(self) -> Any:
        if self._player_closed:
            raise SpeechPlaybackError("Voice playback has been closed.", details={"upstream": "sounddevice"})
        if self._output is not None:
            return self._output
        try:
            self._output = self._output_factory()
            start = getattr(self._output, "start", None)
            if start is not None:
                start()
            return self._output
        except Exception as error:  # noqa: BLE001 - device errors are typed at the edge
            raise SpeechPlaybackError(
                "The configured voice output device could not be opened.",
                details={"upstream": "sounddevice", "reason": str(error)},
            ) from error

    async def speak(self, utterance: AuthoredSpeech, chunks: AsyncIterator[AudioChunk]) -> None:
        """Write ordered chunks asynchronously; standby drops new utterances without touching the run."""
        async with self._lock:
            if self._standby:
                return
            if self._player_closed:
                raise SpeechPlaybackError("Voice playback has been closed.", details={"upstream": "sounddevice"})
            self._speak_task = asyncio.current_task()
            self._active = utterance
            self._interrupt_requested = False
            self._output_ready = asyncio.Event()
            iterator = chunks.__aiter__()
            output: Any = None
            failed = False
            try:
                try:
                    output = await asyncio.to_thread(self._open_output)
                finally:
                    self._output_ready.set()
                async for chunk in iterator:
                    if self._interrupt_requested and (utterance.interruptible or self._player_closed):
                        break
                    if chunk.sample_rate != self.sample_rate or chunk.channels != self.channels:
                        raise SpeechPlaybackError(
                            "Piper audio format does not match the configured output device.",
                            details={"upstream": "sounddevice", "sampleRate": chunk.sample_rate, "channels": chunk.channels},
                        )
                    if chunk.sample_width != 2:
                        raise SpeechPlaybackError(
                            "Voice audio is not 16-bit PCM.",
                            details={"upstream": "sounddevice", "sampleWidth": chunk.sample_width},
                        )
                    self._write_task = asyncio.create_task(asyncio.to_thread(output.write, chunk.samples))
                    try:
                        await self._write_task
                    except Exception as error:  # noqa: BLE001 - output failures are typed per utterance
                        raise SpeechPlaybackError(
                            "The speaker output device failed while playing an utterance.",
                            details={"upstream": "sounddevice", "reason": str(error)},
                        ) from error
                    finally:
                        self._write_task = None
            except BaseException:
                failed = True
                raise
            finally:
                try:
                    close_iterator = getattr(iterator, "aclose", None)
                    if close_iterator is not None:
                        await close_iterator()
                finally:
                    if self._interrupt_requested or failed:
                        await self._retire_output(output or self._output)
                    self._active = None
                    self._interrupt_requested = False
                    self._output_ready = None
                    self._write_task = None
                    self._speak_task = None

    async def interrupt(self, utterance_id: str | None = None) -> None:
        """Request cancellation of the active interruptible utterance only."""
        active = self._active
        if active is None or (utterance_id is not None and active.utterance_id != utterance_id) or not active.interruptible:
            return
        self._interrupt_requested = True
        ready = self._output_ready
        if ready is not None and self._output is None:
            await ready.wait()
            if self._active is not active:
                return
        output = self._output
        abort = getattr(output, "abort", None)
        if abort is not None:
            await asyncio.to_thread(abort)
        write_task = self._write_task
        if write_task is not None and not write_task.done():
            try:
                await asyncio.shield(write_task)
            except Exception:
                # ``speak`` owns the typed playback failure; interrupt must still complete the safe abort order.
                pass
        # ``speak`` closes its async chunk source, then retires this exact output before releasing the lock.

    async def _retire_output(self, output: Any) -> None:
        """Close one exact output stream and make its reopen policy explicit."""
        if output is None or self._output is not output or self._retiring_output is output:
            return
        self._retiring_output = output
        try:
            close = getattr(output, "close", None)
            if close is not None:
                try:
                    await asyncio.to_thread(close)
                except Exception as error:  # noqa: BLE001 - retirement is still a typed playback boundary
                    raise SpeechPlaybackError(
                        "The voice output device failed while closing.",
                        details={"upstream": "sounddevice", "reason": str(error)},
                    ) from error
            self._output = None
        finally:
            # A failed close must never leave a broken stream eligible for the next utterance.
            if self._output is output:
                self._output = None
            self._retiring_output = None

    async def standby(self) -> None:
        """Suppress future speech and interrupt the current interruptible utterance."""
        self._standby = True
        await self.interrupt()

    async def resume(self) -> None:
        """Release standby suppression; the next explicitly submitted utterance may play."""
        self._standby = False

    async def close(self) -> None:
        """Close an opened sounddevice stream without affecting scientific run state."""
        self._player_closed = True
        active = self._active
        if active is not None:
            if active.interruptible:
                await self.interrupt(active.utterance_id)
            else:
                # Shutdown is a terminal lifecycle boundary, not operator barge-in; it may stop even a
                # refusal that is intentionally non-interruptible during normal session operation.
                self._interrupt_requested = True
                output = self._output
                abort = getattr(output, "abort", None)
                if abort is not None:
                    await asyncio.to_thread(abort)
                if self._write_task is not None and not self._write_task.done():
                    try:
                        await asyncio.shield(self._write_task)
                    except Exception:
                        pass
            speak_task = self._speak_task
            if speak_task is not None and speak_task is not asyncio.current_task():
                try:
                    await asyncio.shield(speak_task)
                except Exception:
                    pass
        await self._retire_output(self._output)
