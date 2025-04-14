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

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Google Calendar MCP")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


async def get_current_user(token: str = Depends(oauth2_scheme)):
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


async def save_tokens(user_id: str, tokens: dict):
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


# Routes
@app.get("/")
async def root():
    return {"message": "Google Calendar MCP API"}


@app.get("/api/gcal/connect")
async def connect_google_calendar(request: Request, user_id: str):
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


@app.get("/api/gcal/callback")
async def auth_callback(code: str, state: str):
    try:
        # Decode state to get user_id
        payload = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )

            if token_response.status_code != 200:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": "Failed to exchange authorization code"},
                )

            tokens = token_response.json()
            await save_tokens(user_id, tokens)

            # Create user session token
            access_token = create_access_token(
                data={"sub": user_id},
                expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            )

            # Redirect to dashboard with token
            return RedirectResponse(f"/", status_code=status.HTTP_303_SEE_OTHER)

    except JWTError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid state parameter"},
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": str(e)}
        )


@app.get("/api/gcal/events")
async def get_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_results: int = 100,
    user=Depends(get_current_user),
):
    user_id = user["id"]

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


@app.get("/api/gcal/calendars")
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


@app.get("/api/gcal/status", response_model=StatusResponse)
async def check_status(user=Depends(get_current_user)):
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


@app.post("/api/gcal/disconnect")
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
@app.post("/token")
async def login_for_access_token(user_id: str = Body(..., embed=True)):
    access_token = create_access_token(
        data={"sub": user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


# Debug API route for testing without HTML
@app.get("/api/debug")
async def debug_api(
    action: str,
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Debug endpoint for testing Google Calendar integration without HTML.

    Actions:
    - status: Check connection status for user
    - connect: Get authorization URL for a user
    - events: Get user's events (requires user to be connected)
    - calendars: Get user's calendars (requires user to be connected)
    - disconnect: Disconnect user from Google Calendar

    Example: /api/debug?action=status&user_id=testuser
    """
    try:
        if action == "status":
            user_token = get_user_tokens(user_id)
            if not user_token:
                return {"connected": False, "user_id": user_id}

            current_time = int(datetime.now().timestamp())
            return {
                "connected": True,
                "user_id": user_id,
                "token_valid": current_time < user_token["expiry_date"],
                "expiry": datetime.fromtimestamp(user_token["expiry_date"]).isoformat(),
                "has_refresh_token": bool(user_token.get("refresh_token")),
            }

        elif action == "connect":
            # Generate authorization URL
            state = create_access_token({"sub": user_id})
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
            return {"auth_url": auth_url, "user_id": user_id}

        elif action == "events":
            # Create mock user for dependency
            user = {"id": user_id}

            # Default parameters
            if not start_date:
                start_date = datetime.utcnow().isoformat() + "Z"

            # Call the existing endpoint logic
            return await get_events(start=start_date, end=end_date, user=user)

        elif action == "calendars":
            # Create mock user for dependency
            user = {"id": user_id}
            return await get_calendars(user=user)

        elif action == "disconnect":
            # Create mock user for dependency
            user = {"id": user_id}
            return await disconnect(user=user)

        else:
            return {
                "error": f"Unknown action: {action}",
                "available_actions": [
                    "status",
                    "connect",
                    "events",
                    "calendars",
                    "disconnect",
                ],
            }

    except Exception as e:
        # More detailed error response for debugging
        import traceback

        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "details": {
                "action": action,
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        }


@app.get("/api/test")
async def test_workflow():
    """
    Returns instructions for testing the Google Calendar integration using the debug API.
    This provides a step-by-step guide that can be used with tools like curl, Postman, or any API client.
    """
    # Use a more explicit default URL and allow environment override
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    test_user = "test_user"  # Example user ID

    workflow = [
        {
            "step": 1,
            "description": "Get an access token for testing",
            "endpoint": f"{base_url}/token",
            "method": "POST",
            "body": {"user_id": test_user},
            "expected_response": {"access_token": "...", "token_type": "bearer"},
            "curl": f'curl -X POST "{base_url}/token" -H "Content-Type: application/json" -d \'{{"user_id": "{test_user}"}}\'',
        },
        {
            "step": 2,
            "description": "Check if user is connected to Google Calendar",
            "endpoint": f"{base_url}/api/debug?action=status&user_id={test_user}",
            "method": "GET",
            "expected_response": {"connected": False, "user_id": test_user},
            "curl": f'curl "{base_url}/api/debug?action=status&user_id={test_user}"',
        },
        {
            "step": 3,
            "description": "Get Google authorization URL",
            "endpoint": f"{base_url}/api/debug?action=connect&user_id={test_user}",
            "method": "GET",
            "notes": "Copy the auth_url from the response and open it in a browser to authorize",
            "curl": f'curl "{base_url}/api/debug?action=connect&user_id={test_user}"',
        },
        {
            "step": 4,
            "description": "After authorization, check connection status again",
            "endpoint": f"{base_url}/api/debug?action=status&user_id={test_user}",
            "method": "GET",
            "expected_response": {
                "connected": True,
                "user_id": test_user,
                "token_valid": True,
            },
            "curl": f'curl "{base_url}/api/debug?action=status&user_id={test_user}"',
        },
        {
            "step": 5,
            "description": "Get user's calendar events",
            "endpoint": f"{base_url}/api/debug?action=events&user_id={test_user}",
            "method": "GET",
            "notes": "You can add &start_date=2023-01-01T00:00:00Z&end_date=2023-01-31T23:59:59Z to filter by date range",
            "curl": f'curl "{base_url}/api/debug?action=events&user_id={test_user}"',
        },
        {
            "step": 6,
            "description": "Get user's calendars",
            "endpoint": f"{base_url}/api/debug?action=calendars&user_id={test_user}",
            "method": "GET",
            "curl": f'curl "{base_url}/api/debug?action=calendars&user_id={test_user}"',
        },
        {
            "step": 7,
            "description": "Disconnect from Google Calendar (optional)",
            "endpoint": f"{base_url}/api/debug?action=disconnect&user_id={test_user}",
            "method": "GET",
            "expected_response": {"success": True},
            "curl": f'curl "{base_url}/api/debug?action=disconnect&user_id={test_user}"',
        },
    ]

    return {
        "title": "Google Calendar Integration Test Workflow",
        "instructions": [
            "IMPORTANT: Replace 'localhost:8000' with your actual server address if not running locally",
            "Ensure the server is running before attempting these commands",
            "If you're running this on a different port or host, set the BASE_URL environment variable",
        ],
        "environment_setup": {
            "recommended_env_var": "export BASE_URL=http://localhost:8000  # or your actual server address",
            "port_note": "Default port is 8000, modify if your server uses a different port",
        },
        "base_url": base_url,
        "test_user": test_user,
        "workflow": workflow,
        "troubleshooting": [
            "If curl fails with 'could not resolve host', check your BASE_URL",
            "Ensure the server is running before testing",
            "Verify network connectivity and firewall settings",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
