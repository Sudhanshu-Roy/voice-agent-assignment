"""
Regression tests for STT interim vs final event handling,
event deduplication, and AudioQualityGate behavior.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from agent.session import VoicePhoneSession
from agent.audio import AudioQualityGate


class DummyEvent:
    def __init__(self, transcript: str, is_final: bool = True, item_id: str = "item-1", confidence: float = 0.95):
        self.transcript = transcript
        self.is_final = is_final
        self.item_id = item_id
        self.confidence = confidence


class TestSTTAndAudioQuality:
    """Verifies STT interim vs final events and audio gate."""

    def test_interim_events_are_ignored(self):
        """Interim transcription events must never alter conversation state or digit accumulator."""
        ctx = MagicMock()
        session = VoicePhoneSession(ctx)
        session._session = MagicMock()
        session._session.say = AsyncMock()

        # Simulate user reciting partial digits as interim streaming chunks
        interim1 = DummyEvent(transcript="nine", is_final=False)
        interim2 = DummyEvent(transcript="nine eight", is_final=False)
        interim3 = DummyEvent(transcript="nine eight seven", is_final=False)

        async def _test():
            await session._on_user_transcript(interim1)
            await session._on_user_transcript(interim2)
            await session._on_user_transcript(interim3)

            # Nothing should be in conversation accumulator
            assert len(session.conversation.accumulated_transcripts) == 0
            assert session.conversation.current_candidate_number is None

        asyncio.run(_test())

    def test_final_event_is_processed(self):
        """Final events must be processed exactly as completed user utterances."""
        ctx = MagicMock()
        session = VoicePhoneSession(ctx)
        session._session = MagicMock()
        session._session.say = AsyncMock()

        final_event = DummyEvent(
            transcript="nine eight seven six five four three two one zero",
            is_final=True,
            item_id="final-item-1",
            confidence=0.98
        )

        async def _test():
            await session._on_user_transcript(final_event)

            # Final number parsed and confirmation prompted
            assert session.conversation.current_candidate_number == "9876543210"
            session._session.say.assert_called_once()
            called_prompt = session._session.say.call_args[0][0]
            assert "9, 8, 7, 6, 5, 4, 3, 2, 1, 0" in called_prompt

        asyncio.run(_test())

    def test_duplicate_final_events_protection(self):
        """Re-sent duplicate final events with the same item_id must not be processed twice."""
        ctx = MagicMock()
        session = VoicePhoneSession(ctx)
        session._session = MagicMock()
        session._session.say = AsyncMock()

        final_event = DummyEvent(
            transcript="nine eight seven six five four three two one zero",
            is_final=True,
            item_id="duplicate-id",
            confidence=0.95
        )

        async def _test():
            await session._on_user_transcript(final_event)
            assert session._session.say.call_count == 1

            # Re-send same finalized event
            await session._on_user_transcript(final_event)
            # Must still only be called once
            assert session._session.say.call_count == 1

        asyncio.run(_test())

    def test_audio_quality_gate_acceptable_audio(self):
        """Good RMS signal and high STT confidence must be accepted."""
        gate = AudioQualityGate()
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.08, stt_confidence=0.92)
        assert is_ok is True
        assert "acceptable" in reason

    def test_audio_quality_gate_low_rms_energy_rejected(self):
        """Inaudible / muted microphone (low RMS) must be rejected."""
        gate = AudioQualityGate()
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.002, stt_confidence=0.90)
        assert is_ok is False
        assert "Signal energy too low" in reason

    def test_audio_quality_gate_low_stt_confidence_rejected(self):
        """Low STT confidence must be rejected instead of guessing."""
        gate = AudioQualityGate()
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.05, stt_confidence=0.25)
        assert is_ok is False
        assert "STT confidence too low" in reason
