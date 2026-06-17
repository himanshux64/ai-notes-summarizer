"""
app.py — AI Notes Summarizer Pro
Flask application with Supabase PostgreSQL, flask-login authentication,
user-scoped summary management, and Gunicorn-ready export.
"""

import os
import math
import io

from flask import (
    Flask, request, jsonify, render_template,
    send_file, redirect, url_for, flash, session,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user,
)
from PyPDF2 import PdfReader
from dotenv import load_dotenv

from database import (
    create_user, get_user_by_email, get_user_by_id,
    save_summary, get_history, get_summary, delete_summary, migrate_guest_data
)
from summarizer import summarize_text, chat_with_ai

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
#  App Configuration
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # 16 MB upload limit
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ──────────────────────────────────────────────────────────────────────────────
#  Flask-Login Setup
# ──────────────────────────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


class User(UserMixin):
    """Thin wrapper around our users dict so flask-login is happy."""

    def __init__(self, user_dict: dict):
        self.id = str(user_dict["id"])
        self.email = user_dict["email"]

    def get_id(self):
        return self.id


@login_manager.user_loader
def load_user(user_id: str):
    data = get_user_by_id(user_id)
    return User(data) if data else None


# ──────────────────────────────────────────────────────────────────────────────
#  Helper
# ──────────────────────────────────────────────────────────────────────────────
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using PyPDF2."""
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text.strip()


# ──────────────────────────────────────────────────────────────────────────────
#  Public Routes
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Landing page — redirect authenticated users straight to dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        # Basic validation
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("signup.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("signup.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        pw_hash = generate_password_hash(password)
        user_data = create_user(email, pw_hash)

        if user_data is None:
            flash("An account with that email already exists.", "error")
            return render_template("signup.html")

        user = User(user_data)
        login_user(user)

        guest_id = request.form.get("guest_id")
        if guest_id:
            migrated = migrate_guest_data(guest_id, user.id)
            if migrated > 0:
                flash(f"Account created and {migrated} summaries migrated!", "success")
            else:
                flash("Account created! Welcome aboard 🎉", "success")
        else:
            flash("Account created! Welcome aboard 🎉", "success")

        return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user_data = get_user_by_email(email)

        if not user_data or not check_password_hash(user_data["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        user = User(user_data)
        login_user(user, remember=remember)

        guest_id = request.form.get("guest_id")
        if guest_id:
            migrated = migrate_guest_data(guest_id, user.id)
            if migrated > 0:
                flash(f"Logged in successfully. Migrated {migrated} items from guest session.", "success")

        next_page = request.args.get("next")
        return redirect(next_page or url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("index"))


# ──────────────────────────────────────────────────────────────────────────────
#  Protected Dashboard
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", is_authenticated=current_user.is_authenticated)


# ──────────────────────────────────────────────────────────────────────────────
#  Protected API Routes  (all scoped to current_user.id)
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/api/history", methods=["GET"])
@login_required
def api_get_history():
    try:
        history = get_history(current_user.id)
        return jsonify({"success": True, "history": history})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/history/<string:summary_id>", methods=["GET"])
@login_required
def api_get_summary_detail(summary_id):
    try:
        summary = get_summary(summary_id, current_user.id)
        if not summary:
            return jsonify({"success": False, "error": "Summary not found"}), 404
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/history/<string:summary_id>", methods=["DELETE"])
@login_required
def api_delete_summary(summary_id):
    try:
        deleted = delete_summary(summary_id, current_user.id)
        if not deleted:
            return jsonify({"success": False, "error": "Summary not found or not yours"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            user_id = request.headers.get("X-Guest-ID") or request.form.get("guest_id")
            if not user_id:
                return jsonify({"success": False, "error": "Missing authentication or guest ID"}), 401

        title      = request.form.get("title", "").strip()
        text       = request.form.get("text", "").strip()
        api_token  = (request.headers.get("X-HF-Token")
                      or request.form.get("api_token", "").strip())
        
        model_name = (request.headers.get("X-HF-Model")
                      or request.form.get("model_name", "").strip()
                      or "mistralai/Mistral-7B-Instruct-v0.3")

        # Use server default token if the user didn't provide one and isn't using mock mode
        if not api_token and model_name != "mock":
            api_token = os.environ.get("HUGGINGFACEHUB_API_TOKEN", "")

        # Handle file uploads
        if "file" in request.files:
            uploaded_file = request.files["file"]
            if uploaded_file.filename:
                filename = secure_filename(uploaded_file.filename)
                if not title:
                    title = filename

                file_ext  = os.path.splitext(filename)[1].lower()
                file_bytes = uploaded_file.read()

                if file_ext == ".pdf":
                    text = extract_text_from_pdf(file_bytes)
                elif file_ext in (".txt", ".md"):
                    text = file_bytes.decode("utf-8", errors="ignore")
                else:
                    return jsonify({
                        "success": False,
                        "error": "Unsupported file format. Please upload a PDF or TXT file.",
                    }), 400

        if not text:
            return jsonify({
                "success": False,
                "error": "No text content found to summarize. Please paste text or upload a document.",
            }), 400

        if not title:
            first_line = text.split("\n")[0].strip()
            title = (first_line[:40] + "...") if len(first_line) > 40 else first_line
            if not title:
                title = "Pasted Notes"

        # Stats
        words        = text.split()
        word_count   = len(words)
        reading_time = max(1, math.ceil(word_count / 200))

        # AI summarization
        ai_data = summarize_text(text, api_token=api_token, model_name=model_name)

        # Persist to database
        summary_id = save_summary(
            user_id       = user_id,
            title         = title,
            original_text = text,
            summary       = ai_data["summary"],
            bullet_points = ai_data["bullet_points"],
            takeaways     = ai_data["takeaways"],
            study_notes   = ai_data["study_notes"],
            flashcards    = ai_data["flashcards"],
            word_count    = word_count,
            reading_time  = reading_time,
        )

        return jsonify({
            "success": True,
            "data": {
                "id"          : summary_id,
                "title"       : title,
                "word_count"  : word_count,
                "reading_time": reading_time,
                **ai_data,
            },
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.json or {}
        summary_id = data.get("summary_id")
        user_message = data.get("message")
        chat_history = data.get("history", [])

        if not summary_id or not user_message:
            return jsonify({"success": False, "error": "Missing summary_id or message"}), 400

        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            user_id = request.headers.get("X-Guest-ID") or data.get("guest_id")

        summary_data = get_summary(summary_id, user_id)
        if not summary_data:
            return jsonify({"success": False, "error": "Summary not found or access denied"}), 404

        api_token  = request.headers.get("X-HF-Token", "")
        model_name = request.headers.get("X-HF-Model", "mistralai/Mistral-7B-Instruct-v0.3")

        if not api_token and model_name != "mock":
            api_token = os.environ.get("HUGGINGFACEHUB_API_TOKEN", "")

        reply = chat_with_ai(summary_data["original_text"], user_message, chat_history, api_token, model_name)
        
        return jsonify({"success": True, "reply": reply})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/migrate_guest_data", methods=["POST"])
@login_required
def api_migrate_guest_data_endpoint():
    try:
        data = request.json or {}
        guest_id = data.get("guest_id")
        if not guest_id:
            return jsonify({"success": False, "error": "Missing guest_id"}), 400
            
        migrated = migrate_guest_data(guest_id, current_user.id)
        return jsonify({"success": True, "migrated_count": migrated})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/export/<string:summary_id>/<string:format_type>", methods=["GET"])
@login_required
def api_export_summary(summary_id, format_type):
    try:
        summary_data = get_summary(summary_id, current_user.id)
        if not summary_data:
            return "Summary not found", 404

        title_slug = secure_filename(summary_data["title"].replace(" ", "_"))

        if format_type == "markdown":
            content  = f"# {summary_data['title']}\n\n"
            content += f"**Word Count:** {summary_data['word_count']} | **Estimated Reading Time:** {summary_data['reading_time']} min\n\n"
            content += f"## Summary\n{summary_data['summary']}\n\n"
            content += f"## Key Bullet Points\n{summary_data['bullet_points']}\n\n"
            content += f"## Key Takeaways\n{summary_data['takeaways']}\n\n"
            content += f"## Study Notes\n{summary_data['study_notes']}\n\n"
            content += "## Revision Flashcards\n"
            if isinstance(summary_data["flashcards"], list):
                for idx, card in enumerate(summary_data["flashcards"]):
                    content += f"**Flashcard {idx + 1}**\n- Q: {card['question']}\n- A: {card['answer']}\n\n"
            else:
                content += f"{summary_data['flashcards']}\n"

            return send_file(
                io.BytesIO(content.encode("utf-8")),
                mimetype="text/markdown",
                as_attachment=True,
                download_name=f"{title_slug}_summary.md",
            )

        elif format_type == "text":
            content  = f"TITLE: {summary_data['title']}\n"
            content += f"STATS: {summary_data['word_count']} words | {summary_data['reading_time']} min read\n"
            content += "=" * 50 + "\n\n"
            content += f"SUMMARY:\n{summary_data['summary']}\n\n"
            content += f"BULLET POINTS:\n{summary_data['bullet_points']}\n\n"
            content += f"KEY TAKEAWAYS:\n{summary_data['takeaways']}\n\n"
            content += f"STUDY NOTES:\n{summary_data['study_notes']}\n\n"
            content += "FLASHCARDS:\n"
            if isinstance(summary_data["flashcards"], list):
                for idx, card in enumerate(summary_data["flashcards"]):
                    content += f"Q{idx + 1}: {card['question']}\nA{idx + 1}: {card['answer']}\n\n"
            else:
                content += f"{summary_data['flashcards']}\n"

            return send_file(
                io.BytesIO(content.encode("utf-8")),
                mimetype="text/plain",
                as_attachment=True,
                download_name=f"{title_slug}_summary.txt",
            )

        else:
            return "Unsupported format", 400

    except Exception as e:
        return str(e), 500


# ──────────────────────────────────────────────────────────────────────────────
#  Gunicorn entry point  (do NOT call init_db here — schema is managed on Supabase)
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5000)
