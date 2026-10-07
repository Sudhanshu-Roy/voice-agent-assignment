"""
LiveKit voice session wiring.

Connects noise cancellation, VAD, STT, TTS, and the conversation state machine.
No LLM is used to invent digits — parsing stays deterministic in ConversationManager.
"""

import asyncio
import logging
import time
from typing import Optional, Set

from livekit.agents import JobContext, RoomInputOptions, TurnHandlingOptions
from livekit.agents.voice import AgentSession, Agent

from agent.audio import (
    get_vad,
    get_stt,
    get_tts,
    APMFrameProcessor,
    AudioQualityGate,
)
from agent.conversation import (
    ConversationManager,
    INCOMPLETE_SILENCE_TIMEOUT,
    DialogState,
)

logger = logging.getLogger("vaiu.agent.session")


class PhoneCollectorAgent(Agent):
    """Agent shell without an LLM reply path — dialog is driven by ConversationManager."""

    def __init__(self):
        super().__init__(
            instructions=(
                "Collect and confirm a valid 10-digit Indian mobile number. "
                "Do not guess or invent digits."
            ),
            llm=None,
        )

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        # No LLM reply — ConversationManager already handled the transcript.
        return


class VoicePhoneSession:
    """One LiveKit room session for phone number collection."""

    def __init__(self, ctx: JobContext):
        self.ctx = ctx
        self.conversation = ConversationManager()
        self.apm_processor = APMFrameProcessor(
            echo_cancellation=True,
            noise_suppression=True,
            high_pass_filter=True,
            auto_gain_control=True,
        )
        self.quality_gate = AudioQualityGate()
        self._timeout_task: Optional[asyncio.Task] = None
        self._session: Optional[AgentSession] = None
        self._processed_event_ids: Set[str] = set()
        self._speaking_lock = asyncio.Lock()

    async def run(self):
        logger.info("Connecting to LiveKit room: %s", self.ctx.room.name)
        await self.ctx.connect()
        logger.info("Joined room.")

        vad = get_vad(min_silence_duration=1.2)
        stt = get_stt()
        tts = get_tts()

        # Keep endpointing responsive; ConversationManager still combines digit chunks.
        turn_handling: TurnHandlingOptions = {
            "endpointing": {
                "mode": "fixed",
                "min_delay": 0.6,
                "max_delay": 2.0,
            },
            "interruption": {
                "enabled": True,
            },
        }

        self._session = AgentSession(
            stt=stt,
            tts=tts,
            vad=vad,
            llm=None,
            turn_handling=turn_handling,
        )

        @self._session.on("user_input_transcribed")
        def on_user_input_transcribed(event):
            if hasattr(event, "is_final") and not event.is_final:
                return
            if not getattr(event, "is_final", True):
                return
            asyncio.create_task(self._on_user_transcript(event))

        agent = PhoneCollectorAgent()

        room_input_options = RoomInputOptions(
            noise_cancellation=self.apm_processor
        )

        logger.info("Starting AgentSession with WebRTC APM noise cancellation")
        await self._session.start(
            agent=agent,
            room=self.ctx.room,
            room_input_options=room_input_options,
        )

        greeting = self.conversation.start_conversation()
        logger.info("Greeting: %s", greeting)
        await self._speak(greeting)

    async def _speak(self, text: str) -> None:
        """Speak a prompt and wait until playback finishes when possible."""
        if not self._session or not text:
            return
        async with self._speaking_lock:
            handle = self._session.say(text, allow_interruptions=False)
            wait = getattr(handle, "wait_for_playout", None)
            if callable(wait):
                try:
                    await wait()
                    return
                except Exception as exc:
                    logger.debug("wait_for_playout notice: %s", exc)
            # Fallback: give TTS a short head start if handle is not awaitable
            if asyncio.iscoroutine(handle) or inspect_awaitable(handle):
                try:
                    await handle  # type: ignore[misc]
                except TypeError:
                    await asyncio.sleep(0.3)
            else:
                await asyncio.sleep(0.3)

    async def _on_user_transcript(self, event):
        # Only final transcripts update the digit buffer
        is_final = getattr(event, "is_final", True)
        if not is_final:
            return

        text = getattr(event, "transcript", "") or getattr(event, "text", "")
        if not text or not text.strip():
            return

        # Deduplicate ONLY by LiveKit item id (never by raw text — users often
        # repeat "yes" / "hello" and those must still be processed).
        item_id = getattr(event, "item_id", None) or getattr(event, "id", None)
        if item_id:
            event_signature = str(item_id)
        else:
            event_signature = f"{time.monotonic_ns()}:{text.strip()}"

        if event_signature in self._processed_event_ids:
            logger.debug("Skipping duplicate transcript event id=%s", event_signature)
            return
        self._processed_event_ids.add(event_signature)
        # Keep the set from growing forever in long sessions
        if len(self._processed_event_ids) > 500:
            self._processed_event_ids = set(list(self._processed_event_ids)[-200:])

        confidence = getattr(event, "confidence", None)
        speech_rms = self.apm_processor.get_and_reset_utterance_rms()
        logger.info(
            "Final transcript: '%s' (conf=%s, rms=%.4f)",
            text,
            confidence,
            speech_rms,
        )

        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        # Only apply energy gate when we actually measured energy.
        # Never block confirmation replies on a missing confidence score.
        if speech_rms > 0.0:
            is_ok, quality_msg = self.quality_gate.is_acceptable_quality(
                rms_energy=speech_rms,
                stt_confidence=confidence,
            )
            if not is_ok:
                logger.warning("Quality gate rejected utterance: %s", quality_msg)
                await self._speak(
                    "I could not hear that clearly. "
                    "Could you please repeat your 10-digit number?"
                )
                return

        reply, state = await self.conversation.handle_user_speech(
            transcript=text,
            stt_confidence=confidence,
        )

        if reply:
            logger.info("Agent reply: %s", reply)
            await self._speak(reply)
        elif reply is None and state == DialogState.COLLECTING:
            self._timeout_task = asyncio.create_task(self._handle_incomplete_silence())

    async def _handle_incomplete_silence(self):
        """Wait up to INCOMPLETE_SILENCE_TIMEOUT before asking the user to continue."""
        try:
            await asyncio.sleep(INCOMPLETE_SILENCE_TIMEOUT)
            timeout_prompt = self.conversation.handle_incomplete_timeout()
            if timeout_prompt:
                logger.info("Silence timeout: %s", timeout_prompt)
                await self._speak(timeout_prompt)
        except asyncio.CancelledError:
            pass


def inspect_awaitable(obj) -> bool:
    return hasattr(obj, "__await__")
