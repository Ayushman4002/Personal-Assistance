import os
from fastapi import FastAPI
from pydantic import BaseModel,Field,field_validator

app = FastAPI(
    title = "Agentic Ai assistant",
    description = "Api for Research and Email Agents",
    version = "1.0.0"
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
        "status": " running",
        "message": "Agentic Ai API is running "
    }


from typing import Literal

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=200)
    agent: Literal["chat", "research", "email"] = "chat"

    action: Literal[
        "list_emails",
        "read_email",
        "draft_reply",
        "send_reply"
    ] | None = None

    email_id: str = ""
    user_instruction: str = ""

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot contain only whitespace")
        return value.strip()


from fastapi import HTTPException



@app.post("/chat")
def chat(request: ChatRequest):
    from research_agent import app as agent_graph

    try:
        result = agent_graph.invoke({
            "messages": [
                {"role": "user", "content": request.message}
            ],
            "selected_agent": request.agent,
            "action": request.action,
            "search_count": 0,
            "final_response": None,
            "route": "",
            "email_id": request.email_id,
            "email_content": "",
            "email_to": "",
            "email_subject": "",
            "user_instruction": request.user_instruction,
            "reply_draft": "",
            "confirmed": False
        })

        # Save the generated reply for explicit user approval
        if request.agent == "email" and request.action == "draft_reply":
            reply_draft = result.get("reply_draft", "")
            email_to = result.get("email_to", "")
            email_subject = result.get("email_subject", "")

            if not reply_draft or not email_to:
                raise HTTPException(
                    status_code=400,
                    detail="Could not generate a reply draft."
                )

            draft_id = save_pending_draft(
                email_id=request.email_id,
                email_to=email_to,
                email_subject=email_subject,
                reply_draft=reply_draft
            )

            return {
                "success": True,
                "draft_id": draft_id,
                "draft": reply_draft,
                "to": email_to,
                "subject": email_subject
            }

        response = result.get("final_response")

        if response is not None:
            response = response.model_dump()

        return {
            "agent": result.get("route", request.agent),
            "response": response or (
                result["messages"][-1].content
                if result.get("messages")
                else "No response generated."
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


class EmailSendRequest(BaseModel):
    draft_id: str


class EmailCancelRequest(BaseModel):
    draft_id: str

from uuid import uuid4
from datetime import datetime, timezone, timedelta

pending_drafts = {}

def save_pending_draft(
    email_id: str,
    email_to: str,
    email_subject: str,
    reply_draft: str
):
    draft_id = str(uuid4())

    pending_drafts[draft_id] = {
        "email_id": email_id,
        "to": email_to,
        "subject": email_subject,
        "body": reply_draft,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15)
    }

    return draft_id

@app.post("/email/send")
def send_email_endpoint(request: EmailSendRequest):
    from datetime import datetime, timezone
    import asyncio
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    draft = pending_drafts.get(request.draft_id)

    if not draft or draft["status"] != "pending":
        raise HTTPException(status_code=400, detail="Invalid or already processed draft")

    if datetime.now(timezone.utc) > draft["expires_at"]:
        draft["status"] = "expired"
        raise HTTPException(status_code=400, detail="Draft expired. Generate a new one.")

    if not draft["body"].strip() or not draft["to"].strip():
        raise HTTPException(status_code=400, detail="Draft or recipient is missing")

    # Prevent the same draft from being sent twice
    draft["status"] = "sending"

    async def send():
        transport = StdioTransport(
            command="python",
            args=[os.path.join(os.path.dirname(__file__), "mcp_server", "email_server.py")]
        )
        async with Client(transport) as client:
            return await client.call_tool("send_email", {
                "to": draft["to"],
                "subject": draft["subject"],
                "body": draft["body"]
            })

    try:
        result = asyncio.run(send())
        draft["status"] = "sent"
        return {"success": True, "message": "Email sent successfully."}
    except Exception as e:
        draft["status"] = "pending"
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/email/cancel")
def cancel_email_endpoint(request: EmailCancelRequest):
    draft = pending_drafts.get(request.draft_id)

    if not draft or draft["status"] != "pending":
        raise HTTPException(status_code=400, detail="Invalid or already processed draft")

    draft["status"] = "cancelled"
    return {"success": True, "message": "Email sending cancelled."}