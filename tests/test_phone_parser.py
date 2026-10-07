"""
Comprehensive tests for the deterministic phone number parser.
Tests English, Hindi, Hinglish, repetitions, groupings, punctuation,
and edge cases.
"""

import pytest
from parser.phone_parser import parse_phone_number, parsePhoneNumber, format_digits_for_speech


class TestDeterministicPhoneParser:
    """Core parser test suite covering all mandatory assignment scenarios."""

    def test_english_digits_spaced(self):
        result = parse_phone_number("nine eight seven six five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9876543210"
        assert result["digits"] == 10
        assert result["language"] == "en"

    def test_numeric_spaced_single_digits(self):
        result = parse_phone_number("9 8 7 6 5 4 3 2 1 0")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_pairs_grouping(self):
        result = parse_phone_number("98 76 54 32 10")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_triplet_grouping(self):
        result = parse_phone_number("987 654 321 0")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_five_plus_five_grouping(self):
        result = parse_phone_number("98765 43210")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_full_number_compact(self):
        result = parse_phone_number("9876543210")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_hindi_digits_shunya(self):
        result = parse_phone_number("nau aath saat chhe paanch chaar teen do ek shunya")
        assert result["success"] is True
        assert result["number"] == "9876543210"
        assert result["language"] == "hi"

    def test_hindi_digits_sifar(self):
        result = parse_phone_number("nau aath saat chhe paanch chaar teen do ek sifar")
        assert result["success"] is True
        assert result["number"] == "9876543210"
        assert result["language"] == "hi"

    def test_hindi_phonetic_variants(self):
        # Variants: sunya, ik, doh, tin, ath, nav
        result = parse_phone_number("nav ath sat cheh panch char tin doh ik sunya")
        assert result["success"] is True
        assert result["number"] == "9876543210"
        assert result["language"] == "hi"

    def test_hinglish_mixed_speech(self):
        result = parse_phone_number("nine aath saat 6 5 chaar 3 2 1 zero")
        assert result["success"] is True
        assert result["number"] == "9876543210"
        assert result["language"] == "mixed"

    def test_english_with_oh_as_zero(self):
        result = parse_phone_number("nine eight seven six five four three two one oh")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_double_repetition(self):
        result = parse_phone_number("nine double seven six five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9776543210"

    def test_triple_repetition(self):
        result = parse_phone_number("nine triple eight five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9888543210"

    def test_quadruple_repetition(self):
        result = parse_phone_number("nine quadruple eight four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9888843210"

    def test_double_with_numeric_digits(self):
        result = parse_phone_number("nine double 7 six 5 4 3 2 1 0")
        assert result["success"] is True
        assert result["number"] == "9776543210"

    def test_punctuation_and_whitespace(self):
        result = parse_phone_number("  98-765.43210!  ")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_spoken_compound_words(self):
        # "ninety eight seventy six fifty four thirty two ten"
        result = parse_phone_number("ninety eight seventy six fifty four thirty two ten")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_country_code_plus_91_prefix(self):
        result = parse_phone_number("+91 98765 43210")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_country_code_spoken_plus_nine_one(self):
        result = parse_phone_number("plus nine one nine eight seven six five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_leading_zero_prefix(self):
        result = parse_phone_number("09876543210")
        assert result["success"] is True
        assert result["number"] == "9876543210"

    def test_self_correction_wait_sorry(self):
        # "nine eight seven wait sorry nine eight six seven five four three two one zero"
        result = parse_phone_number("nine eight seven wait sorry nine eight six seven five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9867543210"

    def test_self_correction_with_dashes_no(self):
        # "nine eight seven — no — nine eight six seven five four three two one zero"
        result = parse_phone_number("nine eight seven — no — nine eight six seven five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9867543210"

    def test_self_correction_no_no(self):
        result = parse_phone_number("nine eight seven no no nine eight six seven five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9867543210"

    def test_self_correction_i_mean(self):
        result = parse_phone_number("nine eight seven I mean nine eight six seven five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9867543210"

    def test_self_correction_actually(self):
        result = parse_phone_number("nine eight seven actually nine eight six seven five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9867543210"

    def test_self_correction_correct_that(self):
        result = parse_phone_number("nine eight seven correct that nine eight six seven five four three two one zero")
        assert result["success"] is True
        assert result["number"] == "9867543210"

    def test_parse_phone_number_camel_case_alias(self):
        # Verify parsePhoneNumber alias works identically
        res = parsePhoneNumber("9876543210")
        assert res["success"] is True
        assert res["number"] == "9876543210"

    def test_format_digits_for_speech(self):
        formatted = format_digits_for_speech("9876543210")
        assert formatted == "9, 8, 7, 6, 5, 4, 3, 2, 1, 0"
