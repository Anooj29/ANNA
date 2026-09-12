"""WebSocket connection manager for real-time hospital event broadcasting."""

from __future__ import annotations

import json
import logging
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("anna.websocket")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total active: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Total active: %d", len(self.active_connections))

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast an event payload to all connected clients."""
        payload = json.dumps({"event": event_type, "data": data})
        stale = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                stale.append(connection)
        for s in stale:
            self.disconnect(s)


ws_manager = ConnectionManager()
