"""Spoken prompts used by the phone collection agent."""

from parser.phone_parser import format_digits_for_speech

GREETING = "Hello! Please tell me your 10-digit mobile number."

INVALID_NUMBER = (
    "That doesn't look like a valid mobile number. "
    "Please try again."
)

UNCLEAR_AUDIO = (
    "I couldn't hear that clearly. "
    "Could you please repeat your 10-digit mobile number?"
)

SAVED_SUCCESS = "Thank you! Your number has been saved."

DENIED_RETRY = "Okay, let's try again. Please tell me your full 10-digit mobile number."

AMBIGUOUS_CONFIRMATION = (
    "I didn't catch that clearly. "
    "Please say yes if the number is correct, or no to repeat."
)


def get_incomplete_prompt(digit_count: int) -> str:
    """Ask the user to repeat when we timed out with fewer than 10 digits."""
    if digit_count == 1:
        return "I only got 1 digit. Could you please repeat your full 10-digit mobile number?"
    return (
        f"I only got {digit_count} digits. "
        "Could you please repeat your full 10-digit mobile number?"
    )


def get_confirmation_prompt(phone_number: str) -> str:
    """
    Read the number back digit by digit so TTS does not say it as a huge integer.
    Example: 'Let me confirm — your number is 9, 8, 7, 6, 5, 4, 3, 2, 1, 0. Is that correct?'
    """
    digits_spoken = format_digits_for_speech(phone_number)
    return f"Let me confirm - your number is {digits_spoken}. Is that correct?"
