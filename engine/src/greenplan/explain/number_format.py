TEXT_DECIMALS = 2
STRUCTURE_DECIMALS = 3


def format_number(value: float) -> str:
    text = f"{round(value, TEXT_DECIMALS):.{TEXT_DECIMALS}f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text.replace(".", ",")


def structure_value(value: float) -> float:
    return round(value, STRUCTURE_DECIMALS)
