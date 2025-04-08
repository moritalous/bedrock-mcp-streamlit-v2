import asyncio
import copy
import glob
import json
import os
import time
import uuid
from pathlib import Path

import boto3
import streamlit as st
import yaml

from tools.mcp_client import McpTools

format = {
    "image": ["png", "jpg", "jpeg", "gif", "webp"],
    "document": ["pdf", "csv", "doc", "docx", "xls", "xlsx", "html", "txt", "md"],
}


def process_streaming(stream_response):
    """Processes a streaming response from the Bedrock API.

    Args:
        stream_response (dict): The streaming response from the Bedrock API.

    Returns:
        dict: A dictionary containing the processed response data.
    """
    response = {
        "output": {"message": {"content": []}},
        "ResponseMetadata": stream_response["ResponseMetadata"],
    }

    container = st.empty()

    current_text = ""
    tool_use_info = None
    tool_input = ""

    for chunk in stream_response["stream"]:
        if "messageStart" in chunk:
            response["output"]["message"]["role"] = chunk["messageStart"]["role"]

        elif (
            "contentBlockStart" in chunk
            and "toolUse" in chunk["contentBlockStart"]["start"]
        ):
            tool_use_info = {
                "toolUseId": chunk["contentBlockStart"]["start"]["toolUse"][
                    "toolUseId"
                ],
                "name": chunk["contentBlockStart"]["start"]["toolUse"]["name"],
            }

        elif (
            "contentBlockDelta" in chunk
            and "text" in chunk["contentBlockDelta"]["delta"]
        ):
            current_text += chunk["contentBlockDelta"]["delta"]["text"]
            container.write(current_text)

        elif (
            "contentBlockDelta" in chunk
            and "toolUse" in chunk["contentBlockDelta"]["delta"]
        ):
            if tool_use_info:
                tool_input += chunk["contentBlockDelta"]["delta"]["toolUse"]["input"]

        elif "contentBlockStop" in chunk:
            if current_text:
                response["output"]["message"]["content"].append({"text": current_text})
                current_text = ""
            elif tool_use_info:
                if not tool_input:
                    tool_input = "{}"
                tool_use_info["input"] = json.loads(tool_input)
                response["output"]["message"]["content"].append(
                    {"toolUse": tool_use_info}
                )
                tool_use_info = None
                tool_input = ""

        elif "messageStop" in chunk:
            response["stopReason"] = chunk["messageStop"]["stopReason"]

        elif "metadata" in chunk:
            response["metadata"] = chunk["metadata"]

    return response


def process_user_message(prompt, messages):
    """Processes a user message, extracting text and files.

    Args:
        prompt (streamlit.chat_input): The user's chat input.
        messages (list): The list of messages in the chat history.
    """
    with st.chat_message("user"):
        st.write(prompt.text)

        user_content = [{"text": prompt.text}]

        for f in prompt.files:
            if (file_format := f.type.split("/")[1]) in format["image"]:
                user_content.append(
                    {
                        "image": {
                            "format": file_format,
                            "source": {"bytes": f.getvalue()},
                        }
                    }
                )
                st.image(f)

            elif (ext := os.path.splitext(f.name)[1][1:]) in format["document"]:
                name = str(uuid.uuid4())
                user_content.append(
                    {
                        "document": {
                            "format": ext,
                            "name": name,
                            "source": {"bytes": f.getvalue()},
                        }
                    }
                )
                user_content.append({"text": f"{name} is a renamed file of {f.name}."})
                st.write(f"'{name}' is a renamed file of '{f.name}'.")

        user_message = {"role": "user", "content": user_content}

        messages.append(user_message)


def get_messages_with_cache_point(messages_without_cache_point):
    messages_with_cache_point = []
    user_turns_processed = 0

    for message in reversed(messages_without_cache_point):
        m = copy.deepcopy(message)

        if message["role"] == "user" and user_turns_processed < 2:
            m["content"].append({"cachePoint": {"type": "default"}})
            user_turns_processed += 1

        messages_with_cache_point.append(m)

    messages_with_cache_point.reverse()

    return messages_with_cache_point


async def process_assistant_message(messages):
    """Processes an assistant message, calling the Bedrock API with MCP tools.

    Args:
        messages (list): The list of messages in the chat history.
    """
    with st.chat_message("assistant"):
        client = boto3.client("bedrock-runtime")

        # System prompt
        with open("config/system_prompt.md", mode="rt") as f:
            system_content = f.read()
        systen_message = [{"text": system_content}]

        # Cache setting(system)
        if st.session_state.enable_prompt_cache_system:
            systen_message.append({"cachePoint": {"type": "default"}})

        # Tools
        tools = [
            tool
            for tool in await st.session_state.mcp_tools.list_bedrock_tools()
            if tool["toolSpec"]["name"] in st.session_state.selected_tools
        ]
        # Cache setting(tool)
        if st.session_state.enable_prompt_cache_tools:
            tools.append({"cachePoint": {"type": "default"}})

        while True:
            stream_response = client.converse_stream(
                modelId=st.session_state.model_id,
                messages=get_messages_with_cache_point(messages),
                system=systen_message,
                toolConfig={"tools": tools},
            )

            response = process_streaming(stream_response)
            messages.append(response["output"]["message"])

            print(json.dumps(response["metadata"]))

            if response["stopReason"] == "tool_use":
                tool_requests = [
                    content
                    for content in response["output"]["message"]["content"]
                    if "toolUse" in content
                ]

                tool_result_message = {"role": "user", "content": []}

                for tool_request in tool_requests:
                    name = tool_request["toolUse"]["name"]
                    input = tool_request["toolUse"]["input"]

                    with st.expander(f"tool use: {name}"):
                        st.write(input)

                    tool_result = await st.session_state.mcp_tools.call_mcp_tool(
                        name, input
                    )

                    with st.expander(f"tool result: {name}"):
                        st.write(tool_result)

                    tool_result_content = {
                        "toolResult": {
                            "toolUseId": tool_request["toolUse"]["toolUseId"],
                            "content": [{"json": {"result": tool_result}}],
                        }
                    }
                    tool_result_message["content"].append(tool_result_content)

                messages.append(tool_result_message)

            else:
                break


@st.dialog("SYSTEM_PROMPT", width="large")
def show_system_prompt(system_prompt):
    st.write(
        "If you like it, please use it by reflecting it in SYSTEM_PROMPT of `config/system_prompt.md`."
    )

    st.markdown(f"""````
        {system_prompt}
        """)


async def generate_system_prompt():
    with st.spinner("Generating..."):
        tools = [
            tool
            for tool in await st.session_state.mcp_tools.list_bedrock_tools()
            if tool["toolSpec"]["name"] in st.session_state.selected_tools
        ]

        prompt = f"""
        You are an expert in generative AI, particularly large language models.  
        The user is struggling with creating appropriate prompts. Do your best to help them.  

        **User's concern:**  
            They are building an application that calls external tools, but the tools are not being invoked as expected.
            For example, when a user inputs, *"Tell me how to make curry,"* the AI attempts to answer using only its built-in capabilities. However, the expected behavior is for the AI to use the web search tool before responding.
            When the user explicitly inputs, *"Search the web for how to make curry and tell me,"* the AI behaves as expected. But the goal is for the AI to determine the appropriate tool to call even when the user does not explicitly specify it.
            
            (The application is a general-purpose AI chatbot, so the questions will not be limited to recipes but will cover a wide range of topics.)

            The following tools are defined:  

            <tool_definition>
            {json.dumps(tools, ensure_ascii=False)}
            </tool_definition>

            Generate a **system prompt** that ensures the tools are invoked appropriately as expected.

        Wrap the system prompt with `<SYSTEM_PROMPT></SYSTEM_PROMPT>` tags.  
            
        Do you understand the user's concern?  
        Think step by step before responding.
        """.strip()

        client = boto3.client("bedrock-runtime")
        response = client.converse(
            modelId=st.session_state.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )

        system_prompt = response["output"]["message"]["content"][0]["text"]

        show_system_prompt(system_prompt)


async def main():
    """Main function to run the Bedrock chat application."""

    st.title("Bedrock chat")

    with open("config/config.json", "r") as f:
        config = json.load(f)

    models = config["models"]

    def select_chat(chat_history_file):
        st.session_state.chat_history_file = chat_history_file

    with st.sidebar:
        with st.expander(":gear: config", expanded=True):
            st.selectbox("LLM model", models.keys(), key="model_id")
            st.checkbox("Enable prompt cache", value=True, key="enable_prompt_cache")

            if st.session_state.enable_prompt_cache:
                cache_support = models[st.session_state.model_id]["cache_support"]
                st.session_state.enable_prompt_cache_system = (
                    True if "system" in cache_support else False
                )
                st.session_state.enable_prompt_cache_tools = (
                    True if "tools" in cache_support else False
                )
                st.session_state.enable_prompt_cache_messages = (
                    True if "messages" in cache_support else False
                )
            else:
                st.session_state.enable_prompt_cache_system = False
                st.session_state.enable_prompt_cache_tools = False
                st.session_state.enable_prompt_cache_messages = False

            chat_history_dir = st.text_input(
                "chat_history_dir", value=config["chat_history_dir"]
            )
            st.text_input(
                "mcp_config_file",
                value=config["mcp_config_file"],
                key="mcp_config_file",
            )

            if "mcp_tools" not in st.session_state:
                st.session_state.mcp_tools = McpTools(
                    mcp_config_file=st.session_state.mcp_config_file
                )

            with st.spinner("Tool loading..."):
                bedrock_tools = await st.session_state.mcp_tools.list_bedrock_tools()

            multiselect_tools = [tool["toolSpec"]["name"] for tool in bedrock_tools]
            st.pills(
                "Tool",
                multiselect_tools,
                selection_mode="multi",
                default=multiselect_tools,
                key="selected_tools",
            )

            if st.button(
                "Generate System Prompt from mcp_config",
            ):
                await generate_system_prompt()

        st.button(
            "New Chat",
            on_click=select_chat,
            args=(f"{chat_history_dir}/{int(time.time())}.yaml",),
            use_container_width=True,
            type="primary",
        )

    if "chat_history_file" not in st.session_state:
        st.session_state["chat_history_file"] = (
            f"{chat_history_dir}/{int(time.time())}.yaml"
        )
    chat_history_file = st.session_state.chat_history_file

    if Path(chat_history_file).exists():
        with open(chat_history_file, mode="rt") as f:
            yaml_msg = yaml.safe_load(f)
            messages = yaml_msg
    else:
        messages = []

    for message in messages:
        with st.chat_message(message["role"]):
            for content in message["content"]:
                if "text" in content:
                    st.write(content["text"])
                elif "image" in content:
                    st.image(content["image"]["source"]["bytes"])
                elif "document" in content:
                    pass
                elif "toolUse" in content:
                    with st.expander("tool use"):
                        st.write(content)
                elif "toolResult" in content:
                    with st.expander("tool result"):
                        st.write(content)

    if prompt := st.chat_input(
        accept_file="multiple", file_type=format["image"] + format["document"]
    ):
        process_user_message(prompt, messages)

        await process_assistant_message(messages)

        with open(chat_history_file, mode="wt") as f:
            yaml.safe_dump(messages, f, allow_unicode=True)

    with st.sidebar:
        history_files = glob.glob(os.path.join(chat_history_dir, "*.yaml"))

        for h in sorted(history_files, reverse=True)[:20]:  # latest 20
            st.button(h, on_click=select_chat, args=(h,), use_container_width=True)


asyncio.run(main())
