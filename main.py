from typing import Union

from fastapi import FastAPI, Request
from pydantic import BaseModel
from integrations.gcal import get_calendars

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


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    return {"item_name": item.name, "item_id": item_id}


@app.get("/api/gcal/calendars")
async def get_calendars_route(user_id: str):
    return await get_calendars(user_id)
