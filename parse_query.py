import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_intent_and_constraints(user_prompt):
    system_prompt = """
You are a natural language compiler. Given a user prompt, extract the core intent (what the user wants to do) and any relevant constraints (time, people, conditions, tools, etc).

Respond in this JSON format:
{
  "intent": "<short and clear description of the user's goal>",
  "constraints": ["<constraint 1>", "<constraint 2>", ...]
}
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
    try:
        return eval(content)
    except Exception as e:
        raise ValueError(f"Could not parse LLM response:\n{content}") from e



if __name__ == "__main__":
    prompt = "I'm having a bad day and dont want to respond to my emails, can you go through and respond to all the emails I missed only from last week though?"
    parsed = extract_intent_and_constraints(prompt)
    print(parsed)
