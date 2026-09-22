from greenplan.domain.text_repair import repaired_text

BROKEN_CYRILLIC_X = "смотровы\udcd1\udc85 колодцах"
UNPAIRED_HIGH_SURROGATE = "метка\ud83d"


def test_clean_text_is_returned_unchanged() -> None:
    assert repaired_text("Смотровой колодец №12") == "Смотровой колодец №12"


def test_bytes_kept_as_surrogates_are_decoded_back() -> None:
    assert repaired_text(BROKEN_CYRILLIC_X) == "смотровых колодцах"


def test_undecodable_surrogate_is_replaced_instead_of_raising() -> None:
    result = repaired_text(UNPAIRED_HIGH_SURROGATE)
    assert result.startswith("метка")
    result.encode("utf-8")


def test_result_is_always_encodable() -> None:
    for value in ("обычный текст", BROKEN_CYRILLIC_X, UNPAIRED_HIGH_SURROGATE, ""):
        repaired_text(value).encode("utf-8")
