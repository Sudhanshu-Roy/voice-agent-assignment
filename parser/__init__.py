"""
Parser package for VAIU AI Voice Agent Phone Number Collection.
"""

from parser.phone_parser import (
    parse_phone_number,
    parsePhoneNumber,
    ParsedPhoneResult,
    detect_confirmation,
    format_digits_for_speech,
    validate_indian_mobile_number,
)
from parser.language import classify_tokens_language
from parser.correction import split_transcript_by_corrections

__all__ = [
    "parse_phone_number",
    "parsePhoneNumber",
    "ParsedPhoneResult",
    "detect_confirmation",
    "format_digits_for_speech",
    "validate_indian_mobile_number",
    "classify_tokens_language",
    "split_transcript_by_corrections",
]
