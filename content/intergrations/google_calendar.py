import requests
from .base import Integration
class GoogleCalendarIntegration(Integration):
    BASE_URL = "https://www.googleapis.com/calendar/v3"

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.credentials['access_token']}",
            "Content-Type": "application/json"
        }

    def call_tool(self, tool_name, payload):
        if tool_name == "get_events":
            return self.get_events(payload)
        elif tool_name == "create_event":
            return self.create_event(payload)

    def get_events(self, payload):
        response = requests.get(f"{self.BASE_URL}/calendars/primary/events", 
                                headers=self.get_headers(), params=payload)
        return response.json()

    def create_event(self, payload):
        response = requests.post(f"{self.BASE_URL}/calendars/primary/events", 
                                 headers=self.get_headers(), json=payload)
        return response.json()
