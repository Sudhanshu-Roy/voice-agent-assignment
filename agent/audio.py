"""
WebRTC APM noise processing, RMS/confidence quality gate,
and STT / TTS provider factories.
"""

import os
import math
import logging
from typing import Optional, Tuple, Any

from livekit import rtc
from livekit.rtc import AudioProcessingModule, AudioFrame
from livekit.plugins import silero

logger = logging.getLogger("vaiu.agent.audio")

# Audio quality gate thresholds
MIN_AUDIO_RMS_THRESHOLD = 0.01  # Conservative energy threshold to reject background whispers/noise
MIN_STT_CONFIDENCE_THRESHOLD = 0.40  # Minimum confidence required before trusting transcript


class AudioQualityGate:
    """
    Conservative audio quality and confidence gate based on real audio metrics.
    Evaluates real PCM audio signal energy and STT confidence to prevent
    hallucinating phone digits on ambient noise.
    """

    @staticmethod
    def calculate_rms_energy(frame: Optional[AudioFrame]) -> float:
        """
        Calculate Root Mean Square (RMS) energy from PCM audio frame.
        If frame is empty or invalid, returns 0.0 (representing inaudible/failed signal,
        which fails the quality gate).
        """
        if frame is None:
            return 0.0

        try:
            data = getattr(frame, "data", None)
            if not data:
                return 0.0
            import array
            samples = array.array("h", data)
            if not samples:
                return 0.0
            sum_squares = sum(s * s for s in samples)
            mean_square = sum_squares / len(samples)
            # Normalize to 0.0 - 1.0 range (32768 is max for int16)
            rms = math.sqrt(mean_square) / 32768.0
            return rms
        except Exception as e:
            logger.debug(f"RMS calculation error: {e}")
            return 0.0

    @staticmethod
    def is_acceptable_quality(
        rms_energy: Optional[float] = None,
        stt_confidence: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Conservative quality gate based on real audio metrics:
        - Rejects audio when measured RMS signal energy is below the speech threshold (inaudible/muted)
        - Rejects transcripts when STT provider confidence is below acceptable threshold
        """
        if rms_energy is not None and rms_energy < MIN_AUDIO_RMS_THRESHOLD:
            return False, f"Signal energy too low ({rms_energy:.4f} < {MIN_AUDIO_RMS_THRESHOLD})"

        if stt_confidence is not None and stt_confidence < MIN_STT_CONFIDENCE_THRESHOLD:
            return False, f"STT confidence too low ({stt_confidence:.2f} < {MIN_STT_CONFIDENCE_THRESHOLD})"

        return True, "Audio quality acceptable"


class APMFrameProcessor(rtc.FrameProcessor[AudioFrame]):
    """
    LiveKit native FrameProcessor integrating WebRTC AudioProcessingModule (APM).
    Explicitly enables:
    - Noise Suppression (NS)
    - Acoustic Echo Cancellation (AEC)
    - High-Pass Filter (HPF)
    - Automatic Gain Control (AGC)

    Directly passed to LiveKit RoomInputOptions(noise_cancellation=...) so that
    incoming participant audio is filtered through WebRTC APM BEFORE reaching STT.
    Also tracks speech energy across the utterance window (preventing silence-tail falsing).
    """

    def __init__(
        self,
        echo_cancellation: bool = True,
        noise_suppression: bool = True,
        high_pass_filter: bool = True,
        auto_gain_control: bool = True,
    ):
        super().__init__()
        self._enabled = True
        try:
            self._apm = AudioProcessingModule(
                echo_cancellation=echo_cancellation,
                noise_suppression=noise_suppression,
                high_pass_filter=high_pass_filter,
                auto_gain_control=auto_gain_control,
            )
            logger.info("LiveKit WebRTC APM FrameProcessor initialized with active Noise Suppression, AEC, AGC, and HPF.")
        except Exception as e:
            logger.warning(f"Could not initialize native APM: {e}")
            self._apm = None

        self._utterance_peak_rms: float = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def _process(self, frame: AudioFrame) -> AudioFrame:
        """Process incoming audio frame through native APM and track utterance speech energy."""
        if not self._enabled or frame is None:
            return frame

        # Apply real WebRTC noise suppression to the audio stream reaching STT
        if self._apm:
            try:
                self._apm.process_stream(frame)
            except Exception as e:
                logger.debug(f"APM process_stream notice: {e}")

        # Track peak speech energy across the utterance window
        rms = AudioQualityGate.calculate_rms_energy(frame)
        if rms > self._utterance_peak_rms:
            self._utterance_peak_rms = rms

        return frame

    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Direct frame processing helper."""
        return self._process(frame)

    def get_and_reset_utterance_rms(self) -> float:
        """
        Retrieves the peak speech RMS energy captured during the utterance,
        and resets for the subsequent utterance.
        """
        val = self._utterance_peak_rms
        self._utterance_peak_rms = 0.0
        return val

    def _close(self) -> None:
        pass


# Backward-compatible alias
NoiseSuppressionLayer = APMFrameProcessor


def get_vad(min_silence_duration: float = 2.0):
    """
    Silero VAD with tuned pause tolerance.
    Allows user up to 2-4 seconds pause while reciting phone numbers
    without prematurely cutting them off.
    """
    logger.info(f"Loading Silero VAD (min_silence_duration={min_silence_duration}s)...")
    return silero.VAD.load(
        min_silence_duration=min_silence_duration,
        min_speech_duration=0.08,
        activation_threshold=0.5
    )


def get_stt() -> Any:
    """
    Configurable STT factory supporting Deepgram and OpenAI Whisper.
    Reads STT_PROVIDER environment variable ('deepgram' or 'openai').
    Enforces real provider credentials in live production mode.
    """
    provider = os.getenv("STT_PROVIDER", "deepgram").lower().strip()

    if provider == "deepgram":
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DEEPGRAM_API_KEY environment variable is required for live Deepgram STT. "
                "Please configure DEEPGRAM_API_KEY in your .env file, or run 'python -m agent.main test' for offline dialog testing."
            )
        from livekit.plugins import deepgram
        model = os.getenv("DEEPGRAM_MODEL", "nova-3")
        language = os.getenv("DEEPGRAM_LANGUAGE", "multi")
        logger.info(f"Initializing Deepgram STT (model={model}, language={language} for simultaneous Hindi+English)...")
        return deepgram.STT(
            model=model,
            language=language,
            smart_format=True,
            interim_results=True,
            punctuate=True,
            numerals=True,
            api_key=api_key
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is required for OpenAI Whisper STT. "
                "Please configure OPENAI_API_KEY in your .env file."
            )
        from livekit.plugins import openai
        logger.info("Initializing OpenAI Whisper STT...")
        return openai.STT(
            model="whisper-1",
            api_key=api_key
        )
    else:
        raise ValueError(f"Unsupported STT_PROVIDER: {provider}. Supported: 'deepgram', 'openai'")


def get_tts() -> Any:
    """
    Configurable TTS factory supporting ElevenLabs and OpenAI fallback.
    Reads TTS_PROVIDER environment variable ('elevenlabs' or 'openai').
    Enforces real provider credentials in live production mode.
    """
    provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower().strip()

    if provider == "elevenlabs":
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY environment variable is required for live ElevenLabs TTS. "
                "Please configure ELEVENLABS_API_KEY in your .env file, or run 'python -m agent.main test' for offline dialog testing."
            )
        from livekit.plugins import elevenlabs
        logger.info("Initializing ElevenLabs TTS (eleven_multilingual_v2 model)...")
        return elevenlabs.TTS(
            model="eleven_multilingual_v2",
            api_key=api_key
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is required for OpenAI TTS. "
                "Please configure OPENAI_API_KEY in your .env file."
            )
        from livekit.plugins import openai
        logger.info("Initializing OpenAI TTS fallback...")
        return openai.TTS(
            model="tts-1",
            voice="alloy",
            api_key=api_key
        )
    else:
        raise ValueError(f"Unsupported TTS_PROVIDER: {provider}. Supported: 'elevenlabs', 'openai'")
