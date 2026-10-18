"""Gestor de conexiones WebSocket agrupadas por sesion."""


class ConnectionManager:
    def __init__(self):
        self.connections = []

    async def connect(self, websocket, session_id, role, player_id=None):
        await websocket.accept()
        self.connections.append({
            "ws": websocket,
            "session_id": session_id,
            "role": role,
            "player_id": player_id,
        })

    def disconnect(self, websocket):
        self.connections = [c for c in self.connections if c["ws"] is not websocket]

    async def broadcast(self, session_id, builder):
        """builder(role, player_id) -> dict  (payload distinto por rol)."""
        stale = []
        for conn in list(self.connections):
            if conn["session_id"] != session_id:
                continue
            try:
                payload = builder(conn["role"], conn["player_id"])
                await conn["ws"].send_json(payload)
            except Exception:
                stale.append(conn["ws"])
        for ws in stale:
            self.disconnect(ws)
