# app.py
import os
from flask import Flask
from flask import send_from_directory
STATIC_DIR = os.path.join(os.path.dirname(__file__), "public")
from flask_socketio import SocketIO, emit, join_room
from game.engine import new_room, join as eng_join, apply_move

rooms = {}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "devkey")

# ---- CORS + fallback async mode ----
# ASYNC_MODE options: None (auto), "eventlet", "gevent", "threading"
ASYNC_MODE = os.environ.get("ASYNC_MODE") or None
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

socketio = SocketIO(
    app,
    cors_allowed_origins=CORS_ORIGINS,   # allow browser clients during dev
    async_mode=ASYNC_MODE,               # fallback control via env
    logger=False,                        # set True if you want server logs
    engineio_logger=False                # set True for verbose transport logs
)

# In-memory example; swap to Redis/DB later if games should persist
rooms = {}  # room_id -> { "players": [], "state": {...}, "turn": 0 }

@app.route("/")
def index():
    # Serve the browser client
    return send_from_directory(STATIC_DIR, "index.html")

def health():
    return "CJ Game server OK"

@app.get("/healthz")
def healthz():
    return {"ok": True, "version": os.environ.get("GIT_SHA","local")}

@socketio.on("connect")
def on_connect():
    # Handy to confirm browser actually connects
    print("client connected")

@socketio.on("join")
def on_join(data):
    room = str(data["room"]); name = str(data["name"])
    join_room(room)
    game = rooms.get(room) or new_room()
    game = eng_join(game, name)
    rooms[room] = game
    emit("state", game, room=room)

@socketio.on("move")
def on_move(data):
    room = str(data["room"]); move = data["move"]
    game = rooms.get(room)
    if not game: return
    # server-side validation/authority happens inside engine
    game = apply_move(game, move)
    rooms[room] = game
    emit("state", game, room=room)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    socketio.run(app, host="0.0.0.0", port=port)
