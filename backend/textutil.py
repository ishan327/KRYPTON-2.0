"""Small text helpers shared by ingest, retrieval and the offline engine."""
import re

WORD_RE = re.compile(r"[A-Za-z0-9ऀ-ॿ]+")
SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+(?=[A-Z0-9\"'(ऀ-ॿ])")

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further had has have having he her here
hers herself him himself his how i if in into is it its itself just let like made make many may me might more
most much must my myself no nor not now of off on once one only or other our ours ourselves out over own same
see she should so some such than that the their theirs them themselves then there these they this those
through to too two under until up upon us use used very was we were what when where which while who whom why
will with would you your yours yourself yourselves called known also figure fig activity page chapter
example given shown following let us do find write give state name three four five first second various
different important things thing way ways get gets got take takes many much often within without however thus
therefore around among another every still well even used using lot lots
""".split())


def tokenize(text: str) -> list[str]:
    return [w for w in (t.lower() for t in WORD_RE.findall(text)) if w not in STOPWORDS and len(w) > 1]


def clean_page(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or re.fullmatch(r"[\d\s\-–•|]+", s):
            continue
        if re.search(r"reprint\s+20\d\d|rationalised\s+20\d\d|not to be republished", s, re.I):
            continue
        lines.append(s)
    text = "\n".join(lines)
    text = re.sub(r"-\n(?=[a-z])", "", text)          # join hyphenated line breaks
    text = re.sub(r"(?<![.!?:।\n])\n(?=[a-z(])", " ", text)  # join wrapped lines
    return text


def sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in SENT_SPLIT.split(flat) if s.strip()]
