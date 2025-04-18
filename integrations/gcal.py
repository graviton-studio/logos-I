from fastapi import HTTPException, status
from typing import Optional
from datetime import datetime
import httpx
from utils.auth import TokenService
from fastapi.concurrency import run_in_threadpool


async def get_events(
    user_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_results: int = 100,
):

    # Check if user is connected and refresh token if needed
    credential = TokenService.refresh_token_if_needed(user_id, "gcal")
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not connected to Google Calendar",
        )

    # Default to current time if start not provided
    if not start:
        start = datetime.utcnow().isoformat() + "Z"

    # Build query parameters
    params = {
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
        "timeMin": start,
    }

    if end:
        params["timeMax"] = end

    # Call Google Calendar API
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            params=params,
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        print(response.json())

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch events from Google Calendar API",
            )

        data = response.json()
        return {"events": data.get("items", [])}


async def get_calendars(user_id: str):
    # Check if user is connected and refresh token if needed
    credential = TokenService.refresh_token_if_needed(user_id, "gcal")
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not connected to Google Calendar",
        )

    # Call Google Calendar API
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch calendars from Google Calendar API",
            )

        data = response.json()
        return {"calendars": data.get("items", [])}
