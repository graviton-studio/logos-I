from typing import Union

from fastapi import FastAPI, Request
from pydantic import BaseModel
from integrations.gcal import get_calendars, get_events
from integrations.gmail import list_messages
from googleapiclient.discovery import build
from utils.auth import TokenService
from integrations.gmail import (
    GmailClient,
    SendMessageRequest,
    CreateDraftRequest,
    ReplyMessageRequest,
)
from fastapi import Depends


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


@app.get("/gcal/calendars")
async def get_calendars_endpoint(user_id: str):
    return await get_calendars(user_id)


@app.get("/gcal/events")
async def get_events_endpoint(user_id: str):
    return await get_events(user_id)


@app.post("/gmail/send-message")
async def send_message(
    request: SendMessageRequest,
):
    client = GmailClient(TokenService.get_credentials(request.user_id, "gmail"))
    result = await client.send_message(
        to=request.to,
        subject=request.subject,
        message_text=request.message_text,
        attachments=request.attachments,
    )
    return result


@app.post("/gmail/create-draft")
async def create_draft(
    request: CreateDraftRequest,
):
    client = GmailClient(TokenService.get_credentials(request.user_id, "gmail"))
    result = await client.create_draft(
        to=request.to,
        subject=request.subject,
        message_text=request.message_text,
        attachments=request.attachments,
    )
    return result


@app.post("/gmail/reply-message")
async def reply_message(
    request: ReplyMessageRequest,
):
    client = GmailClient(TokenService.get_credentials(request.user_id, "gmail"))
    result = await client.reply_message(
        message_id=request.message_id,
        to=request.to,
        subject=request.subject,
        message_text=request.message_text,
        thread_id=request.thread_id,
    )
    return result


@app.get("/gmail/list-messages")
async def list_messages(
    user_id: str,
    max_results: int = 10,
):
    client = GmailClient(TokenService.get_credentials(user_id, "gmail"))
    result = await client.list_messages(max_results=max_results)
    return result


@app.get("/gmail/list-labels")
async def list_labels(user_id: str):
    client = GmailClient(TokenService.get_credentials(user_id, "gmail"))
    result = await client.list_labels()
    return result
