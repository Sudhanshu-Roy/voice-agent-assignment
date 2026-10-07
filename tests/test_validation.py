"""
Tests for validation rules, invalid phone numbers, incomplete numbers,
and confirmation intent detection.
"""

import pytest
from parser.phone_parser import (
    parse_phone_number,
    validate_indian_mobile_number,
    detect_confirmation
)


class TestPhoneValidation:
    """Tests edge cases and validation constraints."""

    def test_incomplete_number_three_digits(self):
        result = parse_phone_number("one two three")
        assert result["success"] is False
        assert result["number"] is None
        assert result["digits"] == 3
        assert "Incomplete" in result["reason"]

    def test_incomplete_nine_digits(self):
        result = parse_phone_number("987654321")
        assert result["success"] is False
        assert result["number"] is None
        assert result["digits"] == 9
        assert "Incomplete" in result["reason"]

    def test_too_many_digits_eleven(self):
        result = parse_phone_number("98765432101")
        assert result["success"] is False
        assert result["number"] is None
        assert result["digits"] == 11
        assert "Too many digits" in result["reason"]

    def test_invalid_starting_digit_five(self):
        # 5123456789 starts with 5
        result = parse_phone_number("five one two three four five six seven eight nine")
        assert result["success"] is False
        assert result["number"] is None
        assert result["digits"] == 10
        assert "must start with 6, 7, 8, or 9" in result["reason"]

    def test_invalid_starting_digit_numeric_five(self):
        result = parse_phone_number("5123456789")
        assert result["success"] is False
        assert "must start with 6, 7, 8, or 9" in result["reason"]

    def test_empty_transcript(self):
        result = parse_phone_number("")
        assert result["success"] is False
        assert result["digits"] == 0
        assert "Empty" in result["reason"]

    def test_whitespace_only(self):
        result = parse_phone_number("   \n\t  ")
        assert result["success"] is False
        assert result["digits"] == 0

    def test_no_digits_conversational_filler(self):
        result = parse_phone_number("hello what is your name can you hear me")
        assert result["success"] is False
        assert result["digits"] == 0
        assert "No phone number digits found" in result["reason"]

    def test_valid_starting_digits_6_7_8_9(self):
        # 6, 7, 8, 9 are all valid Indian mobile starting digits
        valid_starters = ["6123456789", "7123456789", "8123456789", "9123456789"]
        for num in valid_starters:
            is_valid, err = validate_indian_mobile_number(num)
            assert is_valid is True
            assert err is None

    def test_invalid_starting_digits_0_to_5(self):
        for starter in ["0", "1", "2", "3", "4", "5"]:
            num = f"{starter}123456789"
            is_valid, err = validate_indian_mobile_number(num)
            assert is_valid is False
            assert "must start with 6, 7, 8, or 9" in err


class TestConfirmationDetection:
    """Tests for deterministic confirmation / denial detection."""

    @pytest.mark.parametrize("affirmative", [
        "yes",
        "yeah",
        "yep",
        "correct",
        "right",
        "that's correct",
        "thats correct",
        "haan",
        "han",
        "sahi",
        "sahi hai",
        "bilkul",
        "yes that's right",
        "ji haan",
        "theek hai",
        "thik hai",
        "sure",
        "perfect",
        "yes please"
    ])
    def test_positive_confirmations(self, affirmative):
        assert detect_confirmation(affirmative) is True

    @pytest.mark.parametrize("negative", [
        "no",
        "wrong",
        "incorrect",
        "galat",
        "nahi",
        "nahin",
        "na",
        "nope",
        "not right",
        "galat hai",
        "no that is wrong",
        "try again"
    ])
    def test_negative_confirmations(self, negative):
        assert detect_confirmation(negative) is False

    def test_ambiguous_transcript(self):
        assert detect_confirmation("what did you say") is None
        assert detect_confirmation("") is None
        assert detect_confirmation("tell me again") is None
