
import asyncio
import os
import ast
from typing import TypedDict, Annotated

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from pydantic import BaseModel, Field


load_dotenv()


# --------------------------------------------------
# MCP SERVER PATHS
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

server_path = os.path.join(
    BASE_DIR,
    "mcp_server",
    "server.py"
)

email_server_path = os.path.join(
    BASE_DIR,
    "mcp_server",
    "email_server.py"
)


# --------------------------------------------------
# STATE
# --------------------------------------------------

class ResearchState(TypedDict):
    messages: Annotated[list, add_messages]
    search_count: int
    final_response: "NewsResponse | None"
    route: str
    selected_agent: str
    email_id: str
    email_content: str
    email_to: str
    email_subject: str
    user_instruction: str
    reply_draft: str
    confirmed: bool
    action: str | None


# --------------------------------------------------
# RESEARCH RESPONSE MODELS
# --------------------------------------------------

class NewsItem(BaseModel):
    title: str = Field(description="Title of the news")
    summary: str = Field(description="Short summary of the news")
    source_url: str = Field(description="URL of the source")


class NewsResponse(BaseModel):
    news: list[NewsItem]


# --------------------------------------------------
# LLM
# --------------------------------------------------

base_llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0
)


system_message = SystemMessage(
    content="""
You are an AI and Technology Research Agent.

You have exactly one tool available: search_web.

When the user asks for current, latest, recent, or today's
AI or technology information, use search_web.

Never call open_file, browser.search, or any other tool.

Do not open URLs yourself.
Use only the search_web tool.

Do not invent information or sources.

If the question is normal conversation, do not search.
Respond naturally to messages such as:
"Hey, my name is Ayush".
"""
)


# --------------------------------------------------
# EMAIL SEND NODE
# --------------------------------------------------

def send_node(state: ResearchState):
    if state.get("confirmed") is not True:
        return {
            "messages": [{
                "role": "assistant",
                "content": "Email not sent. Explicit confirmation is required."
            }]
        }

    if not state.get("reply_draft", "").strip():
        return {
            "messages": [{
                "role": "assistant",
                "content": "Email not sent. No reply draft is available."
            }]
        }

    if not state.get("email_to", "").strip():
        return {
            "messages": [{
                "role": "assistant",
                "content": "Email not sent. No recipient is available."
            }]
        }

    async def run():
        transport = StdioTransport(
            command="python",
            args=[email_server_path]
        )

        mcp_client = Client(transport)

        async with mcp_client:
            return await mcp_client.call_tool(
                "send_email",
                {
                    "to": state["email_to"],
                    "subject": state["email_subject"],
                    "body": state["reply_draft"]
                }
            )

    result = asyncio.run(run())

    return {
        "messages": [{
            "role": "assistant",
            "content": str(result)
        }]
    }

# --------------------------------------------------
# EMAIL REPLY NODE
# --------------------------------------------------

def reply_node(state: ResearchState):
    email_content = state.get("email_content", "").strip()
    user_instruction = state.get("user_instruction", "").strip()

    if not email_content:
        message = "No email content available. Please select an email first."
        return {
            "reply_draft": "",
            "messages": [{"role": "assistant", "content": message}]
        }

    if not user_instruction:
        message = "Please provide instructions for the reply."
        return {
            "reply_draft": "",
            "messages": [{"role": "assistant", "content": message}]
        }

    reply = generate_reply(email_content, user_instruction)

    return {
        "reply_draft": reply,
        "messages": [
            {"role": "assistant", "content": reply}
        ]
    }

# --------------------------------------------------
# GET EMAIL NODE
# --------------------------------------------------

def email_node(state: ResearchState):

    async def run():

        transport = StdioTransport(
            command="python",
            args=[email_server_path]
        )

        mcp_client = Client(transport)

        async with mcp_client:

            result = await mcp_client.call_tool(
                "get_email",
                {
                    "email_id": state["email_id"]
                }
            )

            content = ""

            if hasattr(result, "content"):
                for item in result.content:
                    if hasattr(item, "text"):
                        content += item.text
                    else:
                        content += str(item)
            else:
                content = str(result)

            return content

    email_content = asyncio.run(run())

    email_data = ast.literal_eval(email_content)

    sender = email_data["from"]

    if "<" in sender and ">" in sender:
        sender = sender.split("<")[1].split(">")[0]

    return {
        "email_content": email_content,
        "email_to": sender,
        "email_subject": "Re: " + email_data["subject"]
    }

# --------------------------------------------------
# GENERATE EMAIL REPLY
# --------------------------------------------------

def read_emails_node(state: ResearchState):
    async def run():
        transport = StdioTransport(
            command="python",
            args=[email_server_path]
        )

        mcp_client = Client(transport)

        async with mcp_client:
            result = await mcp_client.call_tool("read_email", {})

            if hasattr(result, "content"):
                return "".join(
                    item.text if hasattr(item, "text") else str(item)
                    for item in result.content
                )

            return str(result)

    email_list = asyncio.run(run())

    return {
        "messages": [
            {
                "role": "assistant",
                "content": email_list
            }
        ]
    }

def generate_reply(email_content: str, user_instruction: str):

    prompt = f"""
You are an email assistant.

Read the email below and write a professional reply
based on the user's instruction.

Email:
{email_content}

User instruction:
{user_instruction}

Rules:
- Write only the reply body.
- Be professional and natural.
- Do not invent information.
- Follow the user's instruction exactly.
"""

    response = base_llm.invoke(prompt)

    return response.content


def llm_node(state: ResearchState):

    async def run():

        transport = StdioTransport(
            command="python",
            args=[server_path]
        )

        mcp_client = Client(transport)

        async with mcp_client:

            tools = await mcp_client.list_tools()

            tool = tools[0]

            llm_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }

            llm_with_tools = base_llm.bind_tools(
                [llm_tool],
                tool_choice="auto"
            )

            messages = [system_message] + state["messages"]

            response = llm_with_tools.invoke(messages)

            return response

    response = asyncio.run(run())

    return {
        "messages": [response]
    }

# --------------------------------------------------
# RESEARCH TOOLS NODE
# --------------------------------------------------

def tools_node(state: ResearchState):

    async def run():

        transport = StdioTransport(
            command="python",
            args=[server_path]
        )

        mcp_client = Client(transport)

        async with mcp_client:

            last_message = state["messages"][-1]

            tool_messages = []

            for tool_call in last_message.tool_calls:

                result = await mcp_client.call_tool(
                    tool_call["name"],
                    tool_call["args"]
                )

                content = ""

                if hasattr(result, "content"):
                    for item in result.content:
                        if hasattr(item, "text"):
                            content += item.text
                        else:
                            content += str(item)
                else:
                    content = str(result)

                tool_messages.append(
                    ToolMessage(
                        content=content,
                        tool_call_id=tool_call["id"]
                    )
                )

            return tool_messages

    tool_messages = asyncio.run(run())

    return {
        "messages": tool_messages,
        "search_count": state["search_count"] + 1
    }


# --------------------------------------------------
# RESEARCH ROUTING
# --------------------------------------------------

def should_continue(state: ResearchState):

    last_message = state["messages"][-1]

    if last_message.tool_calls:

        if state["search_count"] >= 3:
            return "final_response"

        return "tools"

    return "final_response"

# --------------------------------------------------
# FINAL RESEARCH RESPONSE
# --------------------------------------------------

def final_response_node(state: ResearchState):

    search_results = []

    for message in state["messages"]:
        if isinstance(message, ToolMessage):
            search_results.append(message.content)

    research_data = "\n\n".join(search_results)

    prompt = f"""
Based on the following search results, return exactly
10 AI and technology news items.

Return ONLY valid JSON in this format:

{{
    "news": [
        {{
            "title": "News title",
            "summary": "Short summary",
            "source_url": "Source URL"
        }}
    ]
}}

Do not use any tools.
Do not invent information.

Search Results:
{research_data}
"""

    response = base_llm.invoke(prompt)

    final_response = NewsResponse.model_validate_json(
        response.content
    )

    return {
        "final_response": final_response
    }


# --------------------------------------------------
# ROUTER NODE
# --------------------------------------------------

def router_node(state: ResearchState):
    selected_agent = state.get("selected_agent", "chat")
    action = state.get("action")

    if selected_agent == "email":
        if action in {
            "list_emails",
            "read_email",
            "draft_reply",
            "send_reply"
        }:
            return {"route": action}

        return {"route": "list_emails"}

    if selected_agent == "research":
        return {"route": "research"}

    return {"route": "normal"}

# --------------------------------------------------
# NORMAL CHAT NODE
# --------------------------------------------------

def normal_llm_node(state: ResearchState):

    response = base_llm.invoke(state["messages"])

    return {
        "messages": [response]
    }


# --------------------------------------------------
# ROUTER DECISION
# --------------------------------------------------

def route_decision(state: ResearchState):
    route = state.get("route", "normal")

    if route in {
        "list_emails",
        "read_email",
        "draft_reply",
        "send_reply"
    }:
        return route

    if route == "research":
        return "research"

    return "normal"

def email_action_node(state: ResearchState):
    user_message = state["messages"][-1].content.strip().lower()

    if any(word in user_message for word in [
        "latest emails", "show emails", "list emails",
        "inbox", "recent emails", "check emails"
    ]):
        return {"route": "read_emails"}

    if any(word in user_message for word in [
        "reply", "respond", "draft a response",
        "write a response"
    ]):
        return {"route": "read_email"}

    return {"route": "read_email"}

def draft_reply_node(state: ResearchState):
    return reply_node(state)
# --------------------------------------------------
# BUILD LANGGRAPH
# --------------------------------------------------

graph = StateGraph(ResearchState)

graph.add_node("router", router_node)
graph.add_node("normal_llm", normal_llm_node)
graph.add_node("llm", llm_node)


graph = StateGraph(ResearchState)

# Register nodes
graph.add_node("router", router_node)
graph.add_node("normal_llm", normal_llm_node)
graph.add_node("llm", llm_node)
graph.add_node("tools", tools_node)
graph.add_node("read_emails", read_emails_node)
graph.add_node("email", email_node)
graph.add_node("reply", reply_node)
graph.add_node("send", send_node)
graph.add_node("final_response", final_response_node)

# Start and main routing
graph.add_edge(START, "router")

graph.add_conditional_edges(
    "router",
    route_decision,
    {
        "normal": "normal_llm",
        "research": "llm",
        "list_emails": "read_emails",
        "read_email": "email",
        "draft_reply": "email",
        "send_reply": "send"
    }
)

# List emails
graph.add_edge("read_emails", END)

# Read an email or continue to draft a reply
graph.add_conditional_edges(
    "email",
    lambda state: state.get("action"),
    {
        "read_email": END,
        "draft_reply": "reply"
    }
)

# Draft only; never send automatically
graph.add_edge("reply", END)

# Chat workflow
graph.add_edge("normal_llm", END)

# Research workflow
graph.add_conditional_edges(
    "llm",
    should_continue,
    {
        "tools": "tools",
        "final_response": "final_response"
    }
)

graph.add_edge("tools", "llm")
graph.add_edge("final_response", END)

# Compile
app = graph.compile()
