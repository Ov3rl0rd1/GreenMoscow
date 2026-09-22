SURROGATE_ESCAPE = "surrogateescape"
REPLACE = "replace"
ENCODING = "utf-8"


def repaired_text(value: str) -> str:
    if _is_encodable(value, "strict"):
        return value
    if _is_encodable(value, SURROGATE_ESCAPE):
        return value.encode(ENCODING, SURROGATE_ESCAPE).decode(ENCODING, REPLACE)
    return value.encode(ENCODING, REPLACE).decode(ENCODING)


def _is_encodable(value: str, errors: str) -> bool:
    try:
        value.encode(ENCODING, errors)
    except UnicodeEncodeError:
        return False
    return True
