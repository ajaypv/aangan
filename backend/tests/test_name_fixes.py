from app.speech import clean_input

DEMO = [
    {"name": "Priya", "relation": "Mom"}, {"name": "Rahul", "relation": "Dad"},
    {"name": "Aarav", "relation": "Son"}, {"name": "Dadi", "relation": "Grandmother"},
]
OTHER = [{"name": "Meera", "relation": "Mom"}, {"name": "Arun", "relation": "Dad"}, {"name": "Arav", "relation": "Son"}]


def test_existing_members_get_their_mishearings_fixed():
    assert clean_input("how is arav doing", DEMO) == "how is Aarav doing"
    assert clean_input("did dhadhi take her medicine", DEMO) == "did Dadi take her medicine"
    assert clean_input("tell pria", DEMO) == "tell Priya"


def test_names_that_do_not_exist_are_never_invented():
    assert clean_input("how is arav doing", OTHER) == "how is arav doing"
    assert clean_input("tell pria", OTHER) == "tell pria"
    assert "Dadi" not in clean_input("did dhadhi take her medicine", OTHER)


def test_grandma_maps_to_whoever_the_grandmother_is():
    family = [{"name": "Sunita", "relation": "Grandmother"}, {"name": "Meera", "relation": "Mom"}]
    assert clean_input("did granny take her pills", family) == "did Sunita take her pills"
    assert clean_input("did granny take her pills", OTHER) == "did granny take her pills"


def test_generic_fixes_still_apply():
    assert clean_input("um could you please booked it", OTHER) == "could you book it"
    assert clean_input("call mummy", OTHER) == "call mom"


def test_daddy_is_dad_without_a_dadi():
    assert clean_input("call daddy", OTHER) == "call dad"
    assert clean_input("did daddy take her medicine", DEMO) == "did Dadi take her medicine"


def test_legacy_call_without_members_keeps_old_behaviour():
    assert clean_input("how is arav doing") == "how is Aarav doing"
