from app import app, db

<<<<<<< HEAD
# Ensure that the application context is active
=======
# # Ensure that the application context is active
>>>>>>> cd8f058 (rcr brought back)
with app.app_context():
    try:
        # Drop all tables
        db.drop_all()
        print("All tables dropped")

<<<<<<< HEAD
        # # Create all tables
=======
        # Create all tables
>>>>>>> cd8f058 (rcr brought back)
        db.create_all()
        print("Database initialized successfully.")

    except Exception as e:
        print(f"Error initializing database: {e}")
