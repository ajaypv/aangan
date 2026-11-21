from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictBool

from .agents.smart_home import get_house_state, link_house
from .state import STATE
from .toolkit import ToolError

router = APIRouter(prefix="/api/house", tags=["virtual house"])


class HouseLink(BaseModel):
    house_id: Literal["cozy-home"]
    linked: StrictBool


@router.get("")
def house_state():
    return get_house_state(STATE)


@router.post("/link")
def house_link(body: HouseLink):
    try:
        house = link_house(STATE, body.house_id, body.linked)
    except ToolError as exc:
        raise HTTPException(409, str(exc)) from exc
    STATE.log("smart_home", "link_house", body.model_dump(), "ok", {"linked": house["linked"]}, 0)
    return house
