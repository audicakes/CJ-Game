# game/engine.py
from copy import deepcopy

GRID_COLUMNS = 11
GRID_ROWS = 8

PLAYER_THEMES = [
    ("Red",   (239, 68, 68)),
    ("Blue",  (59, 130, 246)),
    ("Amber", (234, 179, 8)),
    ("Green", (34, 197, 94)),
]

DIRECTIONS = {
    "left":  (-1, 0),
    "right": ( 1, 0),
    "up":    ( 0,-1),
    "down":  ( 0, 1),
}

def _in_bounds(c, r):
    return 0 <= c < GRID_COLUMNS and 0 <= r < GRID_ROWS

def new_room():
    # state holds serializable data only
    return {
        "players": [],           # list of names in join order (for turn rotation)
        "state": {
            "grid": {"cols": GRID_COLUMNS, "rows": GRID_ROWS},
            "actors": {},        # name -> {"col","row","facing","color","hp"}
            "theme_index": 0,    # next color to assign
        },
        "turn": 0,
    }

def join(game, name):
    g = deepcopy(game)
    if name in g["state"]["actors"]:
        # already present, just ensure players list contains name
        if name not in g["players"]:
            g["players"].append(name)
        return g

    # assign color/label cyclically
    theme_i = g["state"]["theme_index"] % len(PLAYER_THEMES)
    label, color = PLAYER_THEMES[theme_i]
    g["state"]["theme_index"] = theme_i + 1

    # spawn roughly spread out; very simple placement: column = theme_i*2, row = theme_i*2 (clamped)
    col = min(theme_i * 2, GRID_COLUMNS - 1)
    row = min(theme_i * 2, GRID_ROWS - 1)

    g["players"].append(name)
    g["state"]["actors"][name] = {
        "label": label,
        "color": color,  # RGB tuple is fine; JS will convert
        "col": col,
        "row": row,
        "facing": "right",
        "hp": 3
    }
    return g

def _occupied(g, col, row, except_name=None):
    for n, a in g["state"]["actors"].items():
        if n == except_name:
            continue
        if a["hp"] > 0 and a["col"] == col and a["row"] == row:
            return True
    return False

def apply_move(game, move):
    """
    move = {
      "type": "face" | "step" | "end_turn",
      "dir": "left|right|up|down"   # for face/step
      "who": "<player name>"
    }
    """
    g = deepcopy(game)
    if not g["players"]:
        return g

    # enforce turn order
    current = g["players"][g["turn"] % len(g["players"])]
    if move.get("who") != current:
        # ignore out-of-turn moves
        return g

    actors = g["state"]["actors"]
    if current not in actors:
        return g
    you = actors[current]

    t = move.get("type")
    if t == "face":
        d = move.get("dir")
        if d in DIRECTIONS:
            you["facing"] = d
        return g

    if t == "step":
        d = move.get("dir")
        if d in DIRECTIONS:
            dc, dr = DIRECTIONS[d]
            nc, nr = you["col"] + dc, you["row"] + dr
            if _in_bounds(nc, nr) and not _occupied(g, nc, nr, except_name=current):
                you["col"], you["row"] = nc, nr
        # stepping consumes your turn
        g["turn"] = (g["turn"] + 1) % len(g["players"])
        return g

    if t == "end_turn":
        g["turn"] = (g["turn"] + 1) % len(g["players"])
        return g

    return g
