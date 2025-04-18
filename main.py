from typing import Union

from fastapi import FastAPI, Request
from pydantic import BaseModel
from integrations.gcal import get_calendars, get_events

app = FastAPI()


class Item(BaseModel):
    name: str
    price: float
    is_offer: Union[bool, None] = None


@app.get("/")
def read_root():
    return {
        "message": "In the beginning was the Word, and the Word was with God, and the Word was God."
    }


@app.get("/api/gcal/calendars")
async def get_calendars_route(user_id: str):
    return await get_calendars(user_id)


@app.get("/api/gcal/events")
async def get_events_route(user_id: str):
    return await get_events(user_id)
