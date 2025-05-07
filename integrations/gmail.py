import base64
from email.mime.text import MIMEText
from typing import Optional, List

from googleapiclient.errors import HttpError
from pydantic import BaseModel
from integrations import GoogleClient
from utils.decorators import async_threadpool
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


class GmailClient(GoogleClient):
    def __init__(self, creds):
        super().__init__(creds, service_name="gmail", version="v1")

    def _build_service(self):
        return build("gmail", "v1", credentials=self.creds)

    def _parse_message(self, msg_detail):
        message = {}
        msg_data = msg_detail["payload"]["headers"]
        for values in msg_data:
            name = values["name"]
            if name == "From":
                message["from"] = values["value"]
            elif name == "Subject":
                message["subject"] = values["value"]
            elif name == "Date":
                message["date"] = values["value"]
        print(msg_detail)
        if "parts" in msg_detail["payload"]:
            for part in msg_detail["payload"]["parts"]:
                try:
                    data = part["body"]["data"]
                    byte_code = base64.urlsafe_b64decode(data)

                    text = byte_code.decode("utf-8")
                    message["text"] = text
                except BaseException as error:
                    pass
        return message

    def _retrieve_full_messages(self, messages, user_id="me"):
        """
        Retrieve full details for a list of message IDs.

        Args:
            messages (list): List of message dictionaries containing message IDs
            user_id (str, optional): Gmail user ID. Defaults to "me".

        Returns:
            list: List of parsed message details
        """
        service = self._build_service()
        full_messages = []
        for msg in messages:
            msg_id = msg["id"]
            msg_detail = (
                service.users()
                .messages()
                .get(
                    userId=user_id,
                    id=msg_id,
                    format="full",  # or 'metadata' or 'raw', depending on what you want
                )
                .execute()
            )
            parsed_message = self._parse_message(msg_detail)
            full_messages.append(parsed_message)
        return full_messages

    def list_messages(self, max_results=10, user_id="me", include_message_payload=True):
        try:
            service = self._build_service()

            # Step 1: Get message IDs
            response = (
                service.users()
                .messages()
                .list(userId=user_id, maxResults=max_results)
                .execute()
            )
            messages = response.get("messages", [])
            if not include_message_payload:
                # If you just want IDs
                return {"messages": messages, "success": True}

            # Step 2: Retrieve full message details
            full_messages = self._retrieve_full_messages(messages, user_id)
            return {"messages": full_messages, "success": True}
        except HttpError as error:
            return {"error": f"An error occurred: {error}", "success": False}

    @async_threadpool
    async def list_messages_async(
        self, max_results=10, user_id="me", include_message_payload=True
    ):
        """Async version of list_messages."""
        return self.list_messages(max_results, user_id, include_message_payload)

    def search_messages(self, query, user_id="me", max_results=10):
        try:
            service = self._build_service()
            response = (
                service.users()
                .messages()
                .list(userId=user_id, q=query, maxResults=max_results)
                .execute()
            )
            messages = response.get("messages", [])
            full_messages = self._retrieve_full_messages(messages, user_id)
            return {"messages": full_messages, "success": True}
        except HttpError as error:
            return {"error": f"An error occurred: {error}", "success": False}

    @async_threadpool
    async def search_messages_async(self, query, user_id="me", max_results=10):
        """Async version of search_messages."""
        return self.search_messages(query, user_id, max_results)

    def send_message(self, to, subject, message_text, user_id="me", attachments=None):
        try:
            service = self._build_service()

            if attachments:
                message = self._create_message_with_attachments(
                    to, subject, message_text, attachments
                )
            else:
                message = MIMEText(message_text)
                message["to"] = to
                message["subject"] = subject

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            send_message = (
                service.users()
                .messages()
                .send(userId=user_id, body={"raw": raw_message})
                .execute()
            )

            return {"message": send_message, "success": True}
        except HttpError as error:
            return {"error": f"An error occurred: {error}", "success": False}

    @async_threadpool
    async def send_message_async(
        self, to, subject, message_text, user_id="me", attachments=None
    ):
        """Async version of send_message."""
        return self.send_message(to, subject, message_text, user_id, attachments)

    def create_draft(self, to, subject, message_text, user_id="me", attachments=None):
        try:
            service = self._build_service()

            if attachments:
                message = self._create_message_with_attachments(
                    to, subject, message_text, attachments
                )
            else:
                message = MIMEText(message_text)
                message["to"] = to
                message["subject"] = subject

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            draft_body = {"message": {"raw": raw_message}}

            draft = (
                service.users()
                .drafts()
                .create(userId=user_id, body=draft_body)
                .execute()
            )

            return {"draft": draft, "success": True}
        except HttpError as error:
            return {"error": f"An error occurred: {error}", "success": False}

    @async_threadpool
    async def create_draft_async(
        self, to, subject, message_text, user_id="me", attachments=None
    ):
        """Async version of create_draft."""
        return self.create_draft(to, subject, message_text, user_id, attachments)

    def list_labels(self, user_id="me"):
        try:
            service = self._build_service()
            response = service.users().labels().list(userId=user_id).execute()
            return {"labels": response.get("labels", []), "success": True}
        except HttpError as error:
            return {"error": f"An error occurred: {error}", "success": False}

    @async_threadpool
    async def list_labels_async(self, user_id="me"):
        """Async version of list_labels."""
        return self.list_labels(user_id)

    def reply_message(
        self, message_id, to, subject, message_text, thread_id, user_id="me"
    ):
        try:
            service = self._build_service()
            message = MIMEText(message_text)
            message["to"] = to
            message["subject"] = subject
            message["In-Reply-To"] = message_id
            message["References"] = message_id
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            body = {"raw": raw_message, "threadId": thread_id}

            sent_message = (
                service.users().messages().send(userId=user_id, body=body).execute()
            )

            return {"message": sent_message, "success": True}
        except HttpError as error:
            return {"error": f"An error occurred: {error}", "success": False}

    @async_threadpool
    async def reply_message_async(
        self, message_id, to, subject, message_text, thread_id, user_id="me"
    ):
        """Async version of reply_message."""
        return self.reply_message(
            message_id, to, subject, message_text, thread_id, user_id
        )

    def _create_message_with_attachments(self, to, subject, body_text, attachments):
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body_text, "plain"))

        for file_path in attachments:
            filename = file_path.split("/")[-1]
            with open(file_path, "rb") as f:
                mime_base = MIMEBase("application", "octet-stream")
                mime_base.set_payload(f.read())
                encoders.encode_base64(mime_base)
                mime_base.add_header(
                    "Content-Disposition", f'attachment; filename="{filename}"'
                )
                message.attach(mime_base)

        return message


class SendMessageRequest(BaseModel):
    user_id: str
    to: str
    subject: str
    message_text: str
    attachments: Optional[List[str]] = None  # optional file paths


class CreateDraftRequest(BaseModel):
    user_id: str
    to: str
    subject: str
    message_text: str
    attachments: Optional[List[str]] = None


class ReplyMessageRequest(BaseModel):
    user_id: str
    message_id: str
    to: str
    subject: str
    message_text: str
    thread_id: str
