"""India's 22 scheduled languages (+ English): scripts, voice support, and alphabets for the script trainer."""
import contextvars
import unicodedata

# code: (English name, native name, script, whisper code or None, speech tag)
LANGUAGES = {
    "en": ("English", "English", "Latin", "en", "en-IN"),
    "as": ("Assamese", "অসমীয়া", "Bengali–Assamese", "as", "as-IN"),
    "bn": ("Bengali", "বাংলা", "Bengali–Assamese", "bn", "bn-IN"),
    "brx": ("Bodo", "बड़ो", "Devanagari", None, "brx-IN"),
    "doi": ("Dogri", "डोगरी", "Devanagari", None, "doi-IN"),
    "gu": ("Gujarati", "ગુજરાતી", "Gujarati", "gu", "gu-IN"),
    "hi": ("Hindi", "हिन्दी", "Devanagari", "hi", "hi-IN"),
    "kn": ("Kannada", "ಕನ್ನಡ", "Kannada", "kn", "kn-IN"),
    "ks": ("Kashmiri", "کٲشُر", "Perso-Arabic", None, "ks-IN"),
    "kok": ("Konkani", "कोंकणी", "Devanagari", None, "kok-IN"),
    "mai": ("Maithili", "मैथिली", "Devanagari", None, "mai-IN"),
    "ml": ("Malayalam", "മലയാളം", "Malayalam", "ml", "ml-IN"),
    "mni": ("Manipuri", "ꯃꯤꯇꯩꯂꯣꯟ", "Meitei Mayek", None, "mni-IN"),
    "mr": ("Marathi", "मराठी", "Devanagari", "mr", "mr-IN"),
    "ne": ("Nepali", "नेपाली", "Devanagari", "ne", "ne-NP"),
    "or": ("Odia", "ଓଡ଼ିଆ", "Odia", None, "or-IN"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi", "pa", "pa-IN"),
    "sa": ("Sanskrit", "संस्कृतम्", "Devanagari", "sa", "sa-IN"),
    "sat": ("Santali", "ᱥᱟᱱᱛᱟᱲᱤ", "Ol Chiki", None, "sat-IN"),
    "sd": ("Sindhi", "سنڌي", "Perso-Arabic", "sd", "sd-IN"),
    "ta": ("Tamil", "தமிழ்", "Tamil", "ta", "ta-IN"),
    "te": ("Telugu", "తెలుగు", "Telugu", "te", "te-IN"),
    "ur": ("Urdu", "اردو", "Perso-Arabic", "ur", "ur-IN"),
}

# Unicode block of each script, for the alphabet trainer
SCRIPT_BLOCKS = {
    "Devanagari": (0x0900, 0x097F), "Bengali–Assamese": (0x0980, 0x09FF), "Gurmukhi": (0x0A00, 0x0A7F),
    "Gujarati": (0x0A80, 0x0AFF), "Odia": (0x0B00, 0x0B7F), "Tamil": (0x0B80, 0x0BFF), "Telugu": (0x0C00, 0x0C7F),
    "Kannada": (0x0C80, 0x0CFF), "Malayalam": (0x0D00, 0x0D7F), "Perso-Arabic": (0x0621, 0x06D3),
    "Ol Chiki": (0x1C50, 0x1C7F), "Meitei Mayek": (0xABC0, 0xABFF),
}
# The 39-letter Urdu alphabet, in order (also the base for Kashmiri and Sindhi practice)
URDU_ALPHABET = [0x0627, 0x0628, 0x067E, 0x062A, 0x0679, 0x062B, 0x062C, 0x0686, 0x062D, 0x062E, 0x062F, 0x0688, 0x0630,
                 0x0631, 0x0691, 0x0632, 0x0698, 0x0633, 0x0634, 0x0635, 0x0636, 0x0637, 0x0638, 0x0639, 0x063A, 0x0641,
                 0x0642, 0x06A9, 0x06AF, 0x0644, 0x0645, 0x0646, 0x06BA, 0x0648, 0x06C1, 0x06BE, 0x0621, 0x06CC, 0x06D2]
VOWELS = {"a", "aa", "i", "ii", "u", "uu", "e", "ee", "ai", "o", "oo", "au", "vocalic r", "vocalic rr", "ae", "aai", "aau"}

current_lang: contextvars.ContextVar[str] = contextvars.ContextVar("current_lang", default="")


def info(code: str) -> dict | None:
    l = LANGUAGES.get(code)
    if not l:
        return None
    return {"code": code, "name": l[0], "native": l[1], "script": l[2], "voice_in": bool(l[3]), "whisper": l[3], "tts": l[4]}


def all_languages() -> list[dict]:
    return [info(c) for c in LANGUAGES]


def instruction(code: str | None) -> str | None:
    """Prompt line telling the AI which language to answer in (None = let Krypton decide)."""
    l = LANGUAGES.get(code or "")
    if not l or code == "en":
        return "LANGUAGE: Write everything in English." if code == "en" else None
    name, native, script = l[0], l[1], l[2]
    return (f"LANGUAGE: Write everything in {name} ({native}), using the {script} script. "
            f"Keep scientific terms recognisable: add the English term in brackets the first time, e.g. term (photosynthesis).")


def alphabet(code: str) -> dict:
    l = info(code)
    if not l or l["script"] not in SCRIPT_BLOCKS:
        raise ValueError("No alphabet trainer for this language.")
    lo, hi = SCRIPT_BLOCKS[l["script"]]
    vowels, consonants = [], []
    if l["script"] == "Perso-Arabic":
        cps = URDU_ALPHABET
    elif l["script"] in ("Ol Chiki", "Meitei Mayek"):
        cps = range(lo, hi + 1)
    else:  # Indic blocks keep the standard letters at offsets 0x05-0x39
        cps = range(lo + 0x05, lo + 0x3A)
    for cp in cps:
        ch = chr(cp)
        name = unicodedata.name(ch, "")
        if " LETTER " not in name or unicodedata.category(ch) != "Lo":
            continue
        if any(w in name for w in ("VOCALIC L", "ARCHAIC", "VOCALIC RR", "SHORT ", "CANDRA", "VEDIC")):
            continue
        sound = name.split(" LETTER ", 1)[1].lower()
        item = {"char": ch, "sound": sound}
        (vowels if sound in VOWELS else consonants).append(item)
    if l["script"] in ("Perso-Arabic", "Ol Chiki", "Meitei Mayek"):  # these don't split vowels the Indic way
        consonants, vowels = vowels + consonants, []
    seen, uniq = set(), []
    for x in consonants:
        if x["char"] not in seen:
            seen.add(x["char"])
            uniq.append(x)
    return {**l, "vowels": vowels, "consonants": uniq}
