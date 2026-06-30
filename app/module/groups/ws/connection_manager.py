import asyncio
import uuid
from collections import defaultdict

from fastapi import WebSocket


class GroupConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, dict[uuid.UUID, WebSocket]] = defaultdict(dict)

    async def connect(self, group_id: uuid.UUID, user_id: uuid.UUID, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[group_id][user_id] = ws

    def disconnect(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        group = self._connections.get(group_id, {})
        group.pop(user_id, None)
        if not group:
            self._connections.pop(group_id, None)

    async def broadcast(self, group_id: uuid.UUID, payload: dict) -> None:
        connections = list(self._connections.get(group_id, {}).values())
        if connections:
            await asyncio.gather(
                *[ws.send_json(payload) for ws in connections],
                return_exceptions=True,
            )

    def online_count(self, group_id: uuid.UUID) -> int:
        return len(self._connections.get(group_id, {}))


ws_manager = GroupConnectionManager()
