from intergrations import INTEGRATION_REGISTRY

class MCPGatewayServer:
    def __init__(self, db_client):
        self.db = db_client

    def get_user_credentials(self, user_id, integration_name):
        user = self.db.find_user_by_id(user_id)
        return user["integrations"].get(integration_name)

    def call_integration(self, integration_name, tool_name, user_credentials, payload):
        IntegrationClass = INTEGRATION_REGISTRY.get(integration_name)
        if not IntegrationClass:
            raise Exception(f"No integration found for {integration_name}")

        integration = IntegrationClass(user_credentials)
        return integration.call_tool(tool_name, payload)
