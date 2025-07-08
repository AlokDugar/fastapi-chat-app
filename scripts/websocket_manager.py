from typing import Dict, List
from fastapi import WebSocket
import json
from datetime import datetime

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_users: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user: dict):
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        
        self.connection_users[websocket] = user
        
        print(f"User {user['username']} connected to room {room_id}")

    def disconnect(self, websocket: WebSocket, room_id: int):
        if room_id in self.active_connections:
            if websocket in self.active_connections[room_id]:
                self.active_connections[room_id].remove(websocket)
                
                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]
        
        if websocket in self.connection_users:
            user = self.connection_users[websocket]
            del self.connection_users[websocket]
            print(f"User {user['username']} disconnected from room {room_id}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_room(self, message: dict, room_id: int):
        if room_id in self.active_connections:
            message_json = json.dumps(message)
            disconnected = []
            
            for connection in self.active_connections[room_id]:
                try:
                    await connection.send_text(message_json)
                except:
                    disconnected.append(connection)
            
            for connection in disconnected:
                self.disconnect(connection, room_id)

manager = ConnectionManager()
