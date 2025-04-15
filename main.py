import os

from typing import (
    Annotated,
    Sequence,
    TypedDict,
)

from dotenv import load_dotenv
from agent import call_model, should_continue
from tools import tool_node
from load_model import AgentState, model


from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END


def start_workflow():
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END,
        },
    )

    workflow.add_edge("tools", "agent")

    graph = workflow.compile()

    return graph


def print_stream(stream):
    for s in stream:
        message = s["messages"][-1]
        if isinstance(message, tuple):
            print(message)
        else:
            message.pretty_print()

def main():
    graph = start_workflow()
    inputs = {"messages": [("user", "what is the weather in sf")]} #change this so that the user can input the value
    print_stream(graph.stream(inputs, stream_mode="values"))

