from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
import bcrypt

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB Connection
client = MongoClient("mongodb://localhost:27017/")
db = client["user_auth_db"]
users_collection = db["users"]

class User(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: User):
    if users_collection.find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed_pw = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    users_collection.insert_one({"username": user.username, "password": hashed_pw})
    return {"message": "User registered successfully"}

@app.post("/login")
def login(user: User):
    record = users_collection.find_one({"username": user.username})
    if not record:
        raise HTTPException(status_code=400, detail="User not found")

    if not bcrypt.checkpw(user.password.encode('utf-8'), record["password"]):
        raise HTTPException(status_code=400, detail="Invalid password")

    return {"message": "Login successful", "username": user.username}
