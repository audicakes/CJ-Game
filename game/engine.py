# game/engine.py
from copy import deepcopy
import random

# ---- Config ----
GRID_COLUMNS = 11
GRID_ROWS = 8

MAX_HP = 3
DEAGLE_BASE_RANGE_TILES = 4
SHOTGUN_BASE_DEPTH = 2  # rows forward; width is always 3

DIRECTIONS = {"left":(-1,0), "right":(1,0), "up":(0,-1), "down":(0,1)}

PLAYER_THEMES = [
    ("Red",   (239, 68, 68)),
    ("Blue",  (59, 130, 246)),
    ("Amber", (234, 179, 8)),
    ("Green", (34, 197, 94)),
]

# ---- Helpers ----
def _in_bounds(c, r): return 0 <= c < GRID_COLUMNS and 0 <= r < GRID_ROWS

def _occupied(state, col, row, except_name=None):
    for n,a in state["actors"].items():
        if n == except_name: continue
        if a["hp"] > 0 and a["col"] == col and a["row"] == row:
            return True
    return False

def _ob_at(state, c, r):
    for ob in state["obstacles"]:
        if ob["col"] == c and ob["row"] == r:
            return ob
    return None

def _item_at(state, c, r):
    for it in state["items"]:
        if it["col"] == c and it["row"] == r:
            return it
    return None

# ---- New room / generation ----
def new_room():
    return {
        "players": [],           # join order (names)
        "state": {
            "grid": {"cols": GRID_COLUMNS, "rows": GRID_ROWS},
            "actors": {},        # name -> {...}
            "theme_index": 0,
            "obstacles": [],     # list of {"type":"wall|water", "col","row"}
            "items": [],         # list of {"type": "...", "col","row"}
            "turn_meta": {},     # per-player end/start bookkeeping
        },
        "turn": 0,
    }

def _spawn_position(state):
    # simple spread: use theme index to pick a spawn area; fall back to random
    ti = state["theme_index"]
    col = min(ti * 2, GRID_COLUMNS - 1)
    row = min(ti * 2, GRID_ROWS - 1)
    if not _occupied(state, col, row): return col, row
    # search nearest free
    for radius in range(1, max(GRID_COLUMNS, GRID_ROWS)):
        for dc in range(-radius, radius+1):
            for dr in range(-radius, radius+1):
                c, r = col+dc, row+dr
                if _in_bounds(c,r) and not _occupied(state, c, r):
                    return c, r
    return 0, 0

def _gen_level(state, num_players):
    # obstacles
    state["obstacles"].clear()
    used = {(a["col"], a["row"]) for a in state["actors"].values()}
    min_ob = (GRID_COLUMNS * GRID_ROWS) // 15
    max_ob = (GRID_COLUMNS * GRID_ROWS) // 9 + 3
    obstacle_count = random.randint(min_ob, max_ob)

    def place_one(kind):
        tries = 0
        while tries < 2000:
            tries += 1
            c = random.randrange(0, GRID_COLUMNS)
            r = random.randrange(0, GRID_ROWS)
            if (c, r) in used: continue
            used.add((c,r))
            state["obstacles"].append({"type":kind, "col":c, "row":r})
            return
    for _ in range(obstacle_count):
        place_one("wall" if random.random() < 0.6 else "water")

    # items (rough budget ~ players*3 ± 2)
    base = num_players * 3
    n_items = random.randint(max(1, base-2), base+2)
    n_weapon = int(n_items // 2.5)
    n_misc = n_items - n_weapon

    state["items"].clear()
    def place_item(kind):
        tries = 0
        while tries < 2000:
            tries += 1
            c = random.randrange(0, GRID_COLUMNS)
            r = random.randrange(0, GRID_ROWS)
            if (c, r) in used: continue
            used.add((c,r))
            state["items"].append({"type":kind, "col":c, "row":r})
            return
    for _ in range(n_weapon): place_item("mystery_weapon")
    for _ in range(n_misc):   place_item("mystery_item")

def join(game, name):
    g = deepcopy(game)
    st = g["state"]
    if name in st["actors"]:
        if name not in g["players"]:
            g["players"].append(name)
        return g

    # assign color/theme
    theme_i = st["theme_index"] % len(PLAYER_THEMES)
    st["theme_index"] += 1
    label, color = PLAYER_THEMES[theme_i]
    col, row = _spawn_position(st)

    st["actors"][name] = {
        "label": label,
        "color": color,  # RGB
        "col": col, "row": row,
        "facing": "right",
        "hp": MAX_HP,
        # inventory / flags
        "has_deagle": False,
        "has_shotgun": False,
        "has_agility_boots": False,
        "has_scope": False,
        "has_shield": False,
        "has_grenade": False,
        "grenade_count": 0,
        "consumable_selected": None,
        "last_water_pos": None,
    }
    g["players"].append(name)
    # first two joins → generate a board
    _gen_level(st, max(2, len(g["players"])))
    return g

# ---- Derived areas ----
def _deagle_tiles(st, p):
    if not p["has_deagle"]: return []
    rng = DEAGLE_BASE_RANGE_TILES + (1 if p["has_scope"] else 0)
    tiles = []
    dc, dr = DIRECTIONS[p["facing"]]
    c, r = p["col"] + dc, p["row"] + dr
    steps = 0
    while _in_bounds(c, r) and steps < rng:
        tiles.append((c, r))
        ob = _ob_at(st, c, r)
        steps += 1
        if ob and ob["type"] == "wall": break
        c += dc; r += dr
    return tiles

def _shotgun_tiles(st, p):
    if not p["has_shotgun"]: return []
    depth_max = SHOTGUN_BASE_DEPTH + (1 if p["has_scope"] else 0)
    tiles = set()
    dc, dr = DIRECTIONS[p["facing"]]
    if p["facing"] in ("left","right"): pc, pr = (0,1)
    else:                                pc, pr = (1,0)
    blocked = {-1:False, 0:False, 1:False}
    for d in range(1, depth_max+1):
        for side in (-1,0,1):
            if blocked[side]: continue
            tc = p["col"] + dc*d + pc*side
            tr = p["row"] + dr*d + pr*side
            if not _in_bounds(tc,tr): continue
            # check ray to this tile for a wall
            w = False
            for step in range(1, d+1):
                cc = p["col"] + dc*step + pc*side
                rr = p["row"] + dr*step + pr*side
                if _ob_at(st, cc, rr) and _ob_at(st, cc, rr)["type"] == "wall":
                    w = True; break
            if w: blocked[side] = True; continue
            tiles.add((tc,tr))
    return sorted(list(tiles))

def _grenade_tiles(st, p):
    if p["grenade_count"] <= 0 or p["consumable_selected"] != "Grenade": return []
    tiles = []
    dc, dr = DIRECTIONS[p["facing"]]
    if p["facing"] in ("left","right"): pc, pr = (0,1)
    else:                                pc, pr = (1,0)
    for depth in range(1,4):
        for side in (-1,0,1):
            c = p["col"] + dc*depth + pc*side
            r = p["row"] + dr*depth + pr*side
            if _in_bounds(c,r): tiles.append((c,r))
    return tiles

# ---- Items / pickups ----
def _pickup_if_item(st, p):
    it = _item_at(st, p["col"], p["row"])
    if not it: return
    t = it["type"]
    consumed = True

    if t == "mystery_weapon":
        # remove current weapon then give random Deagle/Shotgun
        p["has_deagle"] = False
        p["has_shotgun"] = False
        if random.random() < 0.5: p["has_deagle"] = True
        else:                      p["has_shotgun"] = True

    elif t == "mystery_item":
        picks = []
        if not p["has_agility_boots"]: picks.append("agility")
        if not p["has_scope"]:         picks.append("scope")
        if not p["has_shield"]:        picks.append("shield")
        if not p["has_grenade"]:       picks.append("grenade")
        if not picks:
            consumed = False
        else:
            give = random.choice(picks)
            if give == "agility": p["has_agility_boots"] = True
            elif give == "scope": p["has_scope"] = True
            elif give == "shield": p["has_shield"] = True
            elif give == "grenade":
                p["has_grenade"] = True
                p["grenade_count"] = max(p["grenade_count"], 0) + 1

    if consumed:
        st["items"] = [x for x in st["items"] if not (x["col"]==it["col"] and x["row"]==it["row"])]

# ---- Damage / end-turn rules ----
def _apply_damage(st, victim_name, amount=1):
    p = st["actors"][victim_name]
    if amount > 0 and p["has_shield"]:
        p["has_shield"] = False
        return
    p["hp"] = max(0, p["hp"] - amount)

def _end_turn_bookkeeping(st, finished_name):
    p = st["actors"].get(finished_name)
    if not p: return
    ob = _ob_at(st, p["col"], p["row"])
    if ob and ob["type"] == "water":
        pos = (p["col"], p["row"])
        last = p.get("last_water_pos")
        if last == pos:
            _apply_damage(st, finished_name, 1)  # drown tick
        p["last_water_pos"] = pos
    else:
        p["last_water_pos"] = None
    p["consumable_selected"] = None

def _advance_turn(g):
    players = g["players"]
    if not players: return
    cur = players[g["turn"] % len(players)]
    _end_turn_bookkeeping(g["state"], cur)
    # next alive
    for _ in range(len(players)):
        g["turn"] = (g["turn"] + 1) % len(players)
        nxt = players[g["turn"]]
        if g["state"]["actors"][nxt]["hp"] > 0:
            break

# ---- Public API ----
def apply_move(game, move):
    """
    move = { "type": "...", "who": "<player>", ... }
    Supported:
      - face {type:'face', who, dir}
      - step {type:'step', who, dir}
      - end_turn {type:'end_turn', who}
      - shoot {type:'shoot', who}        # deagle (right-click in line)
      - shotgun {type:'shotgun', who}    # shotgun fan
      - toggle_grenade {type:'toggle_grenade', who}
      - throw_grenade {type:'throw_grenade', who, target:{col,row}}
    """
    g = deepcopy(game)
    if not g["players"]: return g

    cur = g["players"][g["turn"] % len(g["players"])]
    if move.get("who") != cur:
        return g  # out-of-turn ignored

    st = g["state"]; actors = st["actors"]
    if cur not in actors: return g
    you = actors[cur]

    t = move.get("type")

    # ---- facing ----
    if t == "face":
        d = move.get("dir")
        if d in DIRECTIONS: you["facing"] = d
        return g

    # ---- movement (consumes turn) ----
    if t == "step":
        d = move.get("dir")
        if d in DIRECTIONS:
            dc, dr = DIRECTIONS[d]
            nc, nr = you["col"]+dc, you["row"]+dr
            if _in_bounds(nc,nr) and not _occupied(st, nc, nr, except_name=cur):
                ob = _ob_at(st, nc, nr)
                if not (ob and ob["type"] == "wall"):
                    you["col"], you["row"] = nc, nr
                    _pickup_if_item(st, you)
        _advance_turn(g)
        return g

    # ---- end turn ----
    if t == "end_turn":
        _advance_turn(g)
        return g

    # ---- inventory toggles / actions ----
    if t == "toggle_grenade":
        if you["has_grenade"] and you["grenade_count"] > 0:
            you["consumable_selected"] = None if you["consumable_selected"] == "Grenade" else "Grenade"
        return g

    # deagle fire along facing line; damage first target in range; walls block
    if t == "shoot":
        if you["has_deagle"]:
            for (c,r) in _deagle_tiles(st, you):
                # hit nearest actor on the line
                for name, a in actors.items():
                    if name == cur or a["hp"] <= 0: continue
                    if a["col"] == c and a["row"] == r:
                        _apply_damage(st, name, 1)
                        _advance_turn(g)
                        return g
            # no hit still costs turn
            _advance_turn(g)
        return g

    # shotgun fan; damage any actor in fan area (respecting walls)
    if t == "shotgun":
        if you["has_shotgun"]:
            fan = set(_shotgun_tiles(st, you))
            hit = False
            for name,a in actors.items():
                if name == cur or a["hp"] <= 0: continue
                if (a["col"], a["row"]) in fan:
                    _apply_damage(st, name, 1)
                    hit = True
            _advance_turn(g)
        return g

    # grenade: ignores walls; damages any actor in the 3x3 slab ahead at target
    if t == "throw_grenade":
        tgt = move.get("target") or {}
        tc, tr = tgt.get("col"), tgt.get("row")
        if you["grenade_count"] > 0 and you["consumable_selected"] == "Grenade":
            area = set(_grenade_tiles(st, you))
            if tc is not None and tr is not None and (tc, tr) in area:
                for name,a in actors.items():
                    if name == cur or a["hp"] <= 0: continue
                    if (a["col"], a["row"]) in area:
                        _apply_damage(st, name, 1)
                you["grenade_count"] -= 1
                if you["grenade_count"] <= 0:
                    you["consumable_selected"] = None
                _advance_turn(g)
        return g

    return g
