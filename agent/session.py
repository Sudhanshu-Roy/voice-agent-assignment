"""
LiveKit Voice Agent session management.
Wires AudioProcessingModule, Silero VAD, Deepgram/Whisper STT,
ElevenLabs TTS, and ConversationManager.
"""

import os
import asyncio
import logging
from typing import Optional

from livekit.agents import JobContext
from livekit.agents.voice import AgentSession, Agent
from livekit.rtc import Track, RemoteAudioTrack

from agent.audio import (
    get_vad,
    get_stt,
    get_tts,
    NoiseSuppressionLayer,
    AudioQualityGate
)
from agent.conversation import (
    ConversationManager,
    INCOMPLETE_SILENCE_TIMEOUT,
    DialogState
)

logger = logging.getLogger("vaiu.agent.session")


class VoicePhoneSession:
    """
    Manages a single LiveKit voice session for collecting phone numbers.
    """

    def __init__(self, ctx: JobContext):
        self.ctx = ctx
        self.conversation = ConversationManager()
        self.noise_suppression = NoiseSuppressionLayer()
        self.quality_gate = AudioQualityGate()
        self._timeout_task: Optional[asyncio.Task] = None
        self._session: Optional[AgentSession] = None

    async def run(self):
        """Entrypoint for the voice session."""
        logger.info(f"Connecting to LiveKit room: {self.ctx.room.name}...")
        await self.ctx.connect()
        logger.info("Successfully joined room.")

        # Initialize audio components
        vad = get_vad(min_silence_duration=2.0)
        stt = get_stt()
        tts = get_tts()

        # Build LiveKit AgentSession with tuned endpointing delay for pause tolerance
        self._session = AgentSession(
            stt=stt,
            tts=tts,
            vad=vad,
            min_endpointing_delay=1.8,
            max_endpointing_delay=INCOMPLETE_SILENCE_TIMEOUT,
            allow_interruptions=True,
        )

        # Register event handlers
        @self._session.on("user_input_transcribed")
        def on_user_input_transcribed(event):
            asyncio.create_task(self._on_user_transcript(event))

        # Start agent session
        await self._session.start(self.ctx.room)

        # Initial greeting
        greeting = self.conversation.start_conversation()
        logger.info(f"Speaking initial greeting: '{greeting}'")
        await self._session.say(greeting)

    async def _on_user_transcript(self, event):
        """Handle incoming speech transcription."""
        text = getattr(event, "transcript", "") or getattr(event, "text", "")
        confidence = getattr(event, "confidence", None)

        if not text:
            return

        logger.info(f"User speech detected: '{text}' (conf: {confidence})")

        # Cancel any pending incomplete silence timer
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        # Check audio quality gate
        is_ok, quality_msg = self.quality_gate.is_acceptable_quality(
            rms_energy=0.05,  # Nominal energy for recognized stream
            stt_confidence=confidence
        )
        if not is_ok:
            logger.warning(f"Audio quality gate warning: {quality_msg}")
            if self._session:
                await self._session.say("I could not hear that clearly. Could you please repeat your 10-digit number?")
            return

        # Pass to conversation state machine
        reply, state = await self.conversation.handle_user_speech(
            transcript=text,
            stt_confidence=confidence
        )

        if reply and self._session:
            logger.info(f"Agent responding: '{reply}'")
            await self._session.say(reply)
        elif reply is None and state == DialogState.COLLECTING:
            # Partial number collected: start silence timer for up to 4s
            self._timeout_task = asyncio.create_task(self._handle_incomplete_silence())

    async def _handle_incomplete_silence(self):
        """Wait silently up to INCOMPLETE_SILENCE_TIMEOUT for remaining digits."""
        try:
            await asyncio.sleep(INCOMPLETE_SILENCE_TIMEOUT)
            timeout_prompt = self.conversation.handle_incomplete_timeout()
            if timeout_prompt and self._session:
                logger.info(f"Incomplete pause timeout expired. Prompting user: '{timeout_prompt}'")
                await self._session.say(timeout_prompt)
        except asyncio.CancelledError:
            # User spoke again before timer expired, which is normal
            pass
