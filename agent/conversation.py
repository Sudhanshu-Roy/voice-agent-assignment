"""
Conversation state machine for phone number collection.

Tracks COLLECTING -> CONFIRMING -> SAVED, combines paused segments,
and saves only after the user confirms.
"""

import os
import asyncio
import logging
from enum import Enum
from typing import Optional, Dict, Any, Tuple
import httpx

from parser.phone_parser import (
    parse_phone_number,
    detect_confirmation,
    format_digits_for_speech
)
from agent import prompts

logger = logging.getLogger("vaiu.agent.conversation")

# Timeout in seconds to wait silently while digits are incomplete
INCOMPLETE_SILENCE_TIMEOUT = 4.0

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


class DialogState(str, Enum):
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    CONFIRMING = "CONFIRMING"
    SAVED = "SAVED"


def mask_number(num: Optional[str]) -> str:
    """Mask phone number for safe logging: e.g. 9876543210 -> ******3210"""
    if not num:
        return "None"
    if len(num) >= 4:
        return f"******{num[-4:]}"
    return "****"


class ConversationManager:
    """
    Stateful dialog manager for phone number collection.
    Manages:
    - Accumulated speech segments across natural pauses
    - State transitions (COLLECTING -> CONFIRMING -> SAVED)
    - Deterministic parsing and self-correction
    - Affirmative / negative confirmation
    - Backend persistence via REST API
    """

    def __init__(self, backend_url: str = BACKEND_URL):
        self.state: DialogState = DialogState.IDLE
        self.backend_url: str = backend_url.rstrip("/")

        # Transcript accumulators
        self.accumulated_transcripts: list[str] = []
        self.current_candidate_number: Optional[str] = None
        self.current_candidate_language: str = "en"
        self.current_candidate_raw: str = ""

        # Pause and timeout timer handle
        self._incomplete_timer_task: Optional[asyncio.Task] = None

    def start_conversation(self) -> str:
        """Start the conversation and return the initial greeting."""
        self.state = DialogState.COLLECTING
        self.accumulated_transcripts.clear()
        self.current_candidate_number = None
        self.current_candidate_raw = ""
        logger.info("Session started: State transitioned to COLLECTING")
        return prompts.GREETING

    async def handle_user_speech(
        self,
        transcript: str,
        stt_confidence: Optional[float] = None
    ) -> Tuple[Optional[str], DialogState]:
        """
        Process user speech transcript and return:
        (agent_reply_text, current_dialog_state)
        If agent_reply_text is None, it means the agent should wait silently for more digits.
        """
        cleaned = transcript.strip()
        if not cleaned:
            return None, self.state

        logger.info(f"Transcript received: '{cleaned}' (State: {self.state.value})")

        # ---------------------------------------------------------------------
        # STATE: CONFIRMING (Waiting for user confirmation)
        # ---------------------------------------------------------------------
        if self.state == DialogState.CONFIRMING:
            confirm = detect_confirmation(cleaned)
            logger.info(f"Confirmation intent detected: {confirm} for candidate {mask_number(self.current_candidate_number)}")

            if confirm is True:
                # User confirmed! Persist to backend.
                save_ok, err_msg = await self._persist_phone_number()
                self.state = DialogState.SAVED
                if save_ok:
                    logger.info(f"Phone number {mask_number(self.current_candidate_number)} successfully confirmed and saved.")
                    return prompts.SAVED_SUCCESS, self.state
                else:
                    logger.error(f"Persistence error: {err_msg}")
                    return (
                        f"Thank you. Your number {format_digits_for_speech(self.current_candidate_number or '')} is noted, "
                        f"but our backend returned: {err_msg}.",
                        self.state
                    )

            elif confirm is False:
                # User denied the number: reset and restart collection
                logger.info("User denied the recited phone number. Resetting buffer.")
                self.state = DialogState.COLLECTING
                self.accumulated_transcripts.clear()
                self.current_candidate_number = None
                self.current_candidate_raw = ""
                return prompts.DENIED_RETRY, self.state

            else:
                # Ambiguous confirmation response
                logger.warning(f"Ambiguous confirmation response: '{cleaned}'")
                return prompts.AMBIGUOUS_CONFIRMATION, self.state

        # ---------------------------------------------------------------------
        # STATE: COLLECTING (Collecting 10-digit phone number)
        # ---------------------------------------------------------------------
        if self.state in {DialogState.COLLECTING, DialogState.IDLE}:
            self.state = DialogState.COLLECTING
            self.accumulated_transcripts.append(cleaned)
            full_transcript = " ".join(self.accumulated_transcripts)

            # Deterministic parse
            result = parse_phone_number(full_transcript)
            logger.info(
                f"Parser result: success={result['success']}, "
                f"digits={result['digits']}, "
                f"number={mask_number(result.get('number'))}, "
                f"lang={result['language']}, "
                f"reason={result.get('reason')}"
            )

            # Case A: Valid 10-digit number collected!
            if result["success"] and result["number"]:
                self.current_candidate_number = result["number"]
                self.current_candidate_language = result["language"]
                self.current_candidate_raw = full_transcript
                self.state = DialogState.CONFIRMING

                # Cancel any pending incomplete silence timer
                if self._incomplete_timer_task and not self._incomplete_timer_task.done():
                    self._incomplete_timer_task.cancel()

                # Prompt digit-by-digit confirmation
                confirmation_msg = prompts.get_confirmation_prompt(result["number"])
                logger.info(f"Confirmation requested: {confirmation_msg}")
                return confirmation_msg, self.state

            # Case B: Incomplete digits (user might be pausing in the middle)
            # If fewer than 10 digits, we wait up to INCOMPLETE_SILENCE_TIMEOUT (4 seconds)
            # so the user can finish saying the remainder (e.g. 5+5 or paused chunk).
            if result["digits"] > 0 and result["digits"] < 10:
                logger.info(
                    f"Partial digits detected ({result['digits']}/10). "
                    f"Waiting silently up to {INCOMPLETE_SILENCE_TIMEOUT}s for remainder..."
                )
                return None, self.state

            # Case C: Invalid starting digit or too many digits in the current stream
            if result["digits"] >= 10 and not result["success"]:
                # Clear buffer so user can start fresh
                self.accumulated_transcripts.clear()
                return prompts.INVALID_NUMBER, self.state

            # Case D: No digits detected at all (e.g. background chatter or general filler)
            if result["digits"] == 0:
                return prompts.UNCLEAR_AUDIO, self.state

        return None, self.state

    def handle_incomplete_timeout(self) -> Optional[str]:
        """
        Called when the ~4s pause timer expires and the number is still incomplete.
        Asks user to repeat their full number.
        """
        if self.state == DialogState.COLLECTING and self.accumulated_transcripts:
            full_transcript = " ".join(self.accumulated_transcripts)
            result = parse_phone_number(full_transcript)
            count = result["digits"]
            self.accumulated_transcripts.clear()
            if count > 0:
                return prompts.get_incomplete_prompt(count)
            return prompts.UNCLEAR_AUDIO
        return None

    async def _persist_phone_number(self) -> Tuple[bool, Optional[str]]:
        """
        Persist the validated phone record to the FastAPI backend.
        Uses POST /api/phone.
        """
        if not self.current_candidate_number:
            return False, "No phone number available to save"

        payload = {
            "rawTranscript": self.current_candidate_raw or self.current_candidate_number,
            "parsedNumber": self.current_candidate_number,
            "language": self.current_candidate_language or "en"
        }

        url = f"{self.backend_url}/api/phone"
        logger.info(f"Persisting phone to {url} with masked number {mask_number(self.current_candidate_number)}")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 201:
                    logger.info("Successfully persisted phone number to backend!")
                    return True, None
                else:
                    err = f"Backend returned status {resp.status_code}: {resp.text}"
                    logger.error(err)
                    return False, err
        except Exception as e:
            err = f"Failed to connect to backend at {url}: {e}"
            logger.error(err)
            return False, err
