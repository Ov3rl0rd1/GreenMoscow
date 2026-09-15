import re

INVALID_CHARACTERS = re.compile(r"[^A-Z0-9_-]")
REPEATED_UNDERSCORES = re.compile(r"_{2,}")
SEPARATOR = "_"
FALLBACK_NAME = "UNNAMED"


class LayerNameSanitizer:
    def __init__(self, max_length: int) -> None:
        self._max_length = max_length

    def sanitize(self, name: str) -> str:
        cleaned = REPEATED_UNDERSCORES.sub(SEPARATOR, INVALID_CHARACTERS.sub(SEPARATOR, name.upper()))
        bounded = cleaned.strip(SEPARATOR)[: self._max_length].strip(SEPARATOR)
        return bounded or FALLBACK_NAME

    def join(self, *parts: str) -> str:
        return self.sanitize(SEPARATOR.join(part for part in parts if part))
