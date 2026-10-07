import os
from email.mime.text import MIMEText
from fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

import base64
from bs4 import BeautifulSoup

mcp = FastMCP("Email Tools")

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

def get_gmail_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE, SCOPES
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE, SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

@mcp.tool
def read_email():

    service = get_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=5
    ).execute()

    messages = results.get("messages", [])

    if not messages:
        return "No emails found."

    emails = []

    for message in messages:

        email = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        headers = email.get("payload", {}).get("headers", [])

        data = {}

        for header in headers:
            data[header["name"]] = header["value"]

        emails.append({
        "id": message["id"],
        "from": data.get("From", ""),
        "subject": data.get("Subject", ""),
        "date": data.get("Date", "")
    })

    return str(emails)

@mcp.tool
def get_email(email_id: str):

    service = get_gmail_service()

    email = service.users().messages().get(
        userId="me",
        id=email_id,
        format="full"
    ).execute()

    payload = email.get("payload", {})
    headers = payload.get("headers", [])

    data = {}

    for header in headers:
        data[header["name"]] = header["value"]

    body_data = ""

    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                body_data = part.get("body", {}).get("data", "")
                break

        if not body_data:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    body_data = part.get("body", {}).get("data", "")
                    break
    else:
        body_data = payload.get("body", {}).get("data", "")

    if body_data:
        decoded_body = base64.urlsafe_b64decode(
            body_data + "=" * (-len(body_data) % 4)
        ).decode("utf-8", errors="ignore")

        soup = BeautifulSoup(decoded_body, "html.parser")
        body = soup.get_text("\n", strip=True)
    else:
        body = ""

    return str({
        "id": email_id,
        "from": data.get("From", ""),
        "to": data.get("To", ""),
        "subject": data.get("Subject", ""),
        "date": data.get("Date", ""),
        "body": body
    })

@mcp.tool
def send_email(to: str, subject: str, body: str):

    service = get_gmail_service()

    message = MIMEText(body)

    message["to"] = to
    message["subject"] = subject

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    result = service.users().messages().send(
        userId="me",
        body={"raw": raw_message}
    ).execute()

    return f"Email sent successfully. Message ID: {result['id']}"

if __name__ == "__main__":
    mcp.run()