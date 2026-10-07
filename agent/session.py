"""
LiveKit Voice Agent session management.
Wires AudioProcessingModule, Silero VAD, Deepgram/Whisper STT,
ElevenLabs TTS, and ConversationManager.
"""

import os
import asyncio
import logging
from typing import Optional, Set

from livekit.agents import JobContext, RoomInputOptions
from livekit.agents.voice import AgentSession, Agent

from agent.audio import (
    get_vad,
    get_stt,
    get_tts,
    APMFrameProcessor,
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
    Enforces:
    - Real native LiveKit noise cancellation via RoomInputOptions(noise_cancellation=apm_processor)
    - Filtering of interim transcripts (only final transcripts reach the accumulator)
    - Deduplication of finalized speech events
    - Utterance-synchronized speech energy and STT confidence quality gating
    - LiveKit Agents 1.8.5 AgentSession startup
    """

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

        # Tracking processed final speech events to prevent duplication
        self._processed_event_ids: Set[str] = set()

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
            if hasattr(event, "is_final") and not event.is_final:
                return
            if not getattr(event, "is_final", True):
                return
            asyncio.create_task(self._on_user_transcript(event))

        # Define explicit Agent with deterministic instructions
        agent = Agent(
            instructions=(
                "You are a deterministic phone-number collection agent. "
                "Your only purpose is to collect and confirm a valid "
                "10-digit Indian mobile number. "
                "Never guess, infer, or invent phone digits."
            )
        )

        # Configure LiveKit RoomInputOptions with native WebRTC APM noise cancellation
        room_input_options = RoomInputOptions(
            noise_cancellation=self.apm_processor
        )

        # Correct LiveKit 1.8.5 start syntax with explicit room, agent, and native audio input options
        logger.info("Starting AgentSession with LiveKit 1.8.5 Agent and native Noise Cancellation...")
        await self._session.start(
            agent=agent,
            room=self.ctx.room,
            room_input_options=room_input_options,
        )

        # Initial greeting
        greeting = self.conversation.start_conversation()
        logger.info(f"Speaking initial greeting: '{greeting}'")
        await self._session.say(greeting)

    async def _on_user_transcript(self, event):
        """
        Handle incoming speech transcription.
        Enforces:
        1. Ignore interim events (only process is_final=True)
        2. Deduplicate repeated final events
        3. Real audio quality gating synchronized with utterance speech
        """
        # CRITICAL P0: Ignore interim transcription events!
        # Interim events must NEVER reach ConversationManager or modify the digit accumulator.
        is_final = getattr(event, "is_final", True)
        if not is_final:
            logger.debug(f"Ignoring interim transcript: '{getattr(event, 'transcript', '')}'")
            return

        text = getattr(event, "transcript", "") or getattr(event, "text", "")
        if not text or not text.strip():
            return

        # Deduplication check
        item_id = getattr(event, "item_id", None)
        event_signature = f"{item_id}:{text.strip()}" if item_id else text.strip()
        if event_signature in self._processed_event_ids:
            logger.debug(f"Ignoring duplicate final transcript event: {event_signature}")
            return
        self._processed_event_ids.add(event_signature)

        confidence = getattr(event, "confidence", None)
        speech_rms = self.apm_processor.get_and_reset_utterance_rms()
        logger.info(f"Final user speech transcribed: '{text}' (conf: {confidence}, speech_rms: {speech_rms})")

        # Cancel any pending incomplete silence timer
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        # Real audio quality gate check (using speech energy and STT confidence)
        if speech_rms > 0.0 or confidence is not None:
            is_ok, quality_msg = self.quality_gate.is_acceptable_quality(
                rms_energy=speech_rms if speech_rms > 0.0 else None,
                stt_confidence=confidence
            )
            if not is_ok:
                logger.warning(f"Audio quality gate rejected utterance: {quality_msg}")
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
