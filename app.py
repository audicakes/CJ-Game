# app.py
import os
from flask import Flask
from flask_socketio import SocketIO, emit, join_room

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
def health():
    return "CJ Game server OK"

@socketio.on("connect")
def on_connect():
    # Handy to confirm browser actually connects
    print("client connected")

@socketio.on("join")
def on_join(data):
    print("join payload:", data)
    room = str(data["room"])
    name = str(data["name"])
    join_room(room)
    game = rooms.setdefault(room, {"players": [], "state": {}, "turn": 0})
    if name not in game["players"]:
        game["players"].append(name)
    emit("state", game, room=room)

@socketio.on("move")
def on_move(data):
    room = str(data["room"])
    move = data["move"]
    game = rooms.get(room)
    if not game:
        return
    # Example: advance turn index
    if game["players"]:
        game["turn"] = (game["turn"] + 1) % len(game["players"])
    emit("state", game, room=room)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    socketio.run(app, host="0.0.0.0", port=port)
