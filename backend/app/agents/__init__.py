from .calendar import CalendarAgent
from .care import CareAgent
from .dining import DiningAgent
from .household import HouseholdAgent
from .money import MoneyAgent
from .school import SchoolAgent
from .travel import TravelAgent

REGISTRY = [TravelAgent(), CalendarAgent(), DiningAgent(), SchoolAgent(), CareAgent(), HouseholdAgent(), MoneyAgent()]
BY_NAME = {a.name: a for a in REGISTRY}


def seed_domains(state) -> None:
    for agent in REGISTRY:
        state.domains[agent.name] = agent.seed()
