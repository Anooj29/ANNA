"""Realtime payloads do not expose clinical detail to reception sessions."""
import asyncio
import json
import unittest

from backend.app.websocket import ConnectionManager


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, payload):
        self.messages.append(json.loads(payload))


class WebSocketVisibilityTests(unittest.TestCase):
    def test_role_filtered_event_payloads(self):
        manager = ConnectionManager()
        doctor, reception = FakeSocket(), FakeSocket()
        manager.active_connections = [doctor, reception]
        manager.roles = {doctor: "doctor", reception: "receptionist"}
        asyncio.run(manager.broadcast("task_created", {
            "task_id": 12, "patient_code": "ANP-123", "status": "queued",
            "instructions": "private clinical detail"}))
        self.assertIn("instructions", doctor.messages[0]["data"])
        self.assertNotIn("instructions", reception.messages[0]["data"])
        self.assertIn("event_id", reception.messages[0])
        asyncio.run(manager.broadcast("alert_created", {"message": "sensitive alert"}))
        self.assertEqual(len(reception.messages), 1)
        self.assertEqual(len(doctor.messages), 2)
