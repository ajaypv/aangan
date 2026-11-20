"""Murf Falcon voices for Indian languages.

Picks come from Murf_Recommended_Indian_Voices.pdf; the voiceId and locale strings below are the exact values
returned by Murf's `GET /v1/speech/voices?model=FALCON` (verified), e.g. `en-IN-pooja` speaking locale `hi-LATN`.

Language mode (AANGAN_LANGUAGE_MODE): "english" (default) makes every member's voice speak `en-IN` and every
recogniser listen for `en-IN`; "native" uses each member's own language (Hindi, Hinglish or English).
"""

from . import languages
from .config import settings

# display name -> Murf voiceId (verified against the live voices list)
VOICE_IDS = {
    "pooja": "en-IN-pooja",
    "nikhil": "en-IN-nikhil",
    "anisha": "en-IN-anisha",
    "abhinav": "en-IN-abhinav",
    "rachna": "hi-IN-rachna",
    "pranav": "hi-IN-pranav",
    "prathamesh": "mr-IN-prathamesh",
}

# (locale, gender) -> recommended voice display names, best first (from the PDF)
RECOMMENDED = {
    ("hi-IN", "female"): ["Pooja", "Rachna"],
    ("hi-IN", "male"): ["Pranav", "Prathamesh"],
    ("hi-LATN", "female"): ["Pooja"],
    ("hi-LATN", "male"): ["Nikhil"],
    ("en-IN", "female"): ["Anisha"],
    ("en-IN", "male"): ["Abhinav"],
    # native mode, Telugu and Kannada: the multi-native Falcon voices
    ("te-IN", "female"): ["Rachna"],
    ("te-IN", "male"): ["Pranav"],
    ("kn-IN", "female"): ["Rachna"],
    ("kn-IN", "male"): ["Pranav"],
}

LANGUAGE_LOCALE = {"Hindi": "hi-IN", "Hinglish": "hi-LATN", "English": "en-IN", "Telugu": "te-IN", "Kannada": "kn-IN"}
FEMALE_WORDS = {"mom", "mother", "maa", "wife", "daughter", "sister", "grandmother", "dadi", "nani", "aunt", "girl", "baby girl"}
MALE_WORDS = {"dad", "father", "papa", "husband", "son", "brother", "grandfather", "dada", "nana", "uncle", "boy"}

# Deepgram nova-3 language codes used for Agora's speech recognition
ASR_LANGUAGE = {"Hindi": "hi", "Hinglish": "hi-Latn", "English": "en-IN", "Telugu": "te", "Kannada": "kn"}


def language_mode() -> str:
    return settings().language_mode


def effective_language(member: dict, mode: str | None = None) -> str:
    """The language Aangan speaks to and listens for from this member. In multi-language mode this is the language the
    call opens in (their own); after that the language follows what is said, turn by turn."""
    return "English" if (mode or language_mode()) == "english" else member.get("language", "Hinglish")


def infer_gender(member: dict) -> str:
    if member.get("gender") in ("female", "male"):
        return member["gender"]
    relation = member.get("relation", "").lower()
    if relation in FEMALE_WORDS:
        return "female"
    if relation in MALE_WORDS:
        return "male"
    return "female"


def voice_for(member: dict, mode: str | None = None) -> dict:
    """The voice Aangan uses when speaking to this member: their assigned voice, else the language/gender pick."""
    language = effective_language(member, mode)
    gender = infer_gender(member)
    if (mode or language_mode()) == "multi":
        # one multi-native Falcon voice speaks all four languages; the locale is what changes
        lang = languages.for_member(language)
        vid = languages.MULTI_VOICES[gender]
        return {"name": vid.split("-")[-1].title(), "voice_id": vid, "locale": lang.locale, "gender": gender, "language": lang.name}
    locale = LANGUAGE_LOCALE.get(language, "hi-LATN")
    name = member.get("voice_id") or RECOMMENDED[(locale, gender)][0]
    return {
        "name": name,
        "voice_id": VOICE_IDS.get(name.lower(), name),
        "locale": locale,
        "gender": gender,
        "language": language,
    }


def asr_language(member: dict, mode: str | None = None) -> str:
    if (mode or language_mode()) == "multi":
        return "multi"  # Deepgram nova-3 listens for English, Hindi, Telugu and Kannada at once and follows the speaker
    return ASR_LANGUAGE.get(effective_language(member, mode), "en-IN")
