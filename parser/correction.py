"""
Deterministic correction detection and resolution module.
Handles speech self-corrections such as:
- 'nine eight seven wait sorry nine eight six seven five four three two one zero'
- 'nine eight seven — no — nine eight six seven...'
- 'nau aath saat nahi nau aath chhe saat...'
"""

import re
from typing import List, Tuple, Set

# Markers indicating correction intent
CORRECTION_KEYWORDS: Set[str] = {
    "sorry", "wait", "actually", "correction", "scratch that",
    "i mean", "my bad", "wrong", "mistake",
    # Hindi markers
    "nahi", "nahin", "ruko", "galat", "arre nahi", "arrey nahi"
}

# Regex to detect phrases like 'i mean', 'scratch that', 'wait sorry'
CORRECTION_PHRASE_PATTERNS = [
    r"\bwait\s+sorry\b",
    r"\bscratch\s+that\b",
    r"\bi\s+mean\b",
    r"\bmy\s+bad\b",
    r"\bcorrect\s+that\b",
    r"\bno\s+no\b",
    r"\bhold\s+on\b",
    r"\barre\s+nahi\b",
    r"\barrey\s+nahi\b",
]


def is_correction_token(token: str, prev_token: str = "", next_token: str = "") -> bool:
    """
    Check if a token represents a self-correction marker.
    Special handling for 'no' to ensure we do not over-trigger on normal use.
    """
    cleaned = token.lower().strip(".,!?-—_")
    if cleaned in CORRECTION_KEYWORDS:
        return True

    # Treat "no" as a correction only when it sits between other tokens
    # (e.g. "seven — no — eight"), not when it is the whole utterance.
    if cleaned == "no" and prev_token and next_token:
        return True

    return False


def split_transcript_by_corrections(raw_text: str) -> List[str]:
    """
    Splits a transcript into candidate segments separated by correction markers.
    Handles em-dashes, hyphens, and correction keywords.
    Returns segments in chronological order.
    """
    # Replace em-dashes and strong pauses used with 'no' or corrections
    normalized = raw_text.replace("—", " - ").replace("–", " - ")

    # Normalize known multi-word correction phrases to a unified marker
    for pattern in CORRECTION_PHRASE_PATTERNS:
        normalized = re.sub(pattern, " __CORRECTION__ ", normalized, flags=re.IGNORECASE)

    # Replace single correction words surrounded by word boundaries
    tokens = normalized.split()
    segments: List[List[str]] = [[]]

    for i, tok in enumerate(tokens):
        prev_tok = tokens[i - 1] if i > 0 else ""
        next_tok = tokens[i + 1] if i + 1 < len(tokens) else ""
        
        # Strip punctuation for inspection
        clean_tok = tok.strip(".,!?;:\"'()[]{}").lower()
        
        if clean_tok == "__correction__" or is_correction_token(clean_tok, prev_tok, next_tok):
            # Start a new segment if current segment has content
            if segments[-1]:
                segments.append([])
        else:
            segments[-1].append(tok)

    result_segments = [" ".join(seg).strip() for seg in segments if seg]
    return result_segments if result_segments else [raw_text]
