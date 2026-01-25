"""Webex Teams channel integration."""

import asyncio
import logging
from typing import Any

import httpx

from app.channels.base import Channel, ChannelMessage, ChannelResponse

logger = logging.getLogger(__name__)


class WebexChannel(Channel):
    """Cisco Webex Teams integration via Bot API."""
    
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
        logger.info("Webex channel started")
    
    async def stop(self) -> None:
        """Stop the Webex channel."""
        self._running = False
        logger.info("Webex channel stopped")
    
    async def _get_bot_info(self) -> None:
        """Get bot's own ID to filter out own messages."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/people/me",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if response.status_code == 200:
                    self._bot_id = response.json().get("id")
                    logger.info(f"Webex bot ID: {self._bot_id}")
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
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/messages/{message_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Webex get message error: {e}")
        return None
    
    async def send(self, chat_id: str, response: ChannelResponse) -> bool:
        """Send a message to Webex."""
        if not self.token:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
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
                return result.status_code == 200
                
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
            async with httpx.AsyncClient() as client:
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
        return status
