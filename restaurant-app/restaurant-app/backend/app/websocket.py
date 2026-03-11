"""
websocket.py - WebSocket connection manager.

Two channels:
  - /ws/customer/{session_id}   → per-customer order updates
  - /ws/kitchen/{restaurant_id} → kitchen display for all orders

The manager keeps a dict of active connections and broadcasts
messages to the right channel.
"""

import json
import logging
from typing import Dict, List

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # customer connections: session_id → WebSocket
        self.customer_connections: Dict[str, WebSocket] = {}
        # kitchen connections: restaurant_id → [WebSocket, ...]
        self.kitchen_connections: Dict[str, List[WebSocket]] = {}

    # ── Customer ──────────────────────────────────────────────────────────────

    async def connect_customer(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.customer_connections[session_id] = websocket
        logger.info(f"Customer WS connected: {session_id}")

    def disconnect_customer(self, session_id: str):
        self.customer_connections.pop(session_id, None)
        logger.info(f"Customer WS disconnected: {session_id}")

    async def send_to_customer(self, session_id: str, event_type: str, data: dict):
        """Send a JSON event to a specific customer."""
        ws = self.customer_connections.get(session_id)
        if ws:
            try:
                await ws.send_text(json.dumps({"type": event_type, "data": data}))
            except Exception as e:
                logger.warning(f"Failed to send to customer {session_id}: {e}")
                self.disconnect_customer(session_id)

    # ── Kitchen ───────────────────────────────────────────────────────────────

    async def connect_kitchen(self, restaurant_id: str, websocket: WebSocket):
        await websocket.accept()
        self.kitchen_connections.setdefault(restaurant_id, []).append(websocket)
        logger.info(f"Kitchen WS connected: {restaurant_id}")

    def disconnect_kitchen(self, restaurant_id: str, websocket: WebSocket):
        conns = self.kitchen_connections.get(restaurant_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info(f"Kitchen WS disconnected: {restaurant_id}")

    async def broadcast_to_kitchen(self, restaurant_id: str, event_type: str, data: dict):
        """Broadcast a JSON event to all kitchen screens for a restaurant."""
        conns = self.kitchen_connections.get(restaurant_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps({"type": event_type, "data": data}))
            except Exception as e:
                logger.warning(f"Kitchen WS send failed: {e}")
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)


# Singleton used across the app
manager = ConnectionManager()
