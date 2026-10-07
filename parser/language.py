"""
Language detection module for multilingual phone number parsing.
Supports English, Hindi, and Hinglish / mixed language classification.
"""

from typing import Set, List, Tuple

# Word sets for English digits and common fillers
ENGLISH_DIGIT_WORDS: Set[str] = {
    "zero", "oh", "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine"
}

ENGLISH_COMPOUND_WORDS: Set[str] = {
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    "thirty", "forty", "fourty", "fifty", "sixty", "seventy",
    "eighty", "ninety"
}

# Neutral domain words common in both Hindi and English speech
NEUTRAL_DOMAIN_WORDS: Set[str] = {
    "number", "mobile", "phone", "contact"
}

ENGLISH_MARKERS: Set[str] = {
    "double", "triple", "quadruple",
    "my", "is", "it", "sorry", "wait", "actually", "correct",
    "correction", "please", "yes", "yeah", "right"
}

# Word sets for Hindi digits and common phonetic variants
HINDI_DIGIT_WORDS: Set[str] = {
    # 0
    "shunya", "sunya", "sifar", "sifir", "shoony", "shunyaa",
    # 1
    "ek", "ik",
    # 2
    "do", "doh",
    # 3
    "teen", "tin",
    # 4
    "char", "chaar",
    # 5
    "paanch", "panch",
    # 6
    "cheh", "chhe", "chhah", "che",
    # 7
    "saat", "sat",
    # 8
    "aath", "ath",
    # 9
    "nau", "nav"
}

HINDI_MARKERS: Set[str] = {
    "nahi", "nahin", "ruko", "galat", "sahi", "haan", "han",
    "mera", "meri", "hai", "karo", "aur", "bilkul", "theek",
    "thik", "shukriya", "dhyanyawad", "ji"
}


def classify_tokens_language(
    tokens: List[str],
    has_english_digits: bool = False,
    has_hindi_digits: bool = False
) -> str:
    """
    Deterministically classify the language of the transcript into:
    - 'en' (English)
    - 'hi' (Hindi)
    - 'mixed' (Hinglish / mixed English & Hindi)

    Classification rules:
    1. If digit tokens contain both English and Hindi digit words -> 'mixed'
    2. If digit tokens contain Hindi and non-digit tokens contain English (or vice versa) -> 'mixed'
    3. If only Hindi words are observed -> 'hi'
    4. If only English words (or numeric digits + English) are observed -> 'en'
    5. Pure numeric digits default to 'en' unless Hindi context words are found.
    """
    found_en = has_english_digits
    found_hi = has_hindi_digits

    for tok in tokens:
        t = tok.lower()
        if t in ENGLISH_DIGIT_WORDS or t in ENGLISH_COMPOUND_WORDS or t in ENGLISH_MARKERS:
            found_en = True
        elif t in HINDI_DIGIT_WORDS or t in HINDI_MARKERS:
            found_hi = True

    if found_en and found_hi:
        return "mixed"
    if found_hi and not found_en:
        return "hi"
    return "en"
