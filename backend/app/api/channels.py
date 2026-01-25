"""Channel management API endpoints."""

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

from app.channels.manager import channel_manager
from app.channels.base import ChannelResponse

router = APIRouter(prefix="/channels")


class WebhookSetup(BaseModel):
    """Webhook setup request."""
    target_url: str


@router.get("")
async def list_channels() -> list[dict[str, Any]]:
    """List all configured channels and their status."""
    return channel_manager.list_channels()


@router.get("/{channel_name}")
async def get_channel(channel_name: str) -> dict[str, Any]:
    """Get a specific channel's status."""
    channel = channel_manager.get(channel_name)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_name}")
    return channel.get_status()


@router.post("/{channel_name}/start")
async def start_channel(channel_name: str) -> dict[str, str]:
    """Start a channel."""
    channel = channel_manager.get(channel_name)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_name}")
    
    await channel.start()
    return {"status": "started", "channel": channel_name}


@router.post("/{channel_name}/stop")
async def stop_channel(channel_name: str) -> dict[str, str]:
    """Stop a channel."""
    channel = channel_manager.get(channel_name)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_name}")
    
    await channel.stop()
    return {"status": "stopped", "channel": channel_name}


# === Webex Webhook Endpoint ===

@router.post("/webex/webhook")
async def webex_webhook(
    request: Request,
    x_spark_signature: str | None = Header(None),
) -> dict[str, Any]:
    """Handle incoming Webex webhook."""
    channel = channel_manager.get("webex")
    if not channel:
        raise HTTPException(status_code=404, detail="Webex channel not configured")
    
    # Get raw body for signature verification
    body = await request.body()
    payload = await request.json()
    
    # Verify webhook signature if secret is configured
    if hasattr(channel, 'webhook_secret') and channel.webhook_secret:
        if not x_spark_signature:
            raise HTTPException(status_code=401, detail="Missing signature")
        
        expected = hmac.new(
            channel.webhook_secret.encode(),
            body,
            hashlib.sha1
        ).hexdigest()
        
        if not hmac.compare_digest(expected, x_spark_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Handle the webhook
    response = await channel.handle_webhook(payload)
    
    if response:
        room_id = payload.get("data", {}).get("roomId")
        if room_id:
            await channel.send(room_id, response)
    
    return {"status": "ok"}


@router.post("/webex/setup")
async def setup_webex_webhook(setup: WebhookSetup) -> dict[str, Any]:
    """Create Webex webhook for receiving messages."""
    channel = channel_manager.get("webex")
    if not channel:
        raise HTTPException(status_code=404, detail="Webex channel not configured")
    
    webhook_id = await channel.create_webhook(setup.target_url)
    
    if webhook_id:
        return {"status": "created", "webhook_id": webhook_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to create webhook")


# === Test endpoint ===

class TestMessage(BaseModel):
    """Test message for debugging."""
    text: str
    chat_id: str = "test"


@router.post("/{channel_name}/test")
async def test_channel(channel_name: str, message: TestMessage) -> dict[str, Any]:
    """Send a test message through a channel."""
    channel = channel_manager.get(channel_name)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_name}")
    
    success = await channel.send(
        message.chat_id,
        ChannelResponse(text=message.text)
    )
    
    return {"status": "sent" if success else "failed", "channel": channel_name}
