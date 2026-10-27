"""Speech cues in a transcript line, found with plain text rules.

These are prompts for the teacher's attention, not measures of understanding: no tone, emotion or speaker analysis.
"""
import re

# the same word may arrive with Arabic letters, a half-space, a plain space, or none
_NORMALIZE = str.maketrans({'ي': 'ی', 'ك': 'ک', 'ة': 'ه', '‌': ' ', 'ـ': None})


def normalize(text):
    return re.sub(r'\s+', ' ', text.translate(_NORMALIZE)).strip()


RULES = [
    ('confusion', r'متوجه نشدم|متوجه نمی ?شم|نفهمیدم|نمی ?فهمم|گیج|سردرگم|قاطی کردم|سخته|سخت است|درک نکردم'),
    ('repeat', r'دوباره|یه بار دیگه|یک بار دیگر|یکبار دیگه|تکرار کنید|تکرار می ?کنید|بلندتر'),
    ('example', r'مثال|نمونه بزن|نمونه ای بزن|یه نمونه'),
    ('topic', r'بریم سراغ|برویم سراغ|برگردیم سراغ|موضوع بعدی|مبحث بعدی|بحث بعدی|فصل بعد'),
]
QUESTION = r'[؟?]\s*$|^(چرا|چطور|چطوری|چگونه|آیا)\b|\b(چیه|چیست|چی میشه|چی می شه|یعنی چی)\b'


def detect(text):
    """[(kind, matched text)]; a plain question counts only when nothing more specific was found."""
    t = normalize(text)
    found = []
    for kind, pattern in RULES:
        m = re.search(pattern, t)
        if m:
            found.append((kind, m.group(0)))
    if not found:
        m = re.search(QUESTION, t)
        if m:
            found.append(('question', m.group(0).strip() or '؟'))
    return found
