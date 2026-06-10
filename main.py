import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="comps - RECF Tournament Manager Backend",
    description="REST API framework for managing RECF Robotics Competitions using MongoDB.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DATABASE_NAME", "recf_comps")

try:
    client = MongoClient(MONGO_URI)
    # Store database driver state contextual link globally inside app memory parameters
    app.state.db = client[DB_NAME]
    client.server_info()
    print(f"✅ Connected successfully to MongoDB database: '{DB_NAME}'")
except Exception as e:
    print(f"❌ Failed to connect to MongoDB: {e}")
    raise SystemExit(e)

@app.get("/", tags=["System"])
def read_root():
    return {"status": "Online", "software": "comps", "game_type": "RECF Only"}

# Import routers locally to ensure app context binds dynamically
from routes import operations, analytics

app.include_router(operations.router)
app.include_router(analytics.router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
