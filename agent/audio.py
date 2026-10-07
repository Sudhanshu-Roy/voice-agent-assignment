"""
Audio processing, real WebRTC noise suppression, quality confidence gating,
and configurable STT / TTS provider factories.
"""

import os
import math
import logging
from typing import Optional, Tuple, Any

from livekit.rtc import AudioProcessingModule, AudioFrame
from livekit.plugins import silero

logger = logging.getLogger("vaiu.agent.audio")

# Audio quality gate thresholds
MIN_AUDIO_RMS_THRESHOLD = 0.01  # Conservative energy threshold to reject background whispers/noise
MIN_STT_CONFIDENCE_THRESHOLD = 0.40  # Minimum confidence required before trusting transcript


class AudioQualityGate:
    """
    Conservative audio quality and confidence gate.
    Evaluates audio signal energy and STT confidence to prevent
    hallucinating phone digits on ambient noise.
    """

    @staticmethod
    def calculate_rms_energy(frame: AudioFrame) -> float:
        """Calculate Root Mean Square (RMS) energy from PCM audio frame."""
        try:
            data = frame.data
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


class NoiseSuppressionLayer:
    """
    Real WebRTC Native Audio Processing Module (APM) wrapper.
    Applies real-time noise suppression, acoustic echo cancellation (AEC),
    and automatic gain control (AGC) directly to audio frames.
    """

    def __init__(self):
        try:
            self._apm = AudioProcessingModule()
            logger.info("Native WebRTC AudioProcessingModule (APM) initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize native APM: {e}")
            self._apm = None

    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Process audio frame through native APM for real noise suppression."""
        if self._apm:
            try:
                self._apm.process_stream(frame)
            except Exception as e:
                logger.debug(f"APM process_stream notice: {e}")
        return frame


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
    """
    provider = os.getenv("STT_PROVIDER", "deepgram").lower().strip()

    if provider == "deepgram":
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            logger.warning("DEEPGRAM_API_KEY not configured. Falling back or running in test mode.")
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
            api_key=api_key or "local_dev_key"
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not configured.")
        from livekit.plugins import openai
        logger.info("Initializing OpenAI Whisper STT...")
        return openai.STT(
            model="whisper-1",
            api_key=api_key or "local_dev_key"
        )
    else:
        raise ValueError(f"Unsupported STT_PROVIDER: {provider}. Supported: 'deepgram', 'openai'")


def get_tts() -> Any:
    """
    Configurable TTS factory supporting ElevenLabs and OpenAI fallback.
    Reads TTS_PROVIDER environment variable ('elevenlabs' or 'openai').
    """
    provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower().strip()

    if provider == "elevenlabs":
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            logger.warning("ELEVENLABS_API_KEY not configured.")
        from livekit.plugins import elevenlabs
        logger.info("Initializing ElevenLabs TTS (eleven_multilingual_v2 model)...")
        return elevenlabs.TTS(
            model="eleven_multilingual_v2",
            api_key=api_key or "local_dev_key"
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not configured.")
        from livekit.plugins import openai
        logger.info("Initializing OpenAI TTS fallback...")
        return openai.TTS(
            model="tts-1",
            voice="alloy",
            api_key=api_key or "local_dev_key"
        )
    else:
        raise ValueError(f"Unsupported TTS_PROVIDER: {provider}. Supported: 'elevenlabs', 'openai'")
