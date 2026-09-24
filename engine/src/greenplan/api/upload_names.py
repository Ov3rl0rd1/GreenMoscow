from email.errors import HeaderParseError
from email.header import decode_header, make_header
from pathlib import PureWindowsPath

ENCODED_WORD_MARKER = "=?"


def upload_file_name(raw: str) -> str:
    return PureWindowsPath(decoded_header_text(raw.strip())).name


def decoded_header_text(text: str) -> str:
    if ENCODED_WORD_MARKER not in text:
        return text
    try:
        return str(make_header(decode_header(text)))
    except (HeaderParseError, LookupError, UnicodeError):
        return text
