"""Turn Devanagari speech-recognition output into the romanised Hinglish the rule engine understands.

Agora's speech recogniser may return Hindi in Devanagari. Agents match romanised keywords, so known words are
mapped here; unknown Devanagari is left as is (the Claude brain reads Devanagari natively).
"""

import re

# multi-word phrases first, then single words
PHRASES = {
    "कर दो": "kar do", "कर दीजिए": "kar do", "कर दीजिये": "kar do", "बुक कर": "book kar", "ले ली": "le li",
    "ले लिया": "le li", "पहुंच गया": "pahunch gaya", "पहुँच गया": "pahunch gaya", "पहुंच गई": "pahunch gayi",
    "खत्म हो रही": "khatam ho rahi", "बाहर जाना": "bahar jaana", "बाहर जाने": "bahar jaane", "बाहर खाना": "bahar khana",
    "सब के साथ": "sab ke saath", "सबके साथ": "sab ke saath", "सबसे साथ": "sab saath", "हम सब": "hum sab",
    "कैसा चल रहा": "kaisa chal raha", "कैसी चल रही": "kaisi chal rahi",
}

WORDS = {
    # yes / no / generic verbs
    "हां": "haan", "हाँ": "haan", "हा": "haan", "ठीक": "theek", "नहीं": "nahi", "नही": "nahi", "रुको": "ruko",
    "कर": "kar", "करो": "karo", "करना": "karna", "दो": "do", "दीजिए": "do", "बुक": "book", "चाहिए": "chahiye",
    "है": "hai", "हैं": "hain", "हूं": "hoon", "हूँ": "hoon", "था": "tha", "गया": "gaya", "गई": "gayi", "गयी": "gayi",
    "जाना": "jaana", "जाने": "jaane", "जाएंगे": "jayenge", "जायेंगे": "jayenge", "आना": "aana",
    "दिखाओ": "dikhao", "बताओ": "batao", "बताइए": "batao", "ढूंढो": "dhundo", "देखो": "dekho", "खोजो": "dhundo",
    # people
    "सब": "sab", "सभी": "sabhi", "साथ": "saath", "के": "ke", "को": "ko", "में": "mein", "मे": "me", "से": "se",
    "पर": "par", "पे": "pe", "का": "ka", "की": "ki", "तक": "tak", "भी": "bhi", "और": "aur", "या": "ya", "तो": "to",
    "परिवार": "family", "फैमिली": "family", "दादी": "dadi", "पापा": "papa", "मम्मी": "mom", "माँ": "maa",
    "बेटा": "beta", "बेटी": "beti", "आरव": "aarav", "प्रिया": "priya", "राहुल": "rahul", "भाई": "bhai",
    # time
    "आज": "aaj", "कल": "kal", "परसों": "parso", "सुबह": "subah", "शाम": "shaam", "रात": "raat", "बजे": "baje",
    "रविवार": "sunday", "सोमवार": "monday", "मंगलवार": "tuesday", "बुधवार": "wednesday", "गुरुवार": "thursday",
    "शुक्रवार": "friday", "शनिवार": "saturday", "संडे": "sunday", "मंडे": "monday",
    # food / outing
    "बाहर": "bahar", "खाना": "khana", "खाने": "khaane", "लंच": "lunch", "डिनर": "dinner", "नाश्ता": "breakfast",
    "रेस्टोरेंट": "restaurant", "रेस्तरां": "restaurant", "रेस्टोरेन्ट": "restaurant", "टेबल": "table", "होटल": "hotel",
    "पसंद": "pasand", "एलर्जी": "allergy",
    # health / care
    "दवाई": "dawai", "दवा": "dawa", "दवाइयां": "dawai", "गोली": "tablet", "टैबलेट": "tablet", "डॉक्टर": "doctor",
    "अपॉइंटमेंट": "appointment", "खत्म": "khatam", "तबियत": "tabiyat", "चक्कर": "chakkar", "बीपी": "bp", "शुगर": "sugar",
    # school
    "स्कूल": "school", "पहुंच": "pahunch", "पहुँच": "pahunch", "मार्क्स": "marks", "नंबर": "marks", "मैथ्स": "maths",
    "गणित": "maths", "साइंस": "science", "इंग्लिश": "english", "होमवर्क": "homework", "टेस्ट": "test", "रिजल्ट": "result",
    "पढ़ाई": "padhai", "मिला": "mila", "मिले": "mile", "में से": "out of",
    # travel / calendar
    "फ्लाइट": "flight", "कैब": "cab", "टैक्सी": "taxi", "एयरपोर्ट": "airport", "टिकट": "ticket", "लेट": "late",
    "देरी": "delay", "डिले": "delay", "गोवा": "goa", "दिल्ली": "delhi", "कैलेंडर": "calendar", "शेड्यूल": "schedule",
    "फ्री": "free", "कब": "kab", "कौन": "kaun", "कितने": "kitne", "लोग": "log", "मीटिंग": "meeting", "याद": "yaad",
    "रखना": "rakhna", "जोड़ो": "add", "ऐड": "add", "क्लैश": "clash", "कैसा": "kaisa", "कैसी": "kaisi", "क्या": "kya",
    "विंडो": "window", "सीट": "seat", "सस्ती": "sasti", "बजट": "budget",
}

_DEVANAGARI = re.compile(r"[ऀ-ॿ]+")


def has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def normalize(text: str) -> str:
    """Romanise known Devanagari words and phrases; text without Devanagari is returned unchanged."""
    if not has_devanagari(text):
        return text
    for phrase, roman in sorted(PHRASES.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(phrase, f" {roman} ")
    text = _DEVANAGARI.sub(lambda m: f" {WORDS.get(m.group(0), m.group(0))} ", text)
    return re.sub(r"\s+", " ", text).strip()
