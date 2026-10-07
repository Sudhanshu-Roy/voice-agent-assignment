"""
LiveKit voice session wiring.

Connects noise cancellation, VAD, STT, TTS, and the conversation state machine.
No LLM is used to invent digits — parsing stays deterministic in ConversationManager.
"""

import asyncio
import logging
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

    async def run(self):
        logger.info("Connecting to LiveKit room: %s", self.ctx.room.name)
        await self.ctx.connect()
        logger.info("Joined room.")

        vad = get_vad(min_silence_duration=2.0)
        stt = get_stt()
        tts = get_tts()

        # Endpointing tuned so mid-number pauses (up to ~4s) are not cut off early
        turn_handling: TurnHandlingOptions = {
            "endpointing": {
                "mode": "fixed",
                "min_delay": 1.8,
                "max_delay": INCOMPLETE_SILENCE_TIMEOUT,
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
        await self._session.say(greeting)

    async def _on_user_transcript(self, event):
        # Only final transcripts update the digit buffer
        is_final = getattr(event, "is_final", True)
        if not is_final:
            return

        text = getattr(event, "transcript", "") or getattr(event, "text", "")
        if not text or not text.strip():
            return

        item_id = getattr(event, "item_id", None)
        event_signature = f"{item_id}:{text.strip()}" if item_id else text.strip()
        if event_signature in self._processed_event_ids:
            return
        self._processed_event_ids.add(event_signature)

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

        if speech_rms > 0.0 or confidence is not None:
            is_ok, quality_msg = self.quality_gate.is_acceptable_quality(
                rms_energy=speech_rms if speech_rms > 0.0 else None,
                stt_confidence=confidence,
            )
            if not is_ok:
                logger.warning("Quality gate rejected utterance: %s", quality_msg)
                if self._session:
                    await self._session.say(
                        "I could not hear that clearly. "
                        "Could you please repeat your 10-digit number?"
                    )
                return

        reply, state = await self.conversation.handle_user_speech(
            transcript=text,
            stt_confidence=confidence,
        )

        if reply and self._session:
            logger.info("Agent reply: %s", reply)
            await self._session.say(reply)
        elif reply is None and state == DialogState.COLLECTING:
            self._timeout_task = asyncio.create_task(self._handle_incomplete_silence())

    async def _handle_incomplete_silence(self):
        """Wait up to INCOMPLETE_SILENCE_TIMEOUT before asking the user to continue."""
        try:
            await asyncio.sleep(INCOMPLETE_SILENCE_TIMEOUT)
            timeout_prompt = self.conversation.handle_incomplete_timeout()
            if timeout_prompt and self._session:
                logger.info("Silence timeout: %s", timeout_prompt)
                await self._session.say(timeout_prompt)
        except asyncio.CancelledError:
            pass
