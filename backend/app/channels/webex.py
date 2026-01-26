"""Webex Teams channel integration."""

import asyncio
import logging
from typing import Any

import httpx

from app.channels.base import Channel, ChannelMessage, ChannelResponse

logger = logging.getLogger(__name__)


class WebexChannel(Channel):
    """Cisco Webex Teams integration via Bot API.

    Supports two modes:
    - Webhook mode: Webex sends messages to your public URL (requires public server)
    - Polling mode: Bot periodically checks for new messages (works behind firewalls)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.token = config.get("token", "")  # Bot access token
        self.webhook_secret = config.get("webhook_secret", "")
        self.allowed_users: list[str] = config.get("allowed_users", [])
        self.allowed_rooms: list[str] = config.get("allowed_rooms", [])
        self.api_base = "https://webexapis.com/v1"
        self._running = False
        self._webhook_id: str | None = None
        self._bot_id: str | None = None
        self._poll_task: asyncio.Task | None = None
        self._last_message_id: str | None = None
        self._poll_interval: int = config.get("poll_interval", 3)  # seconds
        self._use_polling: bool = config.get("use_polling", True)  # Default to polling for corporate
        self._verify_ssl: bool = config.get("verify_ssl", False)  # Disable for corporate proxies
    
    @property
    def name(self) -> str:
        return "webex"
    
    @property
    def display_name(self) -> str:
        return "Webex"
    
    async def start(self) -> None:
        """Start the Webex channel."""
        if not self.token:
            logger.warning("Webex: No token configured")
            return

        # Get bot info
        await self._get_bot_info()

        self._running = True

        # Start polling if enabled (default for corporate environments)
        if self._use_polling and self._bot_id:
            self._poll_task = asyncio.create_task(self._poll_messages())
            logger.info(f"Webex channel started (polling every {self._poll_interval}s)")
        else:
            logger.info("Webex channel started (webhook mode)")

    async def stop(self) -> None:
        """Stop the Webex channel."""
        self._running = False

        # Cancel polling task
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        logger.info("Webex channel stopped")
    
    async def _get_bot_info(self) -> None:
        """Get bot's own ID to filter out own messages."""
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                response = await client.get(
                    f"{self.api_base}/people/me",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    self._bot_id = data.get("id")
                    logger.info(f"Webex bot ID: {self._bot_id}, name: {data.get('displayName')}")
                else:
                    logger.error(f"Webex get bot info failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Webex get bot info error: {e}")
    
    async def handle_webhook(self, payload: dict) -> ChannelResponse | None:
        """Handle incoming webhook from Webex.
        
        Called by the API endpoint when Webex sends a webhook.
        """
        if not self._running:
            return None
        
        resource = payload.get("resource")
        event = payload.get("event")
        data = payload.get("data", {})
        
        # Only handle new messages
        if resource != "messages" or event != "created":
            return None
        
        message_id = data.get("id")
        if not message_id:
            return None
        
        # Get full message details (webhook only contains ID)
        message_data = await self._get_message(message_id)
        if not message_data:
            return None
        
        sender_id = message_data.get("personId", "")
        
        # Skip own messages
        if sender_id == self._bot_id:
            return None
        
        # Check allowed users/rooms
        room_id = message_data.get("roomId", "")
        if self.allowed_users and sender_id not in self.allowed_users:
            if self.allowed_rooms and room_id not in self.allowed_rooms:
                return None
        
        msg = ChannelMessage(
            id=message_id,
            channel="webex",
            sender_id=sender_id,
            sender_name=message_data.get("personEmail", "").split("@")[0],
            text=message_data.get("text", ""),
            chat_id=room_id,
            chat_name=message_data.get("roomType"),
            raw=payload,
        )
        
        # Handle via the registered handler
        if self._handler:
            return await self._handler(msg)
        
        return None
    
    async def _get_message(self, message_id: str) -> dict | None:
        """Get full message details from Webex API."""
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                response = await client.get(
                    f"{self.api_base}/messages/{message_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Webex get message error: {e}")
        return None

    async def _poll_messages(self) -> None:
        """Poll for new messages (for corporate environments without webhooks)."""
        logger.info("Webex polling started")

        while self._running:
            try:
                await self._check_new_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Webex poll error: {e}")

            await asyncio.sleep(self._poll_interval)

        logger.info("Webex polling stopped")

    async def _check_new_messages(self) -> None:
        """Check for new direct messages to the bot."""
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                # Get direct messages to the bot
                params = {"max": 10}

                response = await client.get(
                    f"{self.api_base}/messages/direct",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params=params,
                    timeout=10.0,
                )

                if response.status_code != 200:
                    if response.status_code == 401:
                        logger.error("Webex: Invalid token")
                    return

                messages = response.json().get("items", [])

                # Process new messages (newest first, so reverse)
                for msg in reversed(messages):
                    msg_id = msg.get("id")

                    # Skip if we've seen this message
                    if self._last_message_id and msg_id <= self._last_message_id:
                        continue

                    # Skip own messages
                    if msg.get("personId") == self._bot_id:
                        continue

                    # Update last seen
                    self._last_message_id = msg_id

                    # Process the message
                    await self._process_message(msg)

        except httpx.TimeoutException:
            logger.debug("Webex poll timeout")
        except Exception as e:
            logger.error(f"Webex check messages error: {e}")

    async def _process_message(self, message_data: dict) -> None:
        """Process a single message from polling."""
        sender_id = message_data.get("personId", "")
        room_id = message_data.get("roomId", "")

        # Check allowed users/rooms
        if self.allowed_users and sender_id not in self.allowed_users:
            if self.allowed_rooms and room_id not in self.allowed_rooms:
                return

        msg = ChannelMessage(
            id=message_data.get("id", ""),
            channel="webex",
            sender_id=sender_id,
            sender_name=message_data.get("personEmail", "").split("@")[0],
            text=message_data.get("text", ""),
            chat_id=room_id,
            chat_name=message_data.get("roomType"),
            raw=message_data,
        )

        logger.info(f"Webex message from {msg.sender_name}: {msg.text[:50]}...")

        # Handle via the registered handler
        if self._handler:
            response = await self._handler(msg)
            if response:
                await self.send(room_id, response)
    
    async def send(self, chat_id: str, response: ChannelResponse) -> bool:
        """Send a message to Webex."""
        if not self.token:
            return False

        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                data = {
                    "roomId": chat_id,
                    "text": response.text,
                }

                # Webex supports markdown
                if "```" in response.text or "**" in response.text:
                    data["markdown"] = response.text

                result = await client.post(
                    f"{self.api_base}/messages",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json=data,
                )
                if result.status_code == 200:
                    logger.info(f"Webex message sent to {chat_id}")
                    return True
                else:
                    logger.error(f"Webex send failed: {result.status_code} {result.text}")
                    return False

        except Exception as e:
            logger.error(f"Webex send error: {e}")
            return False
    
    async def create_webhook(self, target_url: str) -> str | None:
        """Create a webhook for receiving messages.

        Call this once during setup to register the webhook with Webex.
        """
        if not self.token:
            return None

        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                # First, delete any existing webhooks
                list_response = await client.get(
                    f"{self.api_base}/webhooks",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if list_response.status_code == 200:
                    for webhook in list_response.json().get("items", []):
                        await client.delete(
                            f"{self.api_base}/webhooks/{webhook['id']}",
                            headers={"Authorization": f"Bearer {self.token}"},
                        )
                
                # Create new webhook
                result = await client.post(
                    f"{self.api_base}/webhooks",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={
                        "name": "MaratOS",
                        "targetUrl": target_url,
                        "resource": "messages",
                        "event": "created",
                        "secret": self.webhook_secret or None,
                    },
                )
                
                if result.status_code == 200:
                    webhook_data = result.json()
                    self._webhook_id = webhook_data.get("id")
                    logger.info(f"Webex webhook created: {self._webhook_id}")
                    return self._webhook_id
                else:
                    logger.error(f"Webex webhook creation failed: {result.text}")
                    
        except Exception as e:
            logger.error(f"Webex webhook error: {e}")
        
        return None
    
    def get_status(self) -> dict[str, Any]:
        status = super().get_status()
        status["running"] = self._running
        status["configured"] = bool(self.token)
        status["webhook_id"] = self._webhook_id
        status["bot_id"] = self._bot_id
        status["mode"] = "polling" if self._use_polling else "webhook"
        status["polling_active"] = self._poll_task is not None and not self._poll_task.done()
        status["poll_interval"] = self._poll_interval
        return status
