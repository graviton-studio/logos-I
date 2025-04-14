from fastapi import Body, FastAPI, HTTPException, Depends, Request, Response, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from jose import JWTError, jwt
import secrets
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from fastapi.security import OAuth2PasswordBearer


# Database setup
uri = os.getenv("MONGODB_URI")
# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi("1"))
# Send a ping to confirm a successful connection
try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
db = client["logos-dev"]
user_tokens = db["gcal-tokens"]

# Google OAuth2 configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/api/gcal/callback")
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

# Auth configuration for the MCP API
# In production, use a more secure setup
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Models
class TokenData(BaseModel):
    user_id: str


class UserToken(BaseModel):
    user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    expiry_date: int


class Event(BaseModel):
    id: str
    summary: str
    start: Dict[str, Any]
    end: Dict[str, Any]
    status: Optional[str] = None
    description: Optional[str] = None


class EventsResponse(BaseModel):
    events: List[Event]


class Calendar(BaseModel):
    id: str
    summary: str
    description: Optional[str] = None
    primary: Optional[bool] = None


class CalendarsResponse(BaseModel):
    calendars: List[Calendar]


class StatusResponse(BaseModel):
    connected: bool


# Auth functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")

        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return {"id": user_id}


# Utility functions
def get_user_tokens(user_id: str):
    user_token = user_tokens.find_one({"user_id": user_id})
    if not user_token:
        return None
    return user_token


def save_tokens(user_id: str, tokens: dict):
    user_token = {
        "user_id": user_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expiry_date": int(datetime.now().timestamp() + tokens["expires_in"]),
    }
    print(user_token)

    # Check if user already exists
    existing = user_tokens.find_one({"user_id": user_id})
    if existing:
        print("Updating user token")
        user_tokens.update_one({"user_id": user_id}, {"$set": user_token})
    else:
        print("Inserting user token")
        user_tokens.insert_one(user_token)

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


def connect_google_calendar(request: Request, user_id: str):
    # Generate state token for security
    state = create_access_token({"sub": user_id})

    # Build the authorization URL
    auth_url = (
        "https://accounts.google.com/o/oauth2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={'%20'.join(SCOPES)}"
        "&response_type=code"
        "&access_type=offline"
        "&prompt=consent"
        f"&state={state}"
    )

    return RedirectResponse(auth_url)


async def get_events(
    user_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_results: int = 100,
):

    # Check if user is connected and refresh token if needed
    user_token = await refresh_token_if_needed(user_id)
    if not user_token:
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
            headers={"Authorization": f"Bearer {user_token['access_token']}"},
        )
        print(response.json())

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch events from Google Calendar API",
            )

        data = response.json()
        return {"events": data.get("items", [])}


async def get_calendars(user=Depends(get_current_user)):
    user_id = user["id"]

    # Check if user is connected and refresh token if needed
    user_token = await refresh_token_if_needed(user_id)
    if not user_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not connected to Google Calendar",
        )

    # Call Google Calendar API
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList",
            headers={"Authorization": f"Bearer {user_token['access_token']}"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch calendars from Google Calendar API",
            )

        data = response.json()
        return {"calendars": data.get("items", [])}


def check_status(user=Depends(get_current_user)):
    user_id = user["id"]

    # Check if user has valid tokens
    user_token = get_user_tokens(user_id)
    if not user_token:
        return {"connected": False}

    # Check if token is expired
    current_time = int(datetime.now().timestamp())
    if current_time >= user_token["expiry_date"] and not user_token.get(
        "refresh_token"
    ):
        return {"connected": False}

    return {"connected": True}


async def disconnect(user=Depends(get_current_user)):
    user_id = user["id"]

    # Get user tokens
    user_token = get_user_tokens(user_id)
    if not user_token:
        return {"success": False, "message": "User not connected"}

    # Revoke access token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://oauth2.googleapis.com/revoke?token={user_token['access_token']}"
        )

    # Remove from database
    await user_tokens.delete_one({"user_id": user_id})

    return {
        "success": True,
        "message": "Successfully disconnected from Google Calendar",
    }


# Simple token endpoint for testing
def login_for_access_token(user_id: str = Body(..., embed=True)):
    access_token = create_access_token(
        data={"sub": user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}
