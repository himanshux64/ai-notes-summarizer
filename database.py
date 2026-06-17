"""
database.py — MongoDB Atlas data layer
Uses pymongo for connection and schema management.
All summary queries are scoped to the authenticated user_id.
"""

import os
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from bson.objectid import ObjectId
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
#  Connection Pool
#  pymongo.MongoClient handles its own connection pooling automatically.
# ──────────────────────────────────────────────────────────────────────────────
MONGODB_URI = os.environ.get("MONGODB_URI")

if not MONGODB_URI or MONGODB_URI == "mongodb+srv://<username>:<password>@cluster0.mongodb.net/ai-notes?retryWrites=true&w=majority":
    print("Warning: MONGODB_URI environment variable is not properly set.")
    # We don't raise RuntimeError here so the app can still start and show UI, 
    # but database operations will fail if this isn't set.

_client = None
_db = None

def get_db():
    """Lazy-initialise the MongoDB client and return the database instance."""
    global _client, _db
    if _client is None:
        if not MONGODB_URI:
            raise RuntimeError("MONGODB_URI is not set in the environment.")
        _client = MongoClient(MONGODB_URI)
        # Try to get the default database from the URI, fallback to 'ai_notes' if missing
        try:
            _db = _client.get_default_database()
        except Exception:
            _db = _client["ai_notes"]
        
        # Ensure email uniqueness
        _db.users.create_index("email", unique=True)
        # Ensure fast lookups for user summaries
        _db.summaries.create_index("user_id")
        
    return _db

# ──────────────────────────────────────────────────────────────────────────────
#  Helper
# ──────────────────────────────────────────────────────────────────────────────
def _format_doc(doc: dict) -> dict | None:
    """Helper to format MongoDB documents for the Flask app."""
    if not doc:
        return None
    # Convert _id to string id
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Convert datetime objects to ISO strings if needed, but the original code 
    # handles isoformat() inside get_history and get_summary.
    return doc

# ──────────────────────────────────────────────────────────────────────────────
#  User CRUD
# ──────────────────────────────────────────────────────────────────────────────

def create_user(email: str, password_hash: str) -> dict | None:
    """
    Insert a new user and return the created row as a dict.
    Returns None if the email already exists.
    """
    db = get_db()
    user_doc = {
        "email": email.lower().strip(),
        "password_hash": password_hash,
        "created_at": datetime.utcnow()
    }
    
    try:
        result = db.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        return _format_doc(user_doc)
    except DuplicateKeyError:
        return None


def get_user_by_email(email: str) -> dict | None:
    """Fetch a user row by email (case-insensitive). Returns None if not found."""
    db = get_db()
    user = db.users.find_one({"email": email.lower().strip()})
    return _format_doc(user)


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user row by string ID. Returns None if not found or invalid ID."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        return None
        
    db = get_db()
    user = db.users.find_one({"_id": oid})
    return _format_doc(user)


# ──────────────────────────────────────────────────────────────────────────────
#  Summary CRUD  (all queries scoped to user_id)
# ──────────────────────────────────────────────────────────────────────────────

def save_summary(
    user_id: str,
    title: str,
    original_text: str,
    summary: str,
    bullet_points: str,
    takeaways: str,
    study_notes: str,
    flashcards,
    word_count: int,
    reading_time: int,
) -> str:
    """
    Persist a new summary document and return its string ID.
    flashcards can be a list or a string.
    """
    db = get_db()
    
    summary_doc = {
        "user_id": user_id,
        "title": title,
        "original_text": original_text,
        "summary": summary,
        "bullet_points": bullet_points,
        "takeaways": takeaways,
        "study_notes": study_notes,
        "flashcards": flashcards,
        "word_count": word_count,
        "reading_time": reading_time,
        "created_at": datetime.utcnow()
    }
    
    result = db.summaries.insert_one(summary_doc)
    return str(result.inserted_id)


def get_history(user_id: str) -> list[dict]:
    """Return lightweight summary list (no full text) for the given user, newest first."""
    db = get_db()
    
    cursor = db.summaries.find(
        {"user_id": user_id},
        {"title": 1, "word_count": 1, "reading_time": 1, "created_at": 1}
    ).sort("created_at", -1)
    
    result = []
    for doc in cursor:
        d = _format_doc(doc)
        if d and d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        result.append(d)
        
    return result


def get_summary(summary_id: str, user_id: str) -> dict | None:
    """
    Return full summary detail for the given id, but only if it belongs to user_id.
    Returns None if not found or not owned by the user.
    """
    try:
        oid = ObjectId(summary_id)
    except Exception:
        return None
        
    db = get_db()
    doc = db.summaries.find_one({"_id": oid, "user_id": user_id})
    if not doc:
        return None
        
    data = _format_doc(doc)
    if data and data.get("created_at"):
        data["created_at"] = data["created_at"].isoformat()
        
    return data


def delete_summary(summary_id: str, user_id: str) -> bool:
    """
    Delete a summary document only if it belongs to user_id.
    Returns True if a document was deleted, False otherwise.
    """
    try:
        oid = ObjectId(summary_id)
    except Exception:
        return False
        
    db = get_db()
    result = db.summaries.delete_one({"_id": oid, "user_id": user_id})
    return result.deleted_count > 0
