"""Telegram channel integration."""

import asyncio
import logging
from typing import Any

import httpx

from app.channels.base import Channel, ChannelMessage, ChannelResponse

logger = logging.getLogger(__name__)


class TelegramChannel(Channel):
    """Telegram Bot API integration."""
    
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.token = config.get("token", "")
        self.allowed_users: list[str] = config.get("allowed_users", [])
        self.api_base = f"https://api.telegram.org/bot{self.token}"
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._offset = 0
    
    @property
    def name(self) -> str:
        return "telegram"
    
    @property
    def display_name(self) -> str:
        return "Telegram"
    
    async def start(self) -> None:
        """Start polling for updates."""
        if not self.token:
            logger.warning("Telegram: No token configured")
            return
        
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram channel started")
    
    async def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram channel stopped")
    
    async def _poll_loop(self) -> None:
        """Long-poll for updates."""
        async with httpx.AsyncClient(timeout=60) as client:
            while self._running:
                try:
                    response = await client.get(
                        f"{self.api_base}/getUpdates",
                        params={"offset": self._offset, "timeout": 30},
                    )
                    data = response.json()
                    
                    if data.get("ok"):
                        for update in data.get("result", []):
                            self._offset = update["update_id"] + 1
                            await self._process_update(update)
                    else:
                        logger.error(f"Telegram API error: {data}")
                        await asyncio.sleep(5)
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Telegram poll error: {e}")
                    await asyncio.sleep(5)
    
    async def _process_update(self, update: dict) -> None:
        """Process a Telegram update."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        
        sender = message.get("from", {})
        sender_id = str(sender.get("id", ""))
        
        # Check allowed users
        if self.allowed_users and sender_id not in self.allowed_users:
            logger.debug(f"Telegram: Ignoring message from {sender_id}")
            return
        
        chat = message.get("chat", {})
        
        msg = ChannelMessage(
            id=str(message.get("message_id", "")),
            channel="telegram",
            sender_id=sender_id,
            sender_name=sender.get("first_name", "") + " " + sender.get("last_name", ""),
            text=message.get("text", "") or message.get("caption", ""),
            chat_id=str(chat.get("id", "")),
            chat_name=chat.get("title") or chat.get("first_name"),
            reply_to=str(message.get("reply_to_message", {}).get("message_id", "")) or None,
            raw=update,
        )
        
        await self.handle_message(msg)
    
    async def send(self, chat_id: str, response: ChannelResponse) -> bool:
        """Send a message to Telegram."""
        if not self.token:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                data = {
                    "chat_id": chat_id,
                    "text": response.text,
                }
                
                if response.parse_mode:
                    data["parse_mode"] = response.parse_mode
                elif "```" in response.text or "**" in response.text:
                    data["parse_mode"] = "Markdown"
                
                if response.reply_to:
                    data["reply_to_message_id"] = response.reply_to
                
                result = await client.post(
                    f"{self.api_base}/sendMessage",
                    json=data,
                )
                return result.json().get("ok", False)
                
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False
    
    def get_status(self) -> dict[str, Any]:
        status = super().get_status()
        status["running"] = self._running
        status["configured"] = bool(self.token)
        return status
