"""
database.py — Data layer with MongoDB Atlas primary backend and SQLite fallback.
All summary queries are scoped to the authenticated user_id.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import certifi
from bson.objectid import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI")
USE_LOCAL_DB = os.environ.get("USE_LOCAL_DB", "").lower() in ("1", "true", "yes")
LOCAL_DB_PATH = Path(os.environ.get("LOCAL_DB_PATH", "data/local.db"))

if not MONGODB_URI or MONGODB_URI == (
    "mongodb+srv://<username>:<password>@cluster0.mongodb.net/ai-notes"
    "?retryWrites=true&w=majority"
):
    print("Warning: MONGODB_URI environment variable is not properly set.")

_client = None
_db = None
_backend = None
_sqlite_conn = None


def _use_sqlite() -> bool:
    return USE_LOCAL_DB or _backend == "sqlite"


def _init_sqlite():
    """Initialise local SQLite storage for development/offline use."""
    global _sqlite_conn, _backend
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _sqlite_conn = sqlite3.connect(LOCAL_DB_PATH, check_same_thread=False)
    _sqlite_conn.row_factory = sqlite3.Row

    _sqlite_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS summaries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            original_text TEXT NOT NULL,
            summary TEXT NOT NULL,
            bullet_points TEXT NOT NULL,
            takeaways TEXT NOT NULL,
            study_notes TEXT NOT NULL,
            flashcards TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            reading_time INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_summaries_user_id ON summaries(user_id);
        """
    )
    _sqlite_conn.commit()
    _backend = "sqlite"
    print(f"Using local SQLite database at {LOCAL_DB_PATH.resolve()}")


def get_db():
    """Lazy-initialise MongoDB or fall back to SQLite when Atlas is unreachable."""
    global _client, _db, _backend

    if _use_sqlite():
        if _sqlite_conn is None:
            _init_sqlite()
        return _db

    if _client is None:
        if not MONGODB_URI:
            _init_sqlite()
            return _db

        try:
            _client = MongoClient(
                MONGODB_URI,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
                retryWrites=True,
            )
            _client.admin.command("ping")
            try:
                _db = _client.get_default_database()
            except Exception:
                _db = _client["ai_notes"]

            _db.users.create_index("email", unique=True)
            _db.summaries.create_index("user_id")
            _backend = "mongo"
        except (ServerSelectionTimeoutError, Exception) as exc:
            print(
                "Warning: MongoDB connection failed "
                f"({exc}). Falling back to local SQLite."
            )
            print(
                "If using Atlas, whitelist your IP at "
                "cloud.mongodb.com -> Network Access."
            )
            _client = None
            _db = None
            _init_sqlite()

    return _db


def _new_id() -> str:
    return uuid.uuid4().hex


def _format_doc(doc: dict) -> dict | None:
    if not doc:
        return None
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


def _summary_row_to_dict(row: sqlite3.Row, include_full: bool = True) -> dict:
    data = {
        "id": row["id"],
        "title": row["title"],
        "word_count": row["word_count"],
        "reading_time": row["reading_time"],
        "created_at": row["created_at"],
    }
    if "user_id" in row.keys():
        data["user_id"] = row["user_id"]
    if include_full:
        data.update(
            {
                "original_text": row["original_text"],
                "summary": row["summary"],
                "bullet_points": row["bullet_points"],
                "takeaways": row["takeaways"],
                "study_notes": row["study_notes"],
                "flashcards": json.loads(row["flashcards"]),
            }
        )
    return data


def create_user(email: str, password_hash: str) -> dict | None:
    get_db()
    email = email.lower().strip()
    created_at = datetime.utcnow()

    if _use_sqlite():
        user_id = _new_id()
        try:
            _sqlite_conn.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, email, password_hash, created_at.isoformat()),
            )
            _sqlite_conn.commit()
            return {
                "id": user_id,
                "email": email,
                "password_hash": password_hash,
                "created_at": created_at,
            }
        except sqlite3.IntegrityError:
            return None

    user_doc = {
        "email": email,
        "password_hash": password_hash,
        "created_at": created_at,
    }
    try:
        result = _db.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        return _format_doc(user_doc)
    except DuplicateKeyError:
        return None


def get_user_by_email(email: str) -> dict | None:
    get_db()
    email = email.lower().strip()

    if _use_sqlite():
        row = _sqlite_conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }

    return _format_doc(_db.users.find_one({"email": email}))


def get_user_by_id(user_id: str) -> dict | None:
    get_db()

    if _use_sqlite():
        row = _sqlite_conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }

    try:
        oid = ObjectId(user_id)
    except Exception:
        return None
    return _format_doc(_db.users.find_one({"_id": oid}))


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
    get_db()
    created_at = datetime.utcnow()

    if _use_sqlite():
        summary_id = _new_id()
        _sqlite_conn.execute(
            """
            INSERT INTO summaries (
                id, user_id, title, original_text, summary, bullet_points,
                takeaways, study_notes, flashcards, word_count, reading_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                user_id,
                title,
                original_text,
                summary,
                bullet_points,
                takeaways,
                study_notes,
                json.dumps(flashcards),
                word_count,
                reading_time,
                created_at.isoformat(),
            ),
        )
        _sqlite_conn.commit()
        return summary_id

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
        "created_at": created_at,
    }
    result = _db.summaries.insert_one(summary_doc)
    return str(result.inserted_id)


def get_history(user_id: str) -> list[dict]:
    get_db()

    if _use_sqlite():
        rows = _sqlite_conn.execute(
            """
            SELECT id, title, word_count, reading_time, created_at
            FROM summaries
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [_summary_row_to_dict(row, include_full=False) for row in rows]

    cursor = _db.summaries.find(
        {"user_id": user_id},
        {"title": 1, "word_count": 1, "reading_time": 1, "created_at": 1},
    ).sort("created_at", -1)

    result = []
    for doc in cursor:
        formatted = _format_doc(doc)
        if formatted and formatted.get("created_at"):
            formatted["created_at"] = formatted["created_at"].isoformat()
        result.append(formatted)
    return result


def get_summary(summary_id: str, user_id: str) -> dict | None:
    get_db()

    if _use_sqlite():
        row = _sqlite_conn.execute(
            "SELECT * FROM summaries WHERE id = ? AND user_id = ?",
            (summary_id, user_id),
        ).fetchone()
        return _summary_row_to_dict(row) if row else None

    try:
        oid = ObjectId(summary_id)
    except Exception:
        return None

    doc = _db.summaries.find_one({"_id": oid, "user_id": user_id})
    if not doc:
        return None

    data = _format_doc(doc)
    if data and data.get("created_at"):
        data["created_at"] = data["created_at"].isoformat()
    return data


def delete_summary(summary_id: str, user_id: str) -> bool:
    get_db()

    if _use_sqlite():
        cur = _sqlite_conn.execute(
            "DELETE FROM summaries WHERE id = ? AND user_id = ?",
            (summary_id, user_id),
        )
        _sqlite_conn.commit()
        return cur.rowcount > 0

    try:
        oid = ObjectId(summary_id)
    except Exception:
        return False

    result = _db.summaries.delete_one({"_id": oid, "user_id": user_id})
    return result.deleted_count > 0


def migrate_guest_data(guest_id: str, user_id: str) -> int:
    get_db()

    if _use_sqlite():
        cur = _sqlite_conn.execute(
            "UPDATE summaries SET user_id = ? WHERE user_id = ?",
            (user_id, guest_id),
        )
        _sqlite_conn.commit()
        return cur.rowcount

    result = _db.summaries.update_many(
        {"user_id": guest_id},
        {"$set": {"user_id": user_id}},
    )
    return result.modified_count
