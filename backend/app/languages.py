"""The four spoken languages Aangan understands and answers in: English, Hindi, Telugu and Kannada.

In multi-language mode the person simply talks. Speech recognition listens for all four at once (Deepgram nova-3 `multi`),
each message is read for its script here, the model is told which language to answer in, and the voice is told which Murf
locale to speak. The same Murf voice speaks all four: a handful of Falcon voices are multi-native, so only the locale changes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str  # in English, for the model
    native: str  # in its own script, for people
    locale: str  # Murf locale
    asr: str  # Deepgram language code
    script: str  # what the model must write in


LANGUAGES: dict[str, Language] = {
    "en": Language("en", "English", "English", "en-IN", "en-IN", "English"),
    "hi": Language("hi", "Hindi", "हिन्दी", "hi-IN", "hi", "Devanagari script"),
    "te": Language("te", "Telugu", "తెలుగు", "te-IN", "te", "Telugu script"),
    "kn": Language("kn", "Kannada", "ಕನ್ನಡ", "kn-IN", "kn", "Kannada script"),
}
BY_NAME = {lang.name: lang for lang in LANGUAGES.values()}

# Unicode blocks. Latin letters (English, and romanised Hindi typed in Latin) count as English.
_SCRIPTS = (("hi", 0x0900, 0x097F), ("te", 0x0C00, 0x0C7F), ("kn", 0x0C80, 0x0CFF))

# Murf Falcon voices that are multi-native: each one speaks English, Hindi, Telugu and Kannada (verified in Murf's live voices list).
MULTI_VOICES = {"female": "hi-IN-rachna", "male": "hi-IN-pranav"}


def detect(text: str) -> str:
    """The language of a message, from its script: Telugu, Kannada or Hindi letters win once they are a clear share of the letters."""
    counts = {code: 0 for code, _, _ in _SCRIPTS}
    letters = 0
    for ch in text:
        if not ch.isalpha():
            continue
        letters += 1
        point = ord(ch)
        for code, low, high in _SCRIPTS:
            if low <= point <= high:
                counts[code] += 1
                break
    if letters == 0:
        return "en"
    best = max(counts, key=lambda c: counts[c])
    return best if counts[best] / letters >= 0.3 else "en"


def for_member(language: str | None) -> Language:
    """A member's own language (their profile says English, Hindi, Hinglish, Telugu or Kannada) as one of the four."""
    if language in BY_NAME:
        return BY_NAME[language]
    return LANGUAGES["hi"] if language == "Hinglish" else LANGUAGES["en"]


# What the voice says while Aangan is still working: one short phrase per language, never a promise about the result.
HOLD = {"en": "One moment.", "hi": "एक पल रुकिए।", "te": "ఒక్క నిమిషం.", "kn": "ಒಂದು ನಿಮಿಷ."}
LOOKING = {"en": "Let me look that up.", "hi": "मैं अभी देखता हूँ।", "te": "ఒక్క నిమిషం, చూస్తున్నాను.", "kn": "ಒಂದು ನಿಮಿಷ, ನೋಡುತ್ತಿದ್ದೇನೆ."}
SORRY = {
    "en": "Sorry, I couldn't finish that. Please try again.",
    "hi": "माफ़ कीजिए, मैं यह पूरा नहीं कर पाया। कृपया दोबारा बोलिए।",
    "te": "క్షమించండి, నేను ఇది పూర్తి చేయలేకపోయాను. దయచేసి మళ్లీ చెప్పండి.",
    "kn": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಇದನ್ನು ಪೂರ್ಣಗೊಳಿಸಲು ಆಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ.",
}
GREETING = {
    "en": "Hello {name}, Aangan here. What can I do for the family today?",
    "hi": "नमस्ते {name}, मैं आँगन हूँ। आज मैं परिवार के लिए क्या करूँ?",
    "te": "నమస్కారం {name}, నేను ఆంగన్. ఈ రోజు కుటుంబానికి నేనేమి చేయగలను?",
    "kn": "ನಮಸ್ಕಾರ {name}, ನಾನು ಆಂಗನ್. ಇಂದು ಕುಟುಂಬಕ್ಕಾಗಿ ನಾನು ಏನು ಮಾಡಲಿ?",
}
FAILURE = {
    "en": "One moment, could you say that again?",
    "hi": "एक सेकंड, क्या आप दोबारा बोलेंगे?",
    "te": "ఒక్క నిమిషం, మళ్లీ చెప్పగలరా?",
    "kn": "ಒಂದು ನಿಮಿಷ, ಮತ್ತೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?",
}


def tts_params(code: str, gender: str) -> dict:
    """The Murf settings for one reply, sent to Agora ahead of the text (Murf's REST names: voiceId and locale)."""
    return {"voiceId": MULTI_VOICES.get(gender, MULTI_VOICES["female"]), "locale": LANGUAGES[code].locale}
