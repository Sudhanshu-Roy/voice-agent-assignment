"""
Spoken prompts and dialogue templates for VAIU AI Phone Agent.
Designed for clear, natural, and friendly voice interaction.
"""

from parser.phone_parser import format_digits_for_speech

GREETING = "Hello! Please tell me your 10-digit mobile number."

INVALID_NUMBER = "That doesn't look like a valid mobile number. Indian mobile numbers must be 10 digits starting with 6, 7, 8, or 9. Please try again."

UNCLEAR_AUDIO = "I couldn't hear that clearly. Could you please repeat your 10-digit mobile number?"

SAVED_SUCCESS = "Thank you! Your mobile number has been saved successfully."

DENIED_RETRY = "Okay, let's try again. Please tell me your full 10-digit mobile number."

AMBIGUOUS_CONFIRMATION = "I didn't catch that clearly. Please say yes if the number is correct, or no to repeat."


def get_incomplete_prompt(digit_count: int) -> str:
    """Prompt spoken when user recited fewer than 10 digits after timeout."""
    if digit_count == 1:
        return "I only got 1 digit. Could you please repeat your full 10-digit mobile number?"
    return f"I only got {digit_count} digits. Could you please repeat your full 10-digit mobile number?"


def get_confirmation_prompt(phone_number: str) -> str:
    """
    CRITICAL: Never read back the phone number as a large number.
    Always read digit-by-digit with clear commas for TTS pacing.
    Example: 'Let me confirm — your number is 9, 8, 7, 6, 5, 4, 3, 2, 1, 0. Is that correct?'
    """
    digits_spoken = format_digits_for_speech(phone_number)
    return f"Let me confirm — your number is {digits_spoken}. Is that correct?"
