from content.helpers.tools import tool_node
from content.helpers.load_model import AgentState

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage
from content.helpers.load_model import AgentState, model
from content.helpers.parse_query import extract_intent_and_constraints
from langchain.schema import HumanMessage


class RunAgent:
    def __init__(self):
        self.agent_state = StateGraph(AgentState)
        self.workflow = self.agent_state


    def call_model(self):
        system_prompt_value = ''
        for message in self.state["messages"]:
            if isinstance(message, HumanMessage):
                print("User said:", message.content)
                system_prompt_value = extract_intent_and_constraints(message.content)
        system_prompt = SystemMessage(system_prompt_value)
        response = model.invoke([system_prompt] + self.state["messages"], self.config)
        return {"messages": [response]}

    def should_continue(self):
        messages = self.state["messages"]
        last_message = messages[-1]
        if not last_message.tool_calls:
            return "end"
        else:
            return "continue"
        
    def start_workflow(self):
        self.workflow.add_node("agent", self.call_model)
        self.workflow.add_node("tools", tool_node)

        self.workflow.set_entry_point("agent")

        self.workflow.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "continue": "tools",
                "end": END,
            },
        )

        self.workflow.add_edge("tools", "agent")

        graph = self.workflow.compile()

        return graph
    
    def print_stream(stream):
        for s in stream:
            message = s["messages"][-1]
            if isinstance(message, tuple):
                print(message)
            else:
                message.pretty_print()

    def initialize_graph(self):
        graph = self.start_workflow()
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




