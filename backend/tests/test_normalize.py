import pytest

from app import orchestrator
from app.normalize import has_devanagari, normalize
from app.state import FamilyState


def test_schedule_question_about_a_child_goes_to_the_calendar():
    state = FamilyState()
    orchestrator.converse(state, "rahul", "What is Aarav doing on Monday?")
    assert state.transcript[-1]["agent"] == "calendar"
    orchestrator.converse(state, "rahul", "How is Aarav doing in school?")
    assert state.transcript[-1]["agent"] == "school"


def test_everyone_free_reads_grammatically():
    state = FamilyState()
    reply = orchestrator.converse(state, "rahul", "When is everyone free on Sunday?")
    assert "everyone is free" in reply.lower()


def test_latin_text_is_untouched():
    assert normalize("Sunday ko sab saath bahar jaana hai") == "Sunday ko sab saath bahar jaana hai"
    assert not has_devanagari("hello")


def test_known_devanagari_words_are_romanised():
    assert normalize("Sunday को सब के साथ बाहर जाना है") == "Sunday ko sab ke saath bahar jaana hai"
    assert normalize("हां book कर दो") == "haan book kar do"
    assert normalize("मेरी दवाई खत्म हो रही है").split()[1:3] == ["dawai", "khatam"]


@pytest.mark.parametrize(
    "speech, member, agent",
    [
        ("Sunday को सब के साथ बाहर जाना है", "priya", "dining"),
        ("मैं स्कूल पहुंच गया", "aarav", "school"),
        ("आज मैथ्स में 42 out of 50 मिला", "aarav", "school"),
        ("मेरी दवाई खत्म हो रही है", "dadi", "care"),
        ("Sunday को सब कब फ्री हैं", "rahul", "calendar"),
    ],
)
def test_devanagari_speech_reaches_the_right_agent(speech, member, agent):
    state = FamilyState()
    orchestrator.converse(state, member, speech)
    assert state.transcript[-1]["agent"] == agent
    assert state.transcript[0]["text"] == speech  # the transcript keeps what was actually said
