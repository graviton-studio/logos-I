import uuid
from content.helpers.parse_query import extract_intent_and_constraints


class InitializeAgent:
    def __init__(self, query):
        self.system_prompt = extract_intent_and_constraints(user_prompt=query)
        self.user_id = str(uuid.uuid4())


# this is where we should put the logic to store the object in supabase
