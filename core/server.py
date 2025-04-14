# Base MCP Integration Plugin class
from typing import Any, Dict, List


class MCPIntegrationPlugin:
    """Base class for all MCP integration plugins"""

    name: str
    capabilities: List[Dict[str, Any]]

    async def handle_request(
        self, action: str, params: Dict, credentials: Dict
    ) -> Dict:
        """Process a request for this integration"""
        raise NotImplementedError("Subclasses must implement handle_request")

    async def validate_credentials(self, credentials: Dict) -> bool:
        """Validate credentials for this integration"""
        raise NotImplementedError("Subclasses must implement validate_credentials")

    def get_capabilities(self) -> List[Dict[str, Any]]:
        """Return the list of capabilities this integration supports"""
        return self.capabilities
