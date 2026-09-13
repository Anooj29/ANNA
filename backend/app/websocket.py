"""WebSocket connection manager for real-time hospital event broadcasting."""

from __future__ import annotations

import json
import logging
import datetime as dt
import uuid
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("anna.websocket")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.roles: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, role: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.roles[websocket] = role
        logger.info("WebSocket client connected. Total active: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            self.roles.pop(websocket, None)
            logger.info("WebSocket client disconnected. Total active: %d", len(self.active_connections))

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast an event payload to all connected clients."""
        stale = []
        for connection in self.active_connections:
            role = self.roles.get(connection)
            if role == "receptionist" and event_type not in {
                "patient_admitted", "patient_discharged", "patient_updated", "bed_updated",
                "task_created", "task_updated", "checkup_completed"
            }:
                continue
            visible_data = data
            if role == "receptionist" and event_type in {"checkup_completed", "task_created", "task_updated"}:
                visible_data = {key: data.get(key) for key in
                                ("task_id", "patient_code", "patient_name", "bed_number", "status", "priority")
                                if key in data}
            payload = json.dumps({"event": event_type, "data": visible_data,
                                  "event_id": str(uuid.uuid4()), "emitted_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            try:
                await connection.send_text(payload)
            except Exception:
                stale.append(connection)
        for s in stale:
            self.disconnect(s)


ws_manager = ConnectionManager()
