import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_intent_and_constraints(user_prompt):
    allowed_integrations = {
        "google_calendar_list": {
            "description": "Allows viewing and managing events from the user's Google Calendar.",
            "tools": {
                "get_events": "Fetches all events for a given date range.",
                "create_event": "Creates a new event with title, time, and participants.",
                "delete_event": "Deletes a specified calendar event."
            }
        }
    }

    integration_descriptions = "\n".join(
        f'- "{name}": {data["description"]}\n  Tools: {", ".join([f"{tool} - {desc}" for tool, desc in data["tools"].items()])}'
        for name, data in allowed_integrations.items()
    )

    system_prompt = f"""
You are a natural language compiler. Given a user prompt, extract the core intent (what the user wants to do), any relevant constraints (time, people, conditions, tools, etc), and a relevant integration.

ONLY pick one integration from this list:
{list(allowed_integrations.keys())}

Here are the available integrations and their tools:

{integration_descriptions}

If no relevant integration is found in the user prompt, return null for "integration" and an empty list for "tools".

Based on the selected integration and the user's intent, pick the most relevant tools.

Respond in this JSON format:
{{
  "intent": "<short and clear description of the user's goal>",
  "constraints": ["<constraint 1>", "<constraint 2>", ...],
  "integration": "<one of the allowed integrations or null>",
  "tools": ["<tool_name_1>", "<tool_name_2>", ...]
}}
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    content = response.choices[0].message.content.strip()
    return content

content = extract_intent_and_constraints("can you grab all the events from the week of dec 17th 2024")
print(content)