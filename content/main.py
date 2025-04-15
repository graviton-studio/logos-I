from agent import call_model, should_continue
from tools import tool_node
from load_model import AgentState

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
    history = []

    while True:
        user_input = input("Enter your prompt (or type 'exit' to quit): ").strip()
        if user_input.lower() == "exit":
            break

        history.append(("user", user_input))
        inputs = {"messages": history}

        print("================================ Response ================================")
        for s in graph.stream(inputs, stream_mode="values"):
            message = s["messages"][-1]

            if isinstance(message, tuple):
                print(message[1])
                history.append(message)
            else:
                message.pretty_print()
                history.append(("agent", message.content))

        print("\n")


main()