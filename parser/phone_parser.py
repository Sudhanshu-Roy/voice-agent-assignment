"""
parsePhoneNumber — maps spoken English / Hindi / Hinglish transcripts
to a validated 10-digit Indian mobile number. No LLM involved.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict

from parser.language import (
    ENGLISH_DIGIT_WORDS,
    HINDI_DIGIT_WORDS,
    classify_tokens_language
)
from parser.correction import split_transcript_by_corrections

# Map of single digit words to string digit
DIGIT_WORDS_MAP: Dict[str, str] = {
    # English digits
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    # Hindi digits & common variants
    "shunya": "0",
    "sunya": "0",
    "sifar": "0",
    "sifir": "0",
    "shoony": "0",
    "shunyaa": "0",
    "ek": "1",
    "ik": "1",
    "do": "2",
    "doh": "2",
    "teen": "3",
    "tin": "3",
    "char": "4",
    "chaar": "4",
    "paanch": "5",
    "panch": "5",
    "cheh": "6",
    "chhe": "6",
    "chhah": "6",
    "che": "6",
    "saat": "7",
    "sat": "7",
    "aath": "8",
    "ath": "8",
    "nau": "9",
    "nav": "9",
}

# Repetition indicators
REPETITION_MULTIPLIERS: Dict[str, int] = {
    "double": 2,
    "triple": 3,
    "quadruple": 4,
}

# English tens words
TENS_MAP: Dict[str, str] = {
    "twenty": "2",
    "thirty": "3",
    "forty": "4",
    "fourty": "4",
    "fifty": "5",
    "sixty": "6",
    "seventy": "7",
    "eighty": "8",
    "ninety": "9",
}

# English teens and ten
TEENS_MAP: Dict[str, str] = {
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
}

# Confirmation indicators
CONFIRMATION_AFFIRMATIVE = {
    "yes", "yeah", "yep", "correct", "right", "that's correct", "thats correct",
    "haan", "han", "sahi", "sahi hai", "bilkul", "yes that's right", "sure",
    "ji haan", "theek hai", "thik hai", "it is correct", "perfect", "okay", "ok"
}

CONFIRMATION_NEGATIVE = {
    "no", "wrong", "incorrect", "galat", "nahi", "nahin", "na", "nope",
    "not right", "galat hai", "change", "try again", "no that is wrong"
}


@dataclass
class ParsedPhoneResult:
    success: bool
    number: Optional[str]
    language: str
    digits: int
    reason: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_transcript(text: str) -> str:
    """
    Standardize text: lowercase, normalize punctuation, em-dashes, and spacing.
    """
    if not text:
        return ""
    # Normalize unicode quotes and dashes
    t = text.lower().replace("—", " ").replace("–", " ").replace("-", " ")
    # Replace punctuation characters with whitespace, keeping alphanumeric characters
    t = re.sub(r"[^\w\s]", " ", t)
    # Collapse multiple whitespaces
    return re.sub(r"\s+", " ", t).strip()


def expand_repetitions(tokens: List[str]) -> List[str]:
    """
    Deterministically expand repetition tokens:
    e.g. ['double', 'seven'] -> ['seven', 'seven']
    e.g. ['triple', '9'] -> ['9', '9', '9']
    """
    expanded: List[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in REPETITION_MULTIPLIERS and i + 1 < n:
            mult = REPETITION_MULTIPLIERS[tok]
            next_tok = tokens[i + 1]
            # Verify next_tok is a recognizable digit word or digit string
            if next_tok in DIGIT_WORDS_MAP or next_tok.isdigit():
                for _ in range(mult):
                    expanded.append(next_tok)
                i += 2
                continue
        expanded.append(tok)
        i += 1
    return expanded


def extract_digits_from_segment(raw_segment: str) -> Tuple[List[str], bool, bool]:
    """
    Extracts individual digit characters from a normalized text segment.
    Returns:
    - digits: List of single-character string digits ['9', '8', ...]
    - has_en: Whether any English digit word was encountered
    - has_hi: Whether any Hindi digit word was encountered
    """
    normalized = normalize_transcript(raw_segment)
    tokens = normalized.split()
    expanded_tokens = expand_repetitions(tokens)

    digits: List[str] = []
    has_en = False
    has_hi = False

    i = 0
    total = len(expanded_tokens)
    while i < total:
        tok = expanded_tokens[i]

        # 1. Direct digits (e.g., '98765', '43210', '9')
        if tok.isdigit():
            for d in tok:
                digits.append(d)
            i += 1
            continue

        # 2. Known digit words (English & Hindi)
        if tok in DIGIT_WORDS_MAP:
            digit_char = DIGIT_WORDS_MAP[tok]
            digits.append(digit_char)
            if tok in ENGLISH_DIGIT_WORDS:
                has_en = True
            elif tok in HINDI_DIGIT_WORDS:
                has_hi = True
            i += 1
            continue

        # 3. Teens mapping ('ten' -> '10', 'eleven' -> '11', etc.)
        if tok in TEENS_MAP:
            val = TEENS_MAP[tok]
            digits.extend(list(val))
            has_en = True
            i += 1
            continue

        # 4. Tens mapping ('twenty', 'thirty', ..., 'ninety')
        if tok in TENS_MAP:
            ten_lead = TENS_MAP[tok]
            # Check if next token is a unit digit (1-9)
            if i + 1 < total:
                next_tok = expanded_tokens[i + 1]
                if next_tok in DIGIT_WORDS_MAP:
                    unit_char = DIGIT_WORDS_MAP[next_tok]
                    if unit_char != "0":
                        digits.append(ten_lead)
                        digits.append(unit_char)
                        has_en = True
                        if next_tok in ENGLISH_DIGIT_WORDS:
                            has_en = True
                        elif next_tok in HINDI_DIGIT_WORDS:
                            has_hi = True
                        i += 2
                        continue
                elif next_tok.isdigit() and len(next_tok) == 1 and next_tok != "0":
                    digits.append(ten_lead)
                    digits.append(next_tok)
                    has_en = True
                    i += 2
                    continue
            # If standalone tens word (e.g. 'twenty' alone -> 2, 0)
            digits.append(ten_lead)
            digits.append("0")
            has_en = True
            i += 1
            continue

        # Non-digit word / filler token
        i += 1

    return digits, has_en, has_hi


def clean_indian_phone_digits(digits: List[str]) -> List[str]:
    """
    Cleans leading country code prefixes if present:
    - 12 digits starting with '91' followed by [6-9] -> strips '91'
    - 11 digits starting with '0' followed by [6-9] -> strips '0'
    """
    if len(digits) == 12 and digits[0] == "9" and digits[1] == "1" and digits[2] in {"6", "7", "8", "9"}:
        return digits[2:]
    if len(digits) == 11 and digits[0] == "0" and digits[1] in {"6", "7", "8", "9"}:
        return digits[1:]
    return digits


def validate_indian_mobile_number(digit_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that digit_str conforms to the Indian mobile number specification:
    - Exactly 10 digits
    - Starts with 6, 7, 8, or 9
    """
    if len(digit_str) != 10:
        if len(digit_str) < 10:
            return False, f"Incomplete phone number: expected 10 digits, got {len(digit_str)}"
        return False, f"Too many digits: expected 10 digits, got {len(digit_str)}"

    if digit_str[0] not in {"6", "7", "8", "9"}:
        return False, f"Invalid mobile number: Indian mobile numbers must start with 6, 7, 8, or 9 (got '{digit_str[0]}')"

    return True, None


def parse_phone_number(transcript: str) -> Dict[str, Any]:
    """
    Deterministically parses a spoken or typed transcript into a structured phone result.
    Pipeline:
    1. Normalization & Correction Splitting
    2. Candidate Segment Evaluation
    3. Tokenization & Repetition Expansion
    4. Digit Extraction & Country-Code Stripping
    5. Language Classification
    6. Indian Mobile Number Validation
    7. Return structured dictionary
    """
    if not transcript or not transcript.strip():
        return ParsedPhoneResult(
            success=False,
            number=None,
            language="en",
            digits=0,
            reason="Empty transcript: no phone number provided"
        ).to_dict()

    # Split on correction markers
    segments = split_transcript_by_corrections(transcript)

    best_digits: List[str] = []
    has_en_total = False
    has_hi_total = False

    # Process segments from newest to oldest (self-correction prioritizes newest complete attempt)
    for seg in reversed(segments):
        d_list, seg_en, seg_hi = extract_digits_from_segment(seg)
        d_list = clean_indian_phone_digits(d_list)

        if seg_en:
            has_en_total = True
        if seg_hi:
            has_hi_total = True

        if len(d_list) == 10 and d_list[0] in {"6", "7", "8", "9"}:
            best_digits = d_list
            break
        elif len(d_list) > 10:
            # Over-length sequence (e.g. 11 digits like '98765432101') should not be silently sliced
            best_digits = d_list
            break

    # If no single segment yielded a full number, evaluate all segments combined
    if not best_digits:
        combined_digits, c_en, c_hi = extract_digits_from_segment(transcript)
        combined_digits = clean_indian_phone_digits(combined_digits)
        if c_en:
            has_en_total = True
        if c_hi:
            has_hi_total = True
        best_digits = combined_digits

    # Language classification
    all_tokens = normalize_transcript(transcript).split()
    detected_lang = classify_tokens_language(
        all_tokens,
        has_english_digits=has_en_total,
        has_hindi_digits=has_hi_total
    )

    digit_str = "".join(best_digits)
    count = len(digit_str)

    if count == 0:
        return ParsedPhoneResult(
            success=False,
            number=None,
            language=detected_lang,
            digits=0,
            reason="No phone number digits found in transcript"
        ).to_dict()

    is_valid, error_reason = validate_indian_mobile_number(digit_str)

    if is_valid:
        return ParsedPhoneResult(
            success=True,
            number=digit_str,
            language=detected_lang,
            digits=10,
            reason=None
        ).to_dict()

    return ParsedPhoneResult(
        success=False,
        number=None,
        language=detected_lang,
        digits=count,
        reason=error_reason
    ).to_dict()


# Alias for explicit assignment specification
parsePhoneNumber = parse_phone_number


def detect_confirmation(transcript: str) -> Optional[bool]:
    """
    Deterministically detects whether the user confirmed or denied a phone number.
    Returns:
    - True for affirmative ('yes', 'haan', 'sahi hai', 'bilkul', etc.)
    - False for negative ('no', 'nahi', 'galat', 'wrong', etc.)
    - None if unrecognized / ambiguous
    """
    if not transcript:
        return None

    cleaned = normalize_transcript(transcript)
    words = set(cleaned.split())

    # Exact phrase matching
    if any(phrase in cleaned for phrase in [
        "that s correct", "thats correct", "yes that s right", "yes thats right",
        "sahi hai", "theek hai", "thik hai", "ji haan", "it is correct", "bilkul sahi"
    ]):
        return True

    if any(phrase in cleaned for phrase in [
        "not right", "galat hai", "try again", "no that is wrong", "that is wrong"
    ]):
        return False

    # Check negative words first to avoid false positives (e.g. 'no, not right')
    if words.intersection(CONFIRMATION_NEGATIVE):
        return False

    # Check affirmative words
    if words.intersection(CONFIRMATION_AFFIRMATIVE):
        return True

    return None


def format_digits_for_speech(number: str) -> str:
    """
    Formats a 10-digit number to be spoken digit-by-digit:
    e.g. '9876543210' -> '9, 8, 7, 6, 5, 4, 3, 2, 1, 0'
    Ensures TTS never pronounces it as a billion/million.
    """
    return ", ".join(list(number))
