"""
Unit tests for the real-time audio pipeline:
- Native LiveKit APM FrameProcessor noise cancellation
- RMS energy calculation and utterance speech tracking
- Conservative quality gating (RMS and STT confidence)
- Protection against interim streaming transcripts mutating state
"""

import array
import math
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from agent.audio import (
    AudioQualityGate,
    APMFrameProcessor,
    NoiseSuppressionLayer,
    MIN_AUDIO_RMS_THRESHOLD,
    MIN_STT_CONFIDENCE_THRESHOLD,
)
from agent.session import VoicePhoneSession
from livekit.agents import RoomInputOptions


class MockAudioFrame:
    """Mock audio frame containing 16-bit PCM bytes."""
    def __init__(self, pcm_bytes: bytes):
        self.data = pcm_bytes


class MockSTTEvent:
    """Mock LiveKit STT transcription event."""
    def __init__(self, transcript: str, is_final: bool = True, item_id: str = "item-1", confidence: float = 0.95):
        self.transcript = transcript
        self.is_final = is_final
        self.item_id = item_id
        self.confidence = confidence


class TestRMSEnergyCalculation:
    """Verifies RMS energy calculation across various audio frame conditions."""

    def test_valid_nonsilent_frame_positive_rms(self):
        """1. Valid non-silent frame produces a positive, accurate RMS."""
        sample_val = 3277  # ~10% amplitude in 16-bit PCM
        samples = array.array("h", [sample_val] * 1000)
        frame = MockAudioFrame(samples.tobytes())

        rms = AudioQualityGate.calculate_rms_energy(frame)
        expected = sample_val / 32768.0
        assert math.isclose(rms, expected, rel_tol=1e-3)
        assert rms > 0.05

    def test_silent_frame_produces_zero_rms(self):
        """2. Silent frame produces approximately zero RMS."""
        silence_samples = array.array("h", [0] * 1000)
        frame = MockAudioFrame(silence_samples.tobytes())

        rms = AudioQualityGate.calculate_rms_energy(frame)
        assert rms == 0.0

    def test_empty_or_none_frame_safely_produces_zero(self):
        """3. Empty/invalid frame safely produces zero energy."""
        empty_frame = MockAudioFrame(b"")
        assert AudioQualityGate.calculate_rms_energy(empty_frame) == 0.0
        assert AudioQualityGate.calculate_rms_energy(None) == 0.0

    def test_measurement_errors_do_not_become_accepted_audio(self):
        """4. Measurement errors safely return 0.0 (fails quality gate, does NOT pass)."""
        class CorruptedFrame:
            @property
            def data(self):
                raise RuntimeError("Hardware buffer read error")

        corrupted = CorruptedFrame()
        rms = AudioQualityGate.calculate_rms_energy(corrupted)
        assert rms == 0.0

        gate = AudioQualityGate()
        is_ok, reason = gate.is_acceptable_quality(rms_energy=rms, stt_confidence=0.95)
        assert is_ok is False
        assert "Signal energy too low" in reason


class TestAudioQualityGate:
    """Verifies conservative gating against inaudible speech or low STT confidence."""

    def test_valid_quality_accepted(self):
        """1. Valid energy and high confidence are accepted."""
        gate = AudioQualityGate()
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.08, stt_confidence=0.95)
        assert is_ok is True
        assert "acceptable" in reason.lower()

    def test_too_low_rms_quality_rejected(self):
        """2. Too-low energy (whisper/inaudible < 0.01) is rejected."""
        gate = AudioQualityGate()
        low_energy = 0.005
        is_ok, reason = gate.is_acceptable_quality(rms_energy=low_energy, stt_confidence=0.95)
        assert is_ok is False
        assert "Signal energy too low" in reason

    def test_invalid_measurement_zero_rms_rejected(self):
        """3. Zero RMS (failed measurement or total silence) is rejected."""
        gate = AudioQualityGate()
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.0, stt_confidence=0.90)
        assert is_ok is False
        assert "Signal energy too low" in reason

    def test_low_stt_confidence_rejected(self):
        """4. Low STT confidence (< 0.40) is rejected rather than guessing digits."""
        gate = AudioQualityGate()
        low_confidence = 0.25
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.08, stt_confidence=low_confidence)
        assert is_ok is False
        assert "STT confidence too low" in reason

    def test_good_stt_confidence_accepted(self):
        """5. Good STT confidence is accepted."""
        gate = AudioQualityGate()
        good_confidence = 0.88
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.07, stt_confidence=good_confidence)
        assert is_ok is True
        assert "acceptable" in reason.lower()


class TestNativeLiveKitNoiseProcessing:
    """Verifies APMFrameProcessor integration with WebRTC and RoomInputOptions."""

    def test_apm_processor_initialization_and_enabled(self):
        """Verifies native APM explicitly initializes with NS, AEC, AGC, and HPF."""
        processor = APMFrameProcessor(
            echo_cancellation=True,
            noise_suppression=True,
            high_pass_filter=True,
            auto_gain_control=True,
        )
        assert processor.enabled is True
        assert processor._apm is not None

    def test_apm_process_frame_is_invoked(self):
        """Verifies frame processing method executes and tracks speech energy."""
        processor = APMFrameProcessor()
        sample_val = 3277
        samples = array.array("h", [sample_val] * 500)
        frame = MockAudioFrame(samples.tobytes())

        # Process frame
        processed = processor.process_frame(frame)
        assert processed is frame

        # Energy tracking must capture the speech amplitude
        peak_rms = processor.get_and_reset_utterance_rms()
        assert peak_rms > 0.05

        # Reset ensures subsequent measurement starts clean
        assert processor.get_and_reset_utterance_rms() == 0.0

    def test_native_room_input_options_integration(self):
        """Verifies APM processor seamlessly plugs into LiveKit RoomInputOptions."""
        processor = APMFrameProcessor()
        options = RoomInputOptions(noise_cancellation=processor)
        assert options.noise_cancellation is processor


def test_interim_events_do_not_modify_conversation_state():
    """
    Prove that:
      interim "nine"
      interim "nine eight"
      interim "nine eight seven"
      final   "nine eight seven"
    results in ConversationManager receiving ONLY "nine eight seven",
    not intermediate fragments.
    """
    async def _test():
        ctx = MagicMock()
        session = VoicePhoneSession(ctx)
        session._session = MagicMock()
        session._session.say = AsyncMock()

        # Simulate speech audio passing into APM processor during utterance
        samples = array.array("h", [3277] * 500)
        session.apm_processor.process_frame(MockAudioFrame(samples.tobytes()))

        interim1 = MockSTTEvent(transcript="nine", is_final=False)
        interim2 = MockSTTEvent(transcript="nine eight", is_final=False)
        interim3 = MockSTTEvent(transcript="nine eight seven", is_final=False)
        final_ev = MockSTTEvent(transcript="nine eight seven", is_final=True, item_id="final-id-1")

        # Send 3 interim events
        await session._on_user_transcript(interim1)
        await session._on_user_transcript(interim2)
        await session._on_user_transcript(interim3)

        # ConversationManager must have received ZERO transcripts from interim events
        assert len(session.conversation.accumulated_transcripts) == 0

        # Now send final event
        await session._on_user_transcript(final_ev)

        # ConversationManager must have received ONLY the final completed transcript
        assert session.conversation.accumulated_transcripts == ["nine eight seven"]
        assert len(session.conversation.accumulated_transcripts) == 1

    asyncio.run(_test())
