"""Persian number formatting shared by analytics texts and templates."""
FA_DIGITS = str.maketrans('0123456789.', '۰۱۲۳۴۵۶۷۸۹٫')


def fa(value):
    return str(value).translate(FA_DIGITS)


def pct(x):
    # JS Math.round: halves round up, unlike Python's banker's rounding
    return fa(int(x * 100 + 0.5) if x >= 0 else -int(-x * 100 + 0.5)) + '٪'


def js_round(x):
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)
