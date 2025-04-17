from abc import ABC, abstractmethod

class Integration(ABC):
    def __init__(self, credentials):
        self.credentials = credentials

    @abstractmethod
    def call_tool(self, tool_name, payload):
        pass
