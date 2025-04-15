import json
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from load_model import AgentState, model
from parse_query import extract_intent_and_constraints

def call_model(
    state: AgentState,
    config: RunnableConfig,
):
    system_prompt_value = extract_intent_and_constraints(state["messages"])

    system_prompt = SystemMessage(system_prompt_value)
    response = model.invoke([system_prompt] + state["messages"], config)
    return {"messages": [response]}


def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return "end"
    else:
        return "continue"
    