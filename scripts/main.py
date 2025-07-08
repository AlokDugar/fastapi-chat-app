from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Dict, Any, Optional
from datetime import timedelta
import json

from database import get_db, User, Room, Message, create_tables
from auth import (
    get_password_hash, verify_password, create_access_token, 
    get_current_user, get_admin_user, verify_token, ACCESS_TOKEN_EXPIRE_MINUTES
)
from websocket_manager import manager

# Create FastAPI app with minimal configuration to avoid Pydantic issues
app = FastAPI(
    title="Chat Application API", 
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()
    print("✅ Database tables created successfully!")

# Authentication endpoints
@app.post("/signup")
async def signup(user_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Create a new user account"""
    # Check if user already exists
    db_user = db.query(User).filter(
        (User.username == user_data["username"]) | (User.email == user_data["email"])
    ).first()
    
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data["password"])
    db_user = User(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=hashed_password,
        role=user_data.get("role", "user")
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "role": db_user.role,
        "created_at": db_user.created_at.isoformat()
    }

@app.post("/login")
async def login(credentials: Dict[str, str], db: Session = Depends(get_db)):
    """Login and get access token"""
    # Authenticate user
    user = db.query(User).filter(User.username == credentials["username"]).first()
    
    if not user or not verify_password(credentials["password"], user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat()
        }
    }

# Room management endpoints
@app.post("/rooms")
async def create_room(
    room_data: Dict[str, Any], 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new chat room"""
    db_room = Room(
        name=room_data["name"], 
        description=room_data.get("description")
    )
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    
    return {
        "id": db_room.id,
        "name": db_room.name,
        "description": db_room.description,
        "created_at": db_room.created_at.isoformat()
    }

@app.get("/rooms")
async def get_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all chat rooms"""
    rooms = db.query(Room).all()
    return [
        {
            "id": room.id,
            "name": room.name,
            "description": room.description,
            "created_at": room.created_at.isoformat()
        }
        for room in rooms
    ]

@app.get("/rooms/{room_id}/messages")
async def get_room_messages(
    room_id: int,
    limit: int = 50,
    cursor: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get messages from a specific room"""
    # Cursor-based pagination
    query = db.query(Message).filter(Message.room_id == room_id)
    
    if cursor:
        query = query.filter(Message.id < cursor)
    
    messages = query.order_by(desc(Message.id)).limit(limit).all()
    messages.reverse()  # Return in chronological order
    
    result = []
    for message in messages:
        result.append({
            "id": message.id,
            "content": message.content,
            "user_id": message.user_id,
            "room_id": message.room_id,
            "created_at": message.created_at.isoformat(),
            "sender": {
                "id": message.sender.id,
                "username": message.sender.username,
                "email": message.sender.email,
                "role": message.sender.role,
                "created_at": message.sender.created_at.isoformat()
            }
        })
    
    return result

# WebSocket endpoint for chat
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    room_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time chat"""
    # Verify JWT token
    token_data = verify_token(token)
    if not token_data:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Get user from database
    user = db.query(User).filter(User.username == token_data["username"]).first()
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Verify room exists
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return
    
    # Connect to room
    await manager.connect(websocket, room_id, {"username": user.username, "user_id": user.id})
    
    # Send recent messages to newly connected user
    recent_messages = db.query(Message).filter(
        Message.room_id == room_id
    ).order_by(desc(Message.id)).limit(20).all()
    
    recent_messages.reverse()  # Send in chronological order
    
    for message in recent_messages:
        message_data = {
            "id": message.id,
            "content": message.content,
            "username": message.sender.username,
            "user_id": message.user_id,
            "created_at": message.created_at.isoformat(),
            "type": "history"
        }
        await manager.send_personal_message(json.dumps(message_data), websocket)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Create and save message to database
            db_message = Message(
                content=message_data["content"],
                user_id=user.id,
                room_id=room_id
            )
            db.add(db_message)
            db.commit()
            db.refresh(db_message)
            
            # Broadcast message to all clients in the room
            broadcast_data = {
                "id": db_message.id,
                "content": db_message.content,
                "username": user.username,
                "user_id": user.id,
                "created_at": db_message.created_at.isoformat(),
                "type": "message"
            }
            
            await manager.broadcast_to_room(broadcast_data, room_id)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

# Admin endpoints
@app.get("/admin/users")
async def get_all_users(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """Get all users (admin only)"""
    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat()
        }
        for user in users
    ]

@app.get("/admin/analytics/messages-per-room")
async def get_messages_per_room(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """Get message count per room (admin only)"""
    from sqlalchemy import func
    
    result = db.query(
        Room.name,
        func.count(Message.id).label("message_count")
    ).outerjoin(Message).group_by(Room.id, Room.name).all()
    
    return [{"room_name": room.name, "message_count": room.message_count} for room in result]

@app.get("/admin/analytics/user-activity")
async def get_user_activity(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user)
):
    """Get user activity statistics (admin only)"""
    from sqlalchemy import func
    
    result = db.query(
        User.username,
        func.count(Message.id).label("messages_sent")
    ).outerjoin(Message).group_by(User.id, User.username).all()
    
    return [{"username": user.username, "messages_sent": user.messages_sent} for user in result]

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Chat API is running"}

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "FastAPI Chat Application",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
