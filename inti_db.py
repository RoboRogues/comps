import os
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DATABASE_NAME", "recf_comps")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Enforce clean structural performance limits across collections
db.teams.create_index([("team_number", ASCENDING)], unique=True)
db.matches.create_index([("round", ASCENDING), ("match_number", ASCENDING)], unique=True)
db.skills.create_index([("team_number", ASCENDING), ("type", ASCENDING)])
db.eliminations.create_index([("match_id", ASCENDING)], unique=True)

print("✅ MongoDB collections and indexes initialized successfully.")
db.inspections.create_index([("team_number", ASCENDING)], unique=True)
print("✅ Inspection database tier collection index initialized.")
