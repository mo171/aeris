"""Everything ``aeris voice`` does — an interactive voice loop with hotkey activation.

what  : ``execute_voice()``, the async function behind the Typer command.
where : Called from ``cli/main.py``.
how   : Constructs the voice adapters, binds ``Ctrl+P`` through prompt-toolkit, and runs
        ``VoiceSession.run()`` until the operator exits with ``Ctrl+C``.

        The prompt-toolkit event loop integration keeps the terminal responsive while the
        voice session runs in the background.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from rich.console import Console

from app.config import settings
from app.constants.voice import (
    VOICE_OUTPUT_CHANNELS,
    VOICE_OUTPUT_SAMPLE_RATE_HERTZ,
)

logger = logging.getLogger(__name__)


async def execute_voice(
    *,
    console: Console,
    scene: Path | None = None,
    before: Path | None = None,
    images: list[Path] | None = None,
    sar: list[bool] | None = None,
    level: Any = None,
    gsd: float | None = None,
    registered: bool = False,
    thread: str | None = None,
    request: str | None = None,
) -> None:
    """Run an interactive voice session with hotkey-activated microphone turns."""
    from app.voice.audio import MicrophoneCapture
    from app.voice.session import VoiceSession
    from app.voice.synthesis import PiperSynthesizer, SpeechPlayer
    from app.voice.transcription import WhisperTranscriber

    console.print()
    console.print("  [bold]AERIS Voice Session[/bold]")
    console.print("  Press [bold]Ctrl+P[/bold] to speak, [bold]Ctrl+C[/bold] to exit.")
    console.print()

    # Build the adapters from validated settings
    capture = MicrophoneCapture(
        device=settings.voice_input_device,
    )
    transcriber = WhisperTranscriber()
    synthesizer = PiperSynthesizer()

    def output_factory() -> Any:
        import sounddevice

        return sounddevice.RawOutputStream(
            samplerate=VOICE_OUTPUT_SAMPLE_RATE_HERTZ,
            channels=VOICE_OUTPUT_CHANNELS,
            dtype="int16",
            device=settings.voice_output_device,
        )

    player = SpeechPlayer(output_factory=output_factory)

    # Build the LLM model for turn classification and speech authoring
    model = None
    try:
        from app.lib.llm.chat_model import build_chat_model

        model = build_chat_model()
        if model is None:
            console.print(
                "  [yellow]LLM_PROVIDER=none — voice turn classification and speech authoring "
                "require a language model. Set LLM_PROVIDER and LLM_API_KEY.[/yellow]"
            )
            return
    except Exception as error:
        console.print(f"  [red]Language model unavailable: {error}[/red]")
        console.print(
            "  [yellow]Set LLM_PROVIDER and LLM_API_KEY to enable voice.[/yellow]"
        )
        return

    # State change display
    def on_state_change(state: Any) -> None:
        console.print(f"  [{_state_color(state)}]{state.value}[/{_state_color(state)}]")

    session = VoiceSession(
        capture=capture,
        transcriber=transcriber,
        synthesizer=synthesizer,
        player=player,
        model=model,
        on_state_change=on_state_change,
    )

    # Set up prompt-toolkit keybinding for Ctrl+P
    hotkey_event = asyncio.Event()

    try:
        from prompt_toolkit.input import create_input
        from prompt_toolkit.keys import Keys

        input_handle = create_input()

        async def _read_keys() -> None:
            """Read keys from terminal in background, fire hotkey_event on Ctrl+P."""
            with input_handle.raw_mode():
                with input_handle.attach(lambda: None):
                    while not session._session_closed.is_set():
                        # Use a short timeout so we can check session_closed
                        keys = await asyncio.to_thread(
                            _blocking_read_key, input_handle
                        )
                        if keys is None:
                            continue
                        for key in keys:
                            key_data = getattr(key, "key", key)
                            if key_data == Keys.ControlP or str(key_data) == "c-p":
                                console.print("  [cyan]🎤 listening...[/cyan]")
                                hotkey_event.set()
                            elif key_data == Keys.ControlC or str(key_data) == "c-c":
                                session._session_closed.set()
                                return

        key_task = asyncio.create_task(_read_keys())
    except ImportError:
        console.print(
            "  [yellow]prompt-toolkit not available; using manual input.[/yellow]"
        )
        console.print("  Type 'p' + Enter to speak, 'q' + Enter to quit.")
        key_task = asyncio.create_task(
            _fallback_input(hotkey_event, session, console)
        )

    # If a request was provided, start the agent run
    run_task: asyncio.Task[Any] | None = None
    if request:
        run_task = asyncio.create_task(
            session.start_agent_run(
                request,
                scene_directory=scene,
                reference_directory=before,
                image_paths=images,
                sar=sar,
                declared_level=level,
                ground_sample_distance=gsd,
                declared_registered=registered,
                thread=thread,
            )
        )
    else:
        # Welcome message for open session
        from app.voice.speech import AuthoredSpeech
        from app.db.identifiers import new_identifier, IdentifierPrefix
        welcome_speech = AuthoredSpeech(
            text="AERIS voice mode initialized and ready.",
            run_id="sys_session",
            utterance_id=new_identifier(IdentifierPrefix.UTTERANCE),
        )
        asyncio.create_task(session._speak(welcome_speech))

    try:
        await session.run(hotkey_source=hotkey_event)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await session.close()
        key_task.cancel()
        try:
            await key_task
        except (asyncio.CancelledError, Exception):
            pass
        if run_task is not None and not run_task.done():
            run_task.cancel()
            try:
                await run_task
            except (asyncio.CancelledError, Exception):
                pass
        console.print("\n  [dim]session closed[/dim]")


def _blocking_read_key(input_handle: Any) -> list[Any] | None:
    """Read one key press, blocking. Returns None on timeout or error."""
    import time

    try:
        # Small sleep to prevent tight busy-loop
        time.sleep(0.05)
        keys = input_handle.read_keys()
        return list(keys) if keys else None
    except EOFError:
        return None
    except Exception:
        return None


async def _fallback_input(
    hotkey_event: asyncio.Event,
    session: Any,
    console: Console,
) -> None:
    """Fallback when prompt-toolkit is unavailable: line-based input."""
    loop = asyncio.get_event_loop()
    while not session._session_closed.is_set():
        try:
            line = await loop.run_in_executor(None, input)
        except (EOFError, KeyboardInterrupt):
            session._session_closed.set()
            return
        line = line.strip().lower()
        if line in ("p", "push", "talk"):
            console.print("  [cyan]🎤 listening...[/cyan]")
            hotkey_event.set()
        elif line in ("q", "quit", "exit"):
            session._session_closed.set()
            return


def _state_color(state: Any) -> str:
    from app.constants.voice import VoiceSessionState

    return {
        VoiceSessionState.IDLE: "dim",
        VoiceSessionState.CAPTURING: "cyan",
        VoiceSessionState.TRANSCRIBING: "blue",
        VoiceSessionState.PENDING_APPROVAL: "yellow",
        VoiceSessionState.RUNNING: "green",
        VoiceSessionState.STANDBY: "dim yellow",
        VoiceSessionState.FAILED: "red",
        VoiceSessionState.CLOSED: "dim",
    }.get(state, "white")
