
from sqlalchemy.orm import Session
from database import SessionLocal, User, Room, Message
from datetime import datetime

def add_test_messages():
    db = SessionLocal()
    
    try:
        room = db.query(Room).filter(Room.name == "General").first()
        if not room:
            room = Room(name="General", description="General discussion room")
            db.add(room)
            db.commit()
            db.refresh(room)
        
        admin_user = db.query(User).filter(User.username == "admin").first()
        regular_user = db.query(User).filter(User.username == "user1").first()
        
        if not admin_user or not regular_user:
            print("Default users not found. Run setup_database.py first!")
            return
        
        test_messages = [
            {"content": "Hello everyone! Welcome to the chat!", "user": admin_user},
            {"content": "Thanks! Great to be here.", "user": regular_user},
            {"content": "How is everyone doing today?", "user": admin_user},
            {"content": "Doing well! This chat app is pretty cool.", "user": regular_user},
            {"content": "Yes, it has real-time messaging with WebSockets!", "user": admin_user},
            {"content": "And JWT authentication for security.", "user": regular_user},
            {"content": "Plus message history and pagination.", "user": admin_user},
        ]
        
        for msg_data in test_messages:
            existing = db.query(Message).filter(
                Message.content == msg_data["content"],
                Message.user_id == msg_data["user"].id,
                Message.room_id == room.id
            ).first()
            
            if not existing:
                message = Message(
                    content=msg_data["content"],
                    user_id=msg_data["user"].id,
                    room_id=room.id
                )
                db.add(message)
        
        db.commit()
        
        total_messages = db.query(Message).filter(Message.room_id == room.id).count()
        print(f"Test messages added! Total messages in '{room.name}': {total_messages}")
        
    except Exception as e:
        print(f"Error adding test messages: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_test_messages()
