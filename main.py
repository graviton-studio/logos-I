from typing import Union

from fastapi import FastAPI
from pydantic import BaseModel
from integrations.gcal import get_calendars, get_events
from google.oauth2.credentials import Credentials
from utils.auth import TokenService
from integrations.gmail import (
    GmailClient,
    SendMessageRequest,
    CreateDraftRequest,
    ReplyMessageRequest,
)
from integrations.gsheets import (
    GSheetsClient,
    CreateSpreadsheetRequest,
    GetSpreadsheetRequest,
    GetValuesRequest,
    UpdateValuesRequest,
    AppendValuesRequest,
)

from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.routing import Mount, Route
from mcp.server import Server
import uvicorn
import argparse
from utils.goog import build_query


mcp = FastMCP("MCP Server Gateway")


class Item(BaseModel):
    name: str
    price: float
    is_offer: Union[bool, None] = None


@mcp.tool(
    name="get_google_calendar_calendars",
    description="Get user's Google Calendar calendars",
)
async def get_google_calendar_calendars(user_id: str):
    return await get_calendars(user_id)


@mcp.tool(
    name="get_google_calendar_events", description="Get user's Google Calendar events"
)
async def get_google_calendar_events(user_id: str):
    return await get_events(user_id)


@mcp.tool(name="send_gmail_message", description="Send a Gmail message to a user")
async def send_message(
    request: SendMessageRequest,
):
    credentials = TokenService.get_credentials(request.user_id, "gmail")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GmailClient(credentials)
    result = await client.send_message(
        to=request.to,
        subject=request.subject,
        message_text=request.message_text,
        attachments=request.attachments,
    )
    return result


@mcp.tool(name="create_gmail_draft", description="Create a draft Gmail message")
async def create_gmail_draft(
    request: CreateDraftRequest,
):
    credentials = TokenService.get_credentials(request.user_id, "gmail")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GmailClient(credentials)
    result = await client.create_draft(
        to=request.to,
        subject=request.subject,
        message_text=request.message_text,
        attachments=request.attachments,
    )
    return result


@mcp.tool(name="reply_gmail_message", description="Reply to a Gmail message")
async def reply_gmail_message(
    request: ReplyMessageRequest,
):
    credentials = TokenService.get_credentials(request.user_id, "gmail")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GmailClient(credentials)
    result = await client.reply_message(
        message_id=request.message_id,
        to=request.to,
        subject=request.subject,
        message_text=request.message_text,
        thread_id=request.thread_id,
    )
    return result


@mcp.tool(name="list_gmail_messages", description="List a user's Gmail messages")
async def list_gmail_messages(
    user_id: str,
    max_results: int = 10,
):
    credentials = TokenService.refresh_token_if_needed(user_id, "gmail")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GmailClient(credentials)
    result = client.list_messages(max_results=max_results)
    return result


@mcp.tool(name="search_gmail_messages", description="Search a user's Gmail messages")
async def search_gmail_messages(
    user_id: str,
    max_results: int = 10,
    from_: str = None,
    to: str = None,
    subject: str = None,
    after: str = None,
    before: str = None,
    has: str = None,
    exclude: list[str] = None,
    or_: list[str] = None,
    and_: list[str] = None,
    text: str = None,
):
    credentials = TokenService.refresh_token_if_needed(user_id, "gmail")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GmailClient(credentials)
    query = build_query(
        from_=from_, to=to, subject=subject, after=after, before=before, text=text
    )
    assert query
    result = client.search_messages(query=query, max_results=max_results)
    return result


@mcp.tool(name="list_gmail_labels", description="List a user's Gmail labels")
async def list_gmail_labels(user_id: str):
    credentials = TokenService.get_credentials(user_id, "gmail")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GmailClient(credentials)
    result = await client.list_labels()
    return result


# Google Sheets Tools
@mcp.tool(
    name="create_spreadsheet", description="Create a new Google Sheets spreadsheet"
)
async def create_spreadsheet(request: CreateSpreadsheetRequest):
    credentials = TokenService.refresh_token_if_needed(request.user_id, "sheets")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GSheetsClient(credentials)
    result = await client.create_spreadsheet_async(request.title)
    return result


@mcp.tool(name="get_spreadsheet", description="Get a Google Sheets spreadsheet")
async def get_spreadsheet(request: GetSpreadsheetRequest):
    credentials = TokenService.refresh_token_if_needed(request.user_id, "sheets")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GSheetsClient(credentials)
    result = await client.get_spreadsheet_async(request.spreadsheet_id)
    return result


@mcp.tool(name="get_values", description="Get values from a Google Sheets spreadsheet")
async def get_values(request: GetValuesRequest):
    credentials = TokenService.refresh_token_if_needed(request.user_id, "sheets")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GSheetsClient(credentials)
    result = await client.get_values_async(request.spreadsheet_id, request.range_name)
    return result


@mcp.tool(
    name="update_values", description="Update values in a Google Sheets spreadsheet"
)
async def update_values(request: UpdateValuesRequest):
    credentials = TokenService.refresh_token_if_needed(request.user_id, "sheets")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GSheetsClient(credentials)
    result = await client.update_values_async(
        request.spreadsheet_id, request.range_name, request.values
    )
    return result


@mcp.tool(
    name="append_values", description="Append values to a Google Sheets spreadsheet"
)
async def append_values(request: AppendValuesRequest):
    credentials = TokenService.refresh_token_if_needed(request.user_id, "sheets")
    credentials = Credentials(
        token=credentials.access_token, refresh_token=credentials.refresh_token
    )
    client = GSheetsClient(credentials)
    result = await client.append_values_async(
        request.spreadsheet_id, request.range_name, request.values
    )
    return result


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can server the provied mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


if __name__ == "__main__":
    mcp_server = mcp._mcp_server  # noqa: WPS437

    parser = argparse.ArgumentParser(description="Run MCP SSE-based server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    args = parser.parse_args()

    # Bind SSE request handling to MCP server
    starlette_app = create_starlette_app(mcp_server, debug=True)

    uvicorn.run(starlette_app, host=args.host, port=args.port)
