"""
Thread-safe and asynchronous WebSocket Connection Manager for ISAAC.

Provides:
- Active WebSocket client connection tracking
- Asynchronous broadcasting of real-time telemetry and ML inference results
- Safe cross-thread dispatching (e.g., from simulator background threads)
- Disconnection cleanup and error resilience
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect

from .logger import logger


class ConnectionManager:
    """Manages active WebSocket connections and payload broadcasting."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store reference to the main asyncio event loop."""
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket from active registry."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket) -> None:
        """Send a JSON payload to a specific connected client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Error sending personal message to WebSocket client: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast a JSON payload asynchronously to all active connected clients."""
        if not self.active_connections:
            return

        dead_connections: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket client: {e}. Marking for removal.")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    def broadcast_sync(self, message: Dict[str, Any]) -> None:
        """
        Thread-safe synchronous broadcast entry point for background worker threads
        (e.g., SimulationEngine threads).
        """
        if not self.active_connections:
            return

        try:
            loop = self._loop or asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
            else:
                loop.run_until_complete(self.broadcast(message))
        except RuntimeError:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.broadcast(message))
                loop.close()
            except Exception as err:
                logger.warning(f"Could not broadcast sync payload to WebSocket clients: {err}")
        except Exception as err:
            logger.warning(f"Unexpected error in broadcast_sync: {err}")


# Global Singleton & Alias
WebSocketManager = ConnectionManager
manager = ConnectionManager()


def get_ws_manager() -> ConnectionManager:
    """Dependency / getter for ConnectionManager singleton."""
    return manager
