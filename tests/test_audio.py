"""
Comprehensive unit tests for audio quality gating, RMS calculation,
noise suppression initialization, and STT event filtering.
"""

import array
import math
import pytest
from unittest.mock import MagicMock, AsyncMock

from agent.audio import (
    AudioQualityGate,
    NoiseSuppressionLayer,
    MIN_AUDIO_RMS_THRESHOLD,
    MIN_STT_CONFIDENCE_THRESHOLD,
)
from agent.session import VoicePhoneSession


class MockAudioFrame:
    """Mock audio frame containing raw PCM byte data."""
    def __init__(self, pcm_bytes: bytes):
        self.data = pcm_bytes


class MockSTTEvent:
    """Mock LiveKit STT transcription event."""
    def __init__(self, transcript: str, is_final: bool = True, item_id: str = "item-1", confidence: float = 0.95):
        self.transcript = transcript
        self.is_final = is_final
        self.item_id = item_id
        self.confidence = confidence


class TestAudioQualityAndProcessing:
    """Verifies audio quality gate, RMS energy calculation, and APM layer."""

    def test_1_rms_calculation_with_known_pcm_samples(self):
        """
        1. RMS calculation with known PCM samples.
        Known constant 16-bit PCM amplitude of 3276.8 yields exactly RMS ~ 0.10.
        """
        sample_val = 3277
        samples = array.array("h", [sample_val] * 1000)
        frame = MockAudioFrame(samples.tobytes())

        rms = AudioQualityGate.calculate_rms_energy(frame)
        expected = sample_val / 32768.0
        assert math.isclose(rms, expected, rel_tol=1e-3)
        assert rms > 0.09 and rms < 0.11

    def test_2_empty_audio_frame(self):
        """
        2. Empty audio frame returns 0.0 energy.
        """
        empty_frame = MockAudioFrame(b"")
        rms_empty = AudioQualityGate.calculate_rms_energy(empty_frame)
        assert rms_empty == 0.0

        none_frame_rms = AudioQualityGate.calculate_rms_energy(None)
        assert none_frame_rms == 0.0

    def test_3_low_energy_audio_rejection(self):
        """
        3. Low-energy audio rejection (inaudible/silence below MIN_AUDIO_RMS_THRESHOLD).
        """
        gate = AudioQualityGate()
        low_energy = MIN_AUDIO_RMS_THRESHOLD / 2.0  # 0.005 < 0.01
        is_ok, reason = gate.is_acceptable_quality(rms_energy=low_energy, stt_confidence=0.95)
        assert is_ok is False
        assert "Signal energy too low" in reason

    def test_4_normal_energy_audio_acceptance(self):
        """
        4. Normal-energy audio acceptance.
        """
        gate = AudioQualityGate()
        normal_energy = 0.08  # well above 0.01 threshold
        is_ok, reason = gate.is_acceptable_quality(rms_energy=normal_energy, stt_confidence=0.92)
        assert is_ok is True
        assert "acceptable" in reason.lower()

    def test_5_low_stt_confidence_rejection(self):
        """
        5. Low STT confidence rejection (below MIN_STT_CONFIDENCE_THRESHOLD=0.40).
        """
        gate = AudioQualityGate()
        low_confidence = 0.25
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.08, stt_confidence=low_confidence)
        assert is_ok is False
        assert "STT confidence too low" in reason

    def test_6_good_stt_confidence_acceptance(self):
        """
        6. Good STT confidence acceptance.
        """
        gate = AudioQualityGate()
        good_confidence = 0.95
        is_ok, reason = gate.is_acceptable_quality(rms_energy=0.08, stt_confidence=good_confidence)
        assert is_ok is True
        assert "acceptable" in reason.lower()

    def test_7_rms_calculation_failure_does_not_pass(self):
        """
        7. RMS calculation failure returns 0.0 (fails quality gate, does NOT silently pass).
        """
        class CorruptedFrame:
            @property
            def data(self):
                raise ValueError("Corrupted memory buffer")

        corrupted = CorruptedFrame()
        rms = AudioQualityGate.calculate_rms_energy(corrupted)
        # Must return 0.0 (explicit failure), not an acceptable fallback like 0.05
        assert rms == 0.0

        gate = AudioQualityGate()
        is_ok, reason = gate.is_acceptable_quality(rms_energy=rms, stt_confidence=0.95)
        assert is_ok is False
        assert "Signal energy too low" in reason

    def test_8_noise_suppression_apm_initialization(self):
        """
        8. Noise suppression / APM initialization behavior.
        Verifies NoiseSuppressionLayer instantiates cleanly without exceptions.
        """
        layer = NoiseSuppressionLayer()
        assert layer is not None
        # Passing None frame is handled gracefully without crash
        assert layer.process_frame(None) is None


def test_interim_events_ignored_and_only_final_processed():
    """
    Mandatory Fix #2:
    Prove that:
      interim "nine"
      interim "nine eight"
      interim "nine eight seven"
      final   "nine eight seven"
    results in ConversationManager receiving ONLY "nine eight seven",
    not all four events.
    """
    import asyncio

    async def _test():
        ctx = MagicMock()
        session = VoicePhoneSession(ctx)
        session._session = MagicMock()
        session._session.say = AsyncMock()

        interim1 = MockSTTEvent(transcript="nine", is_final=False)
        interim2 = MockSTTEvent(transcript="nine eight", is_final=False)
        interim3 = MockSTTEvent(transcript="nine eight seven", is_final=False)
        final_ev = MockSTTEvent(transcript="nine eight seven", is_final=True, item_id="final-id-1")

        # Send 3 interim events
        await session._on_user_transcript(interim1)
        await session._on_user_transcript(interim2)
        await session._on_user_transcript(interim3)

        # ConversationManager must have received ZERO transcripts so far
        assert len(session.conversation.accumulated_transcripts) == 0

        # Now send the final event
        await session._on_user_transcript(final_ev)

        # ConversationManager must have received ONLY the final utterance: "nine eight seven"
        assert session.conversation.accumulated_transcripts == ["nine eight seven"]
        assert len(session.conversation.accumulated_transcripts) == 1

    asyncio.run(_test())
