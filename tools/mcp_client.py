import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpTools:
    """
    A class for managing and interacting with MCP (Model Context Protocol) tools.
    """

    def __init__(self, mcp_config_file="mcp_config.json"):
        """
        Initializes the McpTools class by loading the MCP server configurations from a JSON file.

        Args:
            mcp_config_file (str, optional): The path to the MCP configuration file. Defaults to "mcp_config.json".
        """
        self.mcp_server_config = []
        with open(mcp_config_file, "r") as f:
            config = json.load(f)

        self.mcp_server_config = config["mcpServers"]
        self.mcp_tools = {}

    async def list_tools(self):
        """
        Lists all available tools from the configured MCP servers.

        Returns:
            dict: A dictionary where keys are server names and values are the list of tools provided by each server.
        """
        if self.mcp_tools:
            return self.mcp_tools

        tools = {}
        for server_name, server_conofig in self.mcp_server_config.items():
            server_parameter = StdioServerParameters(
                command=server_conofig["command"], args=server_conofig["args"]
            )

            async with stdio_client(server_parameter) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools[server_name] = await session.list_tools()

        self.mcp_tools = tools

        return self.mcp_tools

    async def list_bedrock_tools(self):
        """
        Lists all available tools in a Bedrock-compatible format.

        Returns:
            list: A list of dictionaries, where each dictionary represents a tool in the Bedrock format.
        """
        bedrock_tools = []
        for server_name, tools in (await self.list_tools()).items():
            for tool in tools.tools:
                bedrock_tools.append(
                    {
                        "toolSpec": {
                            "name": f"{server_name}_{tool.name}",
                            "description": tool.description,
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": tool.inputSchema["properties"],
                                    "required": tool.inputSchema["required"]
                                    if "required" in tool.inputSchema
                                    else [],
                                }
                            },
                        }
                    }
                )

        return bedrock_tools

    async def call_mcp_tool(self, name, arguments):
        """
        Calls an MCP tool with the given name and arguments.

        Args:
            name (str): The name of the tool to call (e.g., "server_toolname").
            arguments (dict): A dictionary containing the arguments for the tool.

        Returns:
            dict: A dictionary representing the result of the tool call.
        """
        server_name = name.split("_", 1)[0]
        tool_name = name.split("_", 1)[1]

        config = self.mcp_server_config[server_name]

        command = config["command"]
        arg = config["args"] if "args" in config else None
        env = config["env"] if "env" in config else None

        server_parameter = StdioServerParameters(command=command, args=arg, env=env)

        async with stdio_client(server_parameter) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(name=tool_name, arguments=arguments)

                return result.model_dump()
