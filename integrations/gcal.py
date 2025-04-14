from typing import Dict
from datetime import datetime
import httpx
from core.server import MCPIntegrationPlugin


# Google Calendar Integration Plugin
class GoogleCalendarIntegration(MCPIntegrationPlugin):
    name = "google_calendar"
    capabilities = [
        {
            "name": "list_events",
            "description": "List events from a user's calendar",
            "parameters": ["start_time", "end_time", "calendar_id", "max_results"],
        },
        {
            "name": "create_event",
            "description": "Create a new event on a user's calendar",
            "parameters": [
                "calendar_id",
                "summary",
                "start",
                "end",
                "description",
                "attendees",
                "location",
            ],
        },
        {
            "name": "get_calendars",
            "description": "List all calendars for a user",
            "parameters": [],
        },
        {
            "name": "get_event",
            "description": "Get details of a specific event",
            "parameters": ["calendar_id", "event_id"],
        },
        {
            "name": "update_event",
            "description": "Update an existing event",
            "parameters": [
                "calendar_id",
                "event_id",
                "summary",
                "start",
                "end",
                "description",
                "attendees",
                "location",
            ],
        },
        {
            "name": "delete_event",
            "description": "Delete an event",
            "parameters": ["calendar_id", "event_id"],
        },
    ]

    async def handle_request(
        self, action: str, params: Dict, credentials: Dict
    ) -> Dict:
        """Handle Google Calendar requests"""
        if not credentials.get("access_token"):
            return {"error": "No access token provided"}

        # Map actions to handler methods
        handlers = {
            "list_events": self._list_events,
            "create_event": self._create_event,
            "get_calendars": self._get_calendars,
            "get_event": self._get_event,
            "update_event": self._update_event,
            "delete_event": self._delete_event,
        }

        if action not in handlers:
            return {"error": f"Unknown action: {action}"}

        return await handlers[action](params, credentials)

    async def validate_credentials(self, credentials: Dict) -> bool:
        """Check if the provided credentials are valid"""
        if not credentials.get("access_token"):
            return False

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            return response.status_code == 200

    async def _refresh_token_if_needed(self, credentials: Dict) -> Dict:
        """Refresh token if it's about to expire"""
        # Check if token needs refresh
        current_time = int(datetime.now().timestamp())
        if (
            credentials.get("expiry_date")
            and current_time + 300 >= credentials["expiry_date"]
        ):
            if not credentials.get("refresh_token"):
                return credentials

            # Refresh the token
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": credentials["client_id"],
                        "client_secret": credentials["client_secret"],
                        "refresh_token": credentials["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )

                if response.status_code == 200:
                    new_tokens = response.json()
                    credentials["access_token"] = new_tokens["access_token"]
                    credentials["expiry_date"] = int(
                        datetime.now().timestamp() + new_tokens["expires_in"]
                    )
                    # Keep existing refresh token if not provided
                    if "refresh_token" in new_tokens:
                        credentials["refresh_token"] = new_tokens["refresh_token"]

        return credentials

    async def _list_events(self, params: Dict, credentials: Dict) -> Dict:
        """List calendar events"""
        # Refresh token if needed
        credentials = await self._refresh_token_if_needed(credentials)

        # Default parameters
        calendar_id = params.get("calendar_id", "primary")
        max_results = params.get("max_results", 100)

        # Build query parameters
        query_params = {
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }

        if params.get("start_time"):
            query_params["timeMin"] = params["start_time"]
        else:
            # Default to current time
            query_params["timeMin"] = datetime.utcnow().isoformat() + "Z"

        if params.get("end_time"):
            query_params["timeMax"] = params["end_time"]

        # Call Google Calendar API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                params=query_params,
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )

            if response.status_code != 200:
                return {
                    "error": f"Failed to fetch events: {response.status_code}",
                    "details": response.text,
                }

            data = response.json()
            return {"events": data.get("items", [])}

    async def _create_event(self, params: Dict, credentials: Dict) -> Dict:
        """Create a new calendar event"""
        # Refresh token if needed
        credentials = await self._refresh_token_if_needed(credentials)

        calendar_id = params.get("calendar_id", "primary")

        # Build event data
        event_data = {
            "summary": params.get("summary", "New Event"),
            "start": params.get("start"),
            "end": params.get("end"),
        }

        # Optional fields
        if params.get("description"):
            event_data["description"] = params["description"]

        if params.get("location"):
            event_data["location"] = params["location"]

        if params.get("attendees"):
            event_data["attendees"] = [
                {"email": email} for email in params["attendees"]
            ]

        # Call Google Calendar API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                json=event_data,
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )

            if response.status_code not in (200, 201):
                return {
                    "error": f"Failed to create event: {response.status_code}",
                    "details": response.text,
                }

            return {"event": response.json()}

    async def _get_calendars(self, params: Dict, credentials: Dict) -> Dict:
        """List all calendars"""
        # Refresh token if needed
        credentials = await self._refresh_token_if_needed(credentials)

        # Call Google Calendar API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )

            if response.status_code != 200:
                return {
                    "error": f"Failed to fetch calendars: {response.status_code}",
                    "details": response.text,
                }

            data = response.json()
            return {"calendars": data.get("items", [])}

    async def _get_event(self, params: Dict, credentials: Dict) -> Dict:
        """Get a specific event"""
        # Refresh token if needed
        credentials = await self._refresh_token_if_needed(credentials)

        calendar_id = params.get("calendar_id", "primary")
        event_id = params.get("event_id")

        if not event_id:
            return {"error": "event_id is required"}

        # Call Google Calendar API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )

            if response.status_code != 200:
                return {
                    "error": f"Failed to fetch event: {response.status_code}",
                    "details": response.text,
                }

            return {"event": response.json()}

    async def _update_event(self, params: Dict, credentials: Dict) -> Dict:
        """Update an existing event"""
        # Refresh token if needed
        credentials = await self._refresh_token_if_needed(credentials)

        calendar_id = params.get("calendar_id", "primary")
        event_id = params.get("event_id")

        if not event_id:
            return {"error": "event_id is required"}

        # First get the existing event
        async with httpx.AsyncClient() as client:
            get_response = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )

            if get_response.status_code != 200:
                return {
                    "error": f"Failed to fetch event for update: {get_response.status_code}",
                    "details": get_response.text,
                }

            event_data = get_response.json()

            # Update with new values
            if params.get("summary"):
                event_data["summary"] = params["summary"]

            if params.get("start"):
                event_data["start"] = params["start"]

            if params.get("end"):
                event_data["end"] = params["end"]

            if params.get("description"):
                event_data["description"] = params["description"]

            if params.get("location"):
                event_data["location"] = params["location"]

            if params.get("attendees"):
                event_data["attendees"] = [
                    {"email": email} for email in params["attendees"]
                ]

            # Submit update
            response = await client.put(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                json=event_data,
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )

            if response.status_code != 200:
                return {
                    "error": f"Failed to update event: {response.status_code}",
                    "details": response.text,
                }

            return {"event": response.json()}

    async def _delete_event(self, params: Dict, credentials: Dict) -> Dict:
        """Delete an event"""
        # Refresh token if needed
        credentials = await self._refresh_token_if_needed(credentials)

        calendar_id = params.get("calendar_id", "primary")
        event_id = params.get("event_id")

        if not event_id:
            return {"error": "event_id is required"}

        # Call Google Calendar API
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )

            if response.status_code not in (200, 204):
                return {
                    "error": f"Failed to delete event: {response.status_code}",
                    "details": response.text,
                }

            return {"success": True, "message": "Event deleted successfully"}
