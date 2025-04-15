from langchain_core.tools import tool
import httpx
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Database setup (you'll need to adjust this based on your environment)
uri = os.getenv("MONGODB_URI")
client = MongoClient(uri, server_api=ServerApi("1"))
db = client["logos-dev"]
user_tokens = db["gcal-tokens"]

# Google OAuth2 configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/api/gcal/callback")

# Utility functions from your original code
def get_user_tokens(user_id: str):
    user_token = user_tokens.find_one({"user_id": user_id})
    if not user_token:
        return None
    return user_token

async def refresh_token_if_needed(user_id: str):
    user_token = get_user_tokens(user_id)
    if not user_token:
        return None

    # Check if token is about to expire
    current_time = int(datetime.now().timestamp())
    if current_time + 300 >= user_token["expiry_date"]:  # 5 minutes buffer
        if not user_token.get("refresh_token"):
            return None

        # Refresh the token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "refresh_token": user_token["refresh_token"],
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code == 200:
                new_tokens = response.json()
                # Don't overwrite the refresh token if not provided
                if "refresh_token" not in new_tokens and user_token["refresh_token"]:
                    new_tokens["refresh_token"] = user_token["refresh_token"]

                return await save_tokens(user_id, new_tokens)

    return user_token

def save_tokens(user_id: str, tokens: dict):
    user_token = {
        "user_id": user_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expiry_date": int(datetime.now().timestamp() + tokens["expires_in"]),
    }

    # Check if user already exists
    existing = user_tokens.find_one({"user_id": user_id})
    if existing:
        user_tokens.update_one({"user_id": user_id}, {"$set": user_token})
    else:
        user_tokens.insert_one(user_token)

    return user_token

# Now let's create the tools

@tool
async def get_calendar_events(user_id: str, start: Optional[str] = None, end: Optional[str] = None, max_results: int = 10):
    """
    Fetch events from a user's Google Calendar.
    
    Args:
        user_id: The ID of the user whose calendar events to fetch
        start: Optional start time in ISO format (default: current time)
        end: Optional end time in ISO format
        max_results: Maximum number of events to return (default: 10)
        
    Returns:
        A list of calendar events
    """
    # Check if user is connected and refresh token if needed
    user_token = await refresh_token_if_needed(user_id)
    if not user_token:
        return "Error: User not connected to Google Calendar"

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
            headers={"Authorization": f"Bearer {user_token['access_token']}"},
        )

        if response.status_code != 200:
            return f"Error fetching events: {response.text}"

        data = response.json()
        events = data.get("items", [])
        
        # Format the events for better readability
        formatted_events = []
        for event in events:
            formatted_event = {
                "id": event.get("id"),
                "summary": event.get("summary", "Untitled Event"),
                "start": event.get("start", {}),
                "end": event.get("end", {}),
                "status": event.get("status"),
                "description": event.get("description")
            }
            formatted_events.append(formatted_event)
            
        return json.dumps(formatted_events, indent=2)

@tool
async def get_user_calendars(user_id: str):
    """
    Fetch the list of calendars for a specific user.
    
    Args:
        user_id: The ID of the user whose calendars to fetch
        
    Returns:
        A list of the user's calendars
    """
    # Check if user is connected and refresh token if needed
    user_token = await refresh_token_if_needed(user_id)
    if not user_token:
        return "Error: User not connected to Google Calendar"

    # Call Google Calendar API
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            headers={"Authorization": f"Bearer {user_token['access_token']}"},
        )

        if response.status_code != 200:
            return f"Error fetching calendars: {response.text}"

        data = response.json()
        calendars = data.get("items", [])
        
        # Format the calendars for better readability
        formatted_calendars = []
        for calendar in calendars:
            formatted_calendar = {
                "id": calendar.get("id"),
                "summary": calendar.get("summary", "Untitled Calendar"),
                "description": calendar.get("description"),
                "primary": calendar.get("primary", False)
            }
            formatted_calendars.append(formatted_calendar)
            
        return json.dumps(formatted_calendars, indent=2)

@tool
def check_calendar_connection(user_id: str):
    """
    Check if a user is connected to Google Calendar.
    
    Args:
        user_id: The ID of the user to check
        
    Returns:
        True if connected, False otherwise
    """
    # Check if user has valid tokens
    user_token = get_user_tokens(user_id)
    if not user_token:
        return False

    # Check if token is expired
    current_time = int(datetime.now().timestamp())
    if current_time >= user_token["expiry_date"] and not user_token.get("refresh_token"):
        return False

    return True

@tool
async def create_calendar_event(user_id: str, summary: str, start_time: str, end_time: str, 
                               description: Optional[str] = None, location: Optional[str] = None):
    """
    Create a new event in a user's Google Calendar.
    
    Args:
        user_id: The ID of the user creating the event
        summary: The title of the event
        start_time: Start time in ISO format
        end_time: End time in ISO format
        description: Optional description for the event
        location: Optional location for the event
        
    Returns:
        The created event details
    """
    # Check if user is connected and refresh token if needed
    user_token = await refresh_token_if_needed(user_id)
    if not user_token:
        return "Error: User not connected to Google Calendar"
    
    # Build the event payload
    event = {
        "summary": summary,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time}
    }
    
    if description:
        event["description"] = description
        
    if location:
        event["location"] = location
    
    # Call Google Calendar API to create the event
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            json=event,
            headers={"Authorization": f"Bearer {user_token['access_token']}", 
                    "Content-Type": "application/json"}
        )
        
        if response.status_code not in [200, 201]:
            return f"Error creating event: {response.text}"
            
        return json.dumps(response.json(), indent=2)