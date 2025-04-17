#this file should be populated with intergrations and speific ways we want the prompt handled
import json
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from content.helpers.load_model import AgentState, model

#example 
@tool
def get_weather(location: str):
    """Call to get the weather from a specific location."""
    if any([city in location.lower() for city in ["sf", "san francisco"]]):
        return "It's sunny in San Francisco, but you better look out if you're a Gemini 😈."
    else:
        return f"I am not sure what the weather is in {location}"


tools = [get_weather]

model = model.bind_tools(tools)


tools_by_name = {tool.name: tool for tool in tools}


# Define our tool node
def tool_node(state: AgentState):
    outputs = []
    for tool_call in state["messages"][-1].tool_calls:
        tool_result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        outputs.append(
            ToolMessage(
                content=json.dumps(tool_result),
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        )
    return {"messages": outputs}


#goal should be to call the tool_node in the main.py file 