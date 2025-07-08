from sqlalchemy.orm import Session
from database import SessionLocal, create_tables, User, Room
from auth import get_password_hash

def setup_database():
    create_tables()
    
    db = SessionLocal()
    
    try:
        admin_user = User(
            username="admin",
            email="admin@example.com",
            hashed_password=get_password_hash("admin123"),
            role="admin"
        )
        
        regular_user = User(
            username="user1",
            email="user1@example.com",
            hashed_password=get_password_hash("user123"),
            role="user"
        )
        
        existing_admin = db.query(User).filter(User.username == "admin").first()
        existing_user = db.query(User).filter(User.username == "user1").first()
        
        if not existing_admin:
            db.add(admin_user)
            print("Created admin user: admin/admin123")
        
        if not existing_user:
            db.add(regular_user)
            print("Created regular user: user1/user123")
        
        rooms_data = [
            {"name": "General", "description": "General discussion room"},
            {"name": "Tech Talk", "description": "Technology discussions"},
            {"name": "Random", "description": "Random conversations"}
        ]
        
        for room_data in rooms_data:
            existing_room = db.query(Room).filter(Room.name == room_data["name"]).first()
            if not existing_room:
                room = Room(name=room_data["name"], description=room_data["description"])
                db.add(room)
                print(f"Created room: {room_data['name']}")
        
        db.commit()
        print("Database setup completed successfully!")
        
    except Exception as e:
        print(f"Error setting up database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    setup_database()
