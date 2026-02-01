"""Stream utilities for SSE responses."""

import asyncio
import logging
from typing import AsyncGenerator, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")

async def keep_alive_generator(
    generator: AsyncGenerator[str, Any],
    interval_seconds: float = 5.0,
    ping_payload: str = 'data: {"type": "ping"}\n\n'
) -> AsyncGenerator[str, Any]:
    """Wrap an async generator to emit ping events if no data is received within interval.
    
    This ensures that SSE connections don't time out during long operations
    (like thinking, compiling, or deploying) where the upstream generator
    might be silent for a while.
    
    Args:
        generator: The source generator yielding SSE strings
        interval_seconds: How often to ping if silent (default 5s)
        ping_payload: The SSE event string to send as ping
        
    Yields:
        original items from generator, or ping_payload if idle
    """
    iterator = generator.__aiter__()
    
    while True:
        try:
            # Create a task for the next item
            future = asyncio.create_task(iterator.__anext__())
            
            while not future.done():
                try:
                    # Wait for the item with a timeout
                    item = await asyncio.wait_for(asyncio.shield(future), timeout=interval_seconds)
                    yield item
                    break # Break inner loop, continue outer to get next item
                except asyncio.TimeoutError:
                    # Timeout reached - emit ping and keep waiting for same future
                    # logger.debug("Stream silent, emitting keep-alive ping")
                    yield ping_payload
            
        except StopAsyncIteration:
            break
        except Exception as e:
            logger.error(f"Stream error: {e}")
            # Re-raise to close stream properly or let upstream handle it
            raise
