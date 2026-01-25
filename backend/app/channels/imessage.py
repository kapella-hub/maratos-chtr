"""iMessage channel integration (macOS only via AppleScript)."""

import asyncio
import logging
import subprocess
from typing import Any

from app.channels.base import Channel, ChannelMessage, ChannelResponse

logger = logging.getLogger(__name__)


class IMessageChannel(Channel):
    """iMessage integration via AppleScript (macOS only)."""
    
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.allowed_senders: list[str] = config.get("allowed_senders", [])
        self.poll_interval: int = config.get("poll_interval", 5)
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._last_message_id: str | None = None
    
    @property
    def name(self) -> str:
        return "imessage"
    
    @property
    def display_name(self) -> str:
        return "iMessage"
    
    def _is_macos(self) -> bool:
        """Check if running on macOS."""
        import platform
        return platform.system() == "Darwin"
    
    async def start(self) -> None:
        """Start polling for new messages."""
        if not self._is_macos():
            logger.warning("iMessage: Only available on macOS")
            return
        
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("iMessage channel started")
    
    async def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("iMessage channel stopped")
    
    async def _poll_loop(self) -> None:
        """Poll for new iMessages."""
        while self._running:
            try:
                await self._check_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"iMessage poll error: {e}")
            
            await asyncio.sleep(self.poll_interval)
    
    async def _check_messages(self) -> None:
        """Check for new iMessages using AppleScript."""
        script = '''
        tell application "Messages"
            set latestChat to item 1 of chats
            set latestMessage to last item of messages of latestChat
            set senderId to handle of sender of latestMessage
            set msgText to text of latestMessage
            set msgId to id of latestMessage
            return msgId & "|||" & senderId & "|||" & msgText
        end tell
        '''
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|||")
                if len(parts) >= 3:
                    msg_id, sender_id, text = parts[0], parts[1], "|||".join(parts[2:])
                    
                    # Skip if already processed
                    if msg_id == self._last_message_id:
                        return
                    self._last_message_id = msg_id
                    
                    # Check allowed senders
                    if self.allowed_senders and sender_id not in self.allowed_senders:
                        return
                    
                    msg = ChannelMessage(
                        id=msg_id,
                        channel="imessage",
                        sender_id=sender_id,
                        sender_name=sender_id,
                        text=text,
                        chat_id=sender_id,
                    )
                    
                    await self.handle_message(msg)
                    
        except Exception as e:
            logger.debug(f"iMessage check error: {e}")
    
    async def send(self, chat_id: str, response: ChannelResponse) -> bool:
        """Send an iMessage."""
        if not self._is_macos():
            return False
        
        # Escape the text for AppleScript
        text = response.text.replace('\\', '\\\\').replace('"', '\\"')
        
        script = f'''
        tell application "Messages"
            set targetBuddy to buddy "{chat_id}" of service 1
            send "{text}" to targetBuddy
        end tell
        '''
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", script],
                capture_output=True,
            )
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"iMessage send error: {e}")
            return False
    
    def get_status(self) -> dict[str, Any]:
        status = super().get_status()
        status["running"] = self._running
        status["available"] = self._is_macos()
        return status
