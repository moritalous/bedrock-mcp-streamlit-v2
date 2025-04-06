# Bedrock Chat with MCP tool (ver.2)

This is a chat application built with Streamlit and integrated with the MCP (Model Context Protocol) tool.

## Overview

Bedrock Chat with MCP tool is a chat application built with Streamlit and integrated with the MCP (Model Context Protocol) tool.

This application uses Bedrock . It interacts with the MCP (Model Context Protocol) server defined in `config/mcp_config.json` and accesses various tools. MCP is an open protocol that standardizes how applications provide context to LLM ([https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)). Chat history is stored in a YAML file.

The `config/config.json` file allows you to configure the LLM model to use, where the chat history files are stored, etc.
The `config/mcp_config.json` file describes the configuration of the MCP server.

In the Streamlit sidebar, you can configure the following:
- Select LLM model
- Enable/disable prompt cache
- Change chat history directory
- Change MCP configuration file
- Select tools
- Generate system prompt
- Start a new chat

## Features

- Chat interface using Streamlit
- Bedrock integration
- MCP tool integration
- LLM model selection
- Prompt cache enable/disable
- Chat history save/load
- MCP configuration file change
- Tool selection
- System prompt generation
- File upload

## Setup

1. Install dependencies:

    ```bash
    uv sync
    ```

2. Configure MCP server in `config/mcp_config.json`.

3. Run the application.

    ```bash
    streamlit run main.py
    ```

## Configuration

The `config/config.json` file is where you configure the LLM model and other settings.

```json
{
    "chat_history_dir": "chat_history",
    "mcp_config_file": "config/mcp_config.json",
    "models": {
        "us.amazon.nova-pro-v1:0": {
            "cache_support": [
                "system"
            ]
        },
        ...
        "us.anthropic.claude-3-7-sonnet-20250219-v1:0": {
            "cache_support": [
                "system",
                "messages",
                "tools"
            ]
        },
        ...
    }
}
```

The `config/mcp_config.json` file contains the settings for the MCP server.

```json
{
    "mcpServers": {
        "fetch": {
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                "mcp/fetch"
            ]
        },
        ...
    }
}
```

## Usage

To run the Streamlit application, run the following command.

```bash
streamlit run main.py
```

1.  Run the Streamlit application.
2.  Enter a message in the chat input box.
3.  The chat model and MCP tool will generate a response.
4.  In the sidebar, you can configure the LLM model, chat history directory, MCP configuration file, etc.
5.  You can also select past chat history and resume the conversation.


## Notes

- Write the MCP server configuration in `config/mcp_config.json`.
- To use Bedrock, you need an AWS account.
- Chat history is stored in a YAML file.
