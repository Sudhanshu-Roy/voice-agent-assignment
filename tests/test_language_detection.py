"""
Tests for deterministic language classification:
- English ('en')
- Hindi ('hi')
- Mixed / Hinglish ('mixed')
"""

import pytest
from parser.phone_parser import parse_phone_number
from parser.language import classify_tokens_language


class TestLanguageClassification:
    """Tests language detection on spoken and mixed phrases."""

    def test_english_digits_classified_en(self):
        result = parse_phone_number("nine eight seven six five four three two one zero")
        assert result["language"] == "en"

    def test_hindi_digits_classified_hi(self):
        result = parse_phone_number("nau aath saat chhe paanch chaar teen do ek shunya")
        assert result["language"] == "hi"

    def test_hindi_sifar_classified_hi(self):
        result = parse_phone_number("nau aath saat chhe paanch chaar teen do ek sifar")
        assert result["language"] == "hi"

    def test_hinglish_mixed_digits_classified_mixed(self):
        result = parse_phone_number("nine aath saat 6 5 chaar 3 2 1 zero")
        assert result["language"] == "mixed"

    def test_english_words_with_hindi_markers_classified_mixed(self):
        result = parse_phone_number("mera number hai nine eight seven six five four three two one zero")
        assert result["language"] == "mixed"

    def test_hindi_words_with_english_markers_classified_mixed(self):
        result = parse_phone_number("my phone is nau aath saat chhe paanch chaar teen do ek shunya")
        assert result["language"] == "mixed"

    def test_pure_digits_defaults_en(self):
        result = parse_phone_number("9876543210")
        assert result["language"] == "en"

    def test_pure_digits_with_hindi_context_classified_hi(self):
        result = parse_phone_number("mera number 9876543210 hai")
        assert result["language"] == "hi"
