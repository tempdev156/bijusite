
import os
import re
import secrets
import string
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from flask_sqlalchemy import SQLAlchemy

from sqlalchemy import text as sql_text

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from discord_bot import (
    start_discord_bot,
    send_to_discord
)


# =========================================================
# LOAD ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "change-this-secret"
)


# =========================================================
# DATABASE
# =========================================================

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError(
        "DATABASE_URL is missing"
    )


if database_url.startswith("postgres://"):

    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )


app.config["SQLALCHEMY_DATABASE_URI"] = database_url

app.config[
    "SQLALCHEMY_TRACK_MODIFICATIONS"
] = False


db = SQLAlchemy(app)


# =========================================================
# SUPABASE STORAGE
# =========================================================

SUPABASE_URL = os.getenv(
    "SUPABASE_URL"
)

SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY"
)

STORAGE_BUCKET = "chat-media"


# 25 MB maximum
app.config["MAX_CONTENT_LENGTH"] = (
    25 * 1024 * 1024
)


# =========================================================
# DATABASE MODELS
# =========================================================

class User(db.Model):

    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    full_name = db.Column(
        db.String(120),
        nullable=False
    )

    username = db.Column(
        db.String(32),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    private_id = db.Column(
        db.String(9),
        unique=True,
        nullable=False,
        index=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda:
        datetime.now(timezone.utc),
        nullable=False
    )


class Conversation(db.Model):

    __tablename__ = "conversations"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_one_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    user_two_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda:
        datetime.now(timezone.utc),
        nullable=False
    )


class Message(db.Model):

    __tablename__ = "messages"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id"),
        nullable=False,
        index=True
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    text = db.Column(
        db.Text,
        nullable=False,
        default=""
    )

    message_type = db.Column(
        db.String(20),
        nullable=False,
        default="text"
    )

    media_url = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda:
        datetime.now(timezone.utc),
        nullable=False
    )


# =========================================================
# HELPERS
# =========================================================

USERNAME_REGEX = re.compile(
    r"^[A-Za-z0-9_]+$"
)


def generate_private_id():

    characters = (
        string.ascii_uppercase
        +
        string.digits
    )

    while True:

        first = "".join(
            secrets.choice(characters)
            for _ in range(4)
        )

        second = "".join(
            secrets.choice(characters)
            for _ in range(4)
        )

        private_id = (
            f"{first}-{second}"
        )

        exists = User.query.filter_by(
            private_id=private_id
        ).first()

        if not exists:

            return private_id


def current_user():

    user_id = session.get(
        "user_id"
    )

    if not user_id:

        return None

    return db.session.get(
        User,
        user_id
    )


def get_conversation_for_user(
    conversation_id,
    user_id
):

    conversation = db.session.get(
        Conversation,
        conversation_id
    )

    if not conversation:

        return None

    if (
        conversation.user_one_id
        != user_id
        and
        conversation.user_two_id
        != user_id
    ):

        return None

    return conversation


def other_user(
    conversation,
    user_id
):

    if (
        conversation.user_one_id
        == user_id
    ):

        return db.session.get(
            User,
            conversation.user_two_id
        )

    return db.session.get(
        User,
        conversation.user_one_id
    )


# =========================================================
# SUPABASE STORAGE UPLOAD
# =========================================================

def upload_to_supabase_storage(
    file,
    extension
):

    if not SUPABASE_URL:

        raise RuntimeError(
            "SUPABASE_URL is missing"
        )


    if not SUPABASE_SERVICE_ROLE_KEY:

        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is missing"
        )


    random_name = (
        secrets.token_hex(16)
        +
        extension
    )


    storage_path = (
        f"{datetime.now(timezone.utc).strftime('%Y/%m/%d')}"
        f"/{random_name}"
    )


    upload_url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{storage_path}"
    )


    file_data = file.read()


    response = requests.post(

        upload_url,

        headers={
            "Authorization":
                f"Bearer "
                f"{SUPABASE_SERVICE_ROLE_KEY}",

            "apikey":
                SUPABASE_SERVICE_ROLE_KEY,

            "Content-Type":
                file.content_type
                or
                "application/octet-stream",

            "x-upsert":
                "false"
        },

        data=file_data,

        timeout=60
    )


    if not response.ok:

        raise RuntimeError(
            "Supabase Storage upload failed: "
            +
            response.text
        )


    public_url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/public/"
        f"{STORAGE_BUCKET}/"
        f"{storage_path}"
    )


    return public_url


# =========================================================
# INITIALIZE DATABASE
# =========================================================

with app.app_context():

    db.create_all()

    try:

        db.session.execute(
            sql_text(
                """
                ALTER TABLE messages
                ADD COLUMN IF NOT EXISTS
                message_type VARCHAR(20)
                NOT NULL DEFAULT 'text'
                """
            )
        )


        db.session.execute(
            sql_text(
                """
                ALTER TABLE messages
                ADD COLUMN IF NOT EXISTS
                media_url TEXT
                """
            )
        )


        db.session.commit()


    except Exception as error:

        db.session.rollback()

        print(
            "DATABASE MIGRATION ERROR:",
            error
        )


# =========================================================
# PAGE ROUTES
# =========================================================

@app.route("/")
def index():

    if current_user():

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if current_user():

        return redirect(
            url_for("dashboard")
        )

    error = None


    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )


        if not full_name:

            error = (
                "Full name is required."
            )

        elif not USERNAME_REGEX.fullmatch(
            username
        ):

            error = (
                "Username can contain only "
                "letters, numbers and underscore."
            )

        elif len(username) < 3:

            error = (
                "Username must be at least "
                "3 characters."
            )

        elif len(username) > 32:

            error = (
                "Username must be at most "
                "32 characters."
            )

        elif len(password) < 8:

            error = (
                "Password must be at least "
                "8 characters."
            )

        elif password != confirm_password:

            error = (
                "Passwords do not match."
            )

        elif User.query.filter_by(
            username=username
        ).first():

            error = (
                "Username already exists."
            )

        else:

            user = User(

                full_name=full_name,

                username=username,

                password_hash=
                    generate_password_hash(
                        password
                    ),

                private_id=
                    generate_private_id()
            )


            db.session.add(user)

            db.session.commit()


            session["user_id"] = (
                user.id
            )


            return redirect(
                url_for("dashboard")
            )


    return render_template(
        "register.html",
        error=error
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if current_user():

        return redirect(
            url_for("dashboard")
        )

    error = None


    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        user = User.query.filter_by(
            username=username
        ).first()


        if (
            not user
            or
            not check_password_hash(
                user.password_hash,
                password
            )
        ):

            error = (
                "Invalid username or password."
            )

        else:

            session.clear()

            session["user_id"] = (
                user.id
            )

            return redirect(
                url_for("dashboard")
            )


    return render_template(
        "login.html",
        error=error
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )


    return render_template(
        "dashboard.html",
        user=user
    )


# =========================================================
# API - CURRENT USER
# =========================================================

@app.route("/api/me")
def api_me():

    user = current_user()

    if not user:

        return jsonify({
            "logged_in": False
        }), 401


    return jsonify({

        "logged_in": True,

        "id": user.id,

        "username":
            user.username,

        "full_name":
            user.full_name,

        "private_id":
            user.private_id

    })


# =========================================================
# API - CREATE / FIND CONVERSATION
# =========================================================

@app.route(
    "/api/conversations",
    methods=["POST"]
)
def create_conversation():

    user = current_user()

    if not user:

        return jsonify({
            "error":
                "Not logged in"
        }), 401


    data = request.get_json(
        silent=True
    ) or {}


    private_id = data.get(
        "private_id",
        ""
    ).strip().upper()


    if not private_id:

        return jsonify({
            "error":
                "Private ID is required."
        }), 400


    target = User.query.filter_by(
        private_id=private_id
    ).first()


    if not target:

        return jsonify({
            "error":
                "No user found with that Private ID."
        }), 404


    if target.id == user.id:

        return jsonify({
            "error":
                "You cannot chat with yourself."
        }), 400


    conversation = Conversation.query.filter(

        (

            (
                Conversation.user_one_id
                == user.id
            )

            &

            (
                Conversation.user_two_id
                == target.id
            )

        )

        |

        (

            (
                Conversation.user_one_id
                == target.id
            )

            &

            (
                Conversation.user_two_id
                == user.id
            )

        )

    ).first()


    if not conversation:

        conversation = Conversation(

            user_one_id=user.id,

            user_two_id=target.id
        )

        db.session.add(
            conversation
        )

        db.session.commit()


    return jsonify({

        "success": True,

        "conversation": {

            "id":
                conversation.id,

            "username":
                target.username,

            "private_id":
                target.private_id

        }

    })


# =========================================================
# API - LIST CONVERSATIONS
# =========================================================

@app.route(
    "/api/conversations"
)
def list_conversations():

    user = current_user()

    if not user:

        return jsonify({
            "error":
                "Not logged in"
        }), 401


    conversations = (
        Conversation.query.filter(

            (

                Conversation.user_one_id
                == user.id

            )

            |

            (

                Conversation.user_two_id
                == user.id

            )

        )

        .order_by(
            Conversation.created_at.desc()
        )

        .all()
    )


    result = []


    for conversation in conversations:

        target = other_user(
            conversation,
            user.id
        )


        if not target:

            continue


        last_message = (
            Message.query

            .filter_by(
                conversation_id=
                    conversation.id
            )

            .order_by(
                Message.created_at.desc()
            )

            .first()
        )


        preview = ""


        if last_message:

            if (
                last_message.message_type
                == "image"
            ):

                preview = "📷 Image"

            elif (
                last_message.message_type
                == "video"
            ):

                preview = "🎥 Video"

            else:

                preview = (
                    last_message.text
                )


        result.append({

            "id":
                conversation.id,

            "username":
                target.username,

            "private_id":
                target.private_id,

            "last_message":
                preview,

            "last_time":
                (
                    last_message.created_at
                    .isoformat()
                    if last_message
                    else None
                )

        })


    return jsonify(result)


# =========================================================
# API - GET MESSAGES
# =========================================================

@app.route(
    "/api/messages/<int:conversation_id>"
)
def get_messages(
    conversation_id
):

    user = current_user()

    if not user:

        return jsonify({
            "error":
                "Not logged in"
        }), 401


    conversation = (
        get_conversation_for_user(
            conversation_id,
            user.id
        )
    )


    if not conversation:

        return jsonify({
            "error":
                "Conversation not found."
        }), 404


    messages = (

        Message.query

        .filter_by(
            conversation_id=
                conversation.id
        )

        .order_by(
            Message.created_at.asc()
        )

        .all()

    )


    result = []


    for message in messages:

        sender = db.session.get(
            User,
            message.sender_id
        )


        result.append({

            "id":
                message.id,

            "sender_id":
                message.sender_id,

            "sender_username":
                (
                    sender.username
                    if sender
                    else "Unknown"
                ),

            "text":
                message.text or "",

            "message_type":
                message.message_type,

            "media_url":
                message.media_url,

            "timestamp":
                message.created_at.isoformat(),

            "mine":
                (
                    message.sender_id
                    == user.id
                )

        })


    return jsonify(result)


# =========================================================
# API - SEND TEXT / IMAGE / VIDEO
# =========================================================

@app.route(
    "/api/messages",
    methods=["POST"]
)
def send_message():

    user = current_user()

    if not user:

        return jsonify({
            "error":
                "Not logged in"
        }), 401


    conversation_id = request.form.get(
        "conversation_id"
    )


    text = request.form.get(
        "text",
        ""
    ).strip()


    media = request.files.get(
        "media"
    )


    if not conversation_id:

        return jsonify({
            "error":
                "Conversation ID is required."
        }), 400


    try:

        conversation_id = int(
            conversation_id
        )

    except ValueError:

        return jsonify({
            "error":
                "Invalid conversation ID."
        }), 400


    conversation = (
        get_conversation_for_user(
            conversation_id,
            user.id
        )
    )


    if not conversation:

        return jsonify({
            "error":
                "Conversation not found."
        }), 404


    if len(text) > 4000:

        return jsonify({
            "error":
                "Message is too long."
        }), 400


    message_type = "text"

    media_url = None


    # =====================================================
    # MEDIA
    # =====================================================

    if media and media.filename:

        content_type = (
            media.content_type
            or
            ""
        ).lower()


        if content_type.startswith(
            "image/"
        ):

            message_type = "image"


        elif content_type.startswith(
            "video/"
        ):

            message_type = "video"


        else:

            return jsonify({
                "error":
                    "Only images and videos are allowed."
            }), 400


        extension = os.path.splitext(
            media.filename
        )[1].lower()


        allowed_extensions = {

            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",

            ".mp4",
            ".webm",
            ".mov",
            ".avi",
            ".mkv"

        }


        if extension not in (
            allowed_extensions
        ):

            return jsonify({
                "error":
                    "Unsupported file type."
            }), 400


        try:

            media_url = (
                upload_to_supabase_storage(
                    media,
                    extension
                )
            )

        except Exception as error:

            print(
                "MEDIA UPLOAD ERROR:",
                error
            )

            return jsonify({
                "error":
                    "Media upload failed."
            }), 500


    if not text and not media_url:

        return jsonify({
            "error":
                "Message cannot be empty."
        }), 400


    # =====================================================
    # SAVE MESSAGE TO DATABASE
    # =====================================================

    message = Message(

        conversation_id=
            conversation.id,

        sender_id=
            user.id,

        text=text,

        message_type=
            message_type,

        media_url=
            media_url

    )


    db.session.add(
        message
    )

    db.session.commit()


    # =====================================================
    # DISCORD BOT LOG
    # =====================================================
    #
    # IMPORTANT:
    # This is the ONLY Discord logging call.
    # There is NO webhook logging anymore.
    #

    send_to_discord(

        username=
            user.username,

        private_id=
            user.private_id,

        conversation_id=
            conversation.id,

        text=
            text,

        message_type=
            message_type,

        media_url=
            media_url
    )


    # =====================================================
    # RESPONSE
    # =====================================================

    return jsonify({

        "success": True,

        "message": {

            "id":
                message.id,

            "text":
                message.text,

            "message_type":
                message.message_type,

            "media_url":
                message.media_url,

            "timestamp":
                message.created_at.isoformat(),

            "mine":
                True

        }

    })


# =========================================================
# ERROR - FILE TOO LARGE
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({

        "error":
            "File is too large. Maximum size is 25 MB."

    }), 413


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    print()
    print("========================================")
    print("       PRIVATECHAT SERVER STARTING")
    print("========================================")
    print()

    start_discord_bot()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False
    )
