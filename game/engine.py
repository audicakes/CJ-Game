# game/engine.py
from copy import deepcopy
import random

# --- Board / rules config ---
GRID_COLUMNS = 11
GRID_ROWS = 8
MAX_HP = 3
DEAGLE_BASE_RANGE_TILES = 4
SHOTGUN_BASE_DEPTH = 2
DIRECTIONS = {"left":(-1,0), "right":(1,0), "up":(0,-1), "down":(0,1)}

PLAYER_THEMES = [
    ("Red",   (239, 68, 68)),
    ("Blue",  (59, 130, 246)),
    ("Amber", (234, 179, 8)),
    ("Green", (34, 197, 94)),
]

def _in_bounds(c, r): return 0 <= c < GRID_COLUMNS and 0 <= r < GRID_ROWS

def new_room():
    return {
        "players": [],  # join order (names)
        "state": {
            "grid": {"cols": GRID_COLUMNS, "rows": GRID_ROWS},
            "actors": {},          # name -> dict (hp, col/row, facing, inventory)
            "theme_index": 0,
            "obstacles": [],       # {"type":"wall|water","col","row"}
            "items": [],           # {"type":"mystery_weapon|mystery_item","col","row"}
            "game_over": False,
        },
        "turn": 0,
    }

def _occupied(st, col, row, except_name=None):
    for n,a in st["actors"].items():
        if n == except_name: continue
        if a["hp"] > 0 and a["col"] == col and a["row"] == row:
            return True
    return False

def _ob_at(st, c, r):
    for ob in st["obstacles"]:
        if ob["col"] == c and ob["row"] == r:
            return ob
    return None

def _item_at(st, c, r):
    for it in st["items"]:
        if it["col"] == c and it["row"] == r:
            return it
    return None

def _spawn_position(st):
    ti = st["theme_index"]
    col = min(ti * 2, GRID_COLUMNS - 1)
    row = min(ti * 2, GRID_ROWS - 1)
    if not _occupied(st, col, row):
        return col, row
    # search nearest free
    for radius in range(1, max(GRID_COLUMNS, GRID_ROWS)):
        for dc in range(-radius, radius+1):
            for dr in range(-radius, radius+1):
                c, r = col+dc, row+dr
                if _in_bounds(c,r) and not _occupied(st, c, r):
                    return c, r
    return 0, 0

def _gen_level(st, num_players):
    st["obstacles"].clear()
    used = {(a["col"], a["row"]) for a in st["actors"].values()}
    min_ob = (GRID_COLUMNS * GRID_ROWS) // 15
    max_ob = (GRID_COLUMNS * GRID_ROWS) // 9 + 3
    obstacle_count = random.randint(min_ob, max_ob)

    def place_ob(kind):
        for _ in range(2000):
            c = random.randrange(0, GRID_COLUMNS)
            r = random.randrange(0, GRID_ROWS)
            if (c, r) in used: continue
            used.add((c, r))
            st["obstacles"].append({"type": kind, "col": c, "row": r})
            return

    for _ in range(obstacle_count):
        place_ob("wall" if random.random() < 0.6 else "water")

    # items
    st["items"].clear()
    base = num_players * 3
    n_items = random.randint(max(1, base-2), base+2)
    n_weapon = int(n_items // 2.5)
    n_misc = n_items - n_weapon

    def place_item(kind):
        for _ in range(2000):
            c = random.randrange(0, GRID_COLUMNS)
            r = random.randrange(0, GRID_ROWS)
            if (c, r) in used: continue
            used.add((c, r))
            st["items"].append({"type": kind, "col": c, "row": r})
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

    theme_i = st["theme_index"] % len(PLAYER_THEMES)
    st["theme_index"] += 1
    label, color = PLAYER_THEMES[theme_i]
    col, row = _spawn_position(st)

    st["actors"][name] = {
        "label": label, "color": color,
        "col": col, "row": row, "facing": "right",
        "hp": MAX_HP,
        # inventory/flags
        "has_deagle": False, "has_shotgun": False,
        "has_agility_boots": False, "has_scope": False, "has_shield": False,
        "has_grenade": False, "grenade_count": 0, "consumable_selected": None,
        "last_water_pos": None,
    }
    g["players"].append(name)
    _gen_level(st, max(2, len(g["players"])))
    return g

# ---------- highlight helpers ----------
def _deagle_tiles(st, p):
    if not p["has_deagle"]: return []
    rng = DEAGLE_BASE_RANGE_TILES + (1 if p["has_scope"] else 0)
    dc, dr = DIRECTIONS[p["facing"]]
    out = []
    c, r, steps = p["col"]+dc, p["row"]+dr, 0
    while _in_bounds(c, r) and steps < rng:
        out.append((c, r))
        steps += 1
        ob = _ob_at(st, c, r)
        if ob and ob["type"] == "wall":
            break
        c += dc; r += dr
    return out

def _shotgun_tiles(st, p):
    if not p["has_shotgun"]: return []
    depth_max = SHOTGUN_BASE_DEPTH + (1 if p["has_scope"] else 0)
    dc, dr = DIRECTIONS[p["facing"]]
    horizontal = p["facing"] in ("left", "right")
    pc, pr = (0, 1) if horizontal else (1, 0)
    blocked = {-1: False, 0: False, 1: False}
    out = set()
    for d in range(1, depth_max+1):
        for side in (-1, 0, 1):
            if blocked[side]: continue
            tc = p["col"] + dc*d + pc*side
            tr = p["row"] + dr*d + pr*side
            if not _in_bounds(tc, tr): continue
            # check for wall along this mini-ray
            w = False
            for s in range(1, d+1):
                cc = p["col"] + dc*s + pc*side
                rr = p["row"] + dr*s + pr*side
                ob = _ob_at(st, cc, rr)
                if ob and ob["type"] == "wall":
                    w = True; break
            if w:
                blocked[side] = True
                continue
            out.add((tc, tr))
    return sorted(out)

def _grenade_tiles(st, p):
    if not (p["grenade_count"] > 0 and p["consumable_selected"] == "Grenade"):
        return []
    dc, dr = DIRECTIONS[p["facing"]]
    horizontal = p["facing"] in ("left", "right")
    pc, pr = (0, 1) if horizontal else (1, 0)
    out = []
    for d in range(1, 4):
        for side in (-1, 0, 1):
            c = p["col"] + dc*d + pc*side
            r = p["row"] + dr*d + pr*side
            if _in_bounds(c, r):
                out.append((c, r))
    return out

# ---------- pickups ----------
def _pickup_if_item(st, p):
    it = _item_at(st, p["col"], p["row"])
    if not it:
        return
    t = it["type"]
    consumed = True
    if t == "mystery_weapon":
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
        st["items"] = [x for x in st["items"] if not (x["col"] == it["col"] and x["row"] == it["row"])]

# ---------- damage / turn ----------
def _alive_names(st):
    return [n for n,a in st["actors"].items() if a["hp"] > 0]

def _apply_damage(st, victim_name, amount=1):
    p = st["actors"].get(victim_name)
    if not p:
        return
    if amount > 0 and p["has_shield"]:
        p["has_shield"] = False
        return
    p["hp"] = max(0, p["hp"] - amount)
    st["game_over"] = len(_alive_names(st)) <= 1

def _end_turn_bookkeeping(st, name):
    p = st["actors"].get(name)
    if not p:
        return
    ob = _ob_at(st, p["col"], p["row"])
    if ob and ob["type"] == "water":
        pos = (p["col"], p["row"])
        last = p.get("last_water_pos")
        if last == pos:
            _apply_damage(st, name, 1)
        p["last_water_pos"] = pos
    else:
        p["last_water_pos"] = None
    p["consumable_selected"] = None  # clear consumable toggle each turn

def _advance_turn(g):
    st = g["state"]
    players = g["players"]
    if not players:
        return
    cur = players[g["turn"] % len(players)]
    _end_turn_bookkeeping(st, cur)
    for _ in range(len(players)):
        g["turn"] = (g["turn"] + 1) % len(players)
        nxt = players[g["turn"]]
        if st["actors"][nxt]["hp"] > 0:
            break

def _restart(g):
    st = g["state"]
    st["game_over"] = False
    # reset actors & reposition
    for name, a in st["actors"].items():
        a.update({
            "hp": MAX_HP,
            "has_deagle": False, "has_shotgun": False,
            "has_agility_boots": False, "has_scope": False, "has_shield": False,
            "has_grenade": False, "grenade_count": 0,
            "consumable_selected": None, "last_water_pos": None, "facing": "right",
        })
        a["col"], a["row"] = _spawn_position(st)
    _gen_level(st, max(2, len(g["players"])))
    g["turn"] = 0

# ---------- Public API ----------
def apply_move(game, move):
    """
    move = { "type": "...", "who": "<name>", ... }

    Types:
      restart                          # always allowed (even after game_over)
      self_ko {who}
      face {who, dir}
      step {who, dir, steps?=1}
      end_turn {who}
      toggle_grenade {who}
      shoot {who}                      # deagle
      shotgun {who}
      throw_grenade {who, target:{col,row}}
    """
    g = deepcopy(game)
    st = g["state"]
    if not g["players"]:
        return g

    t = move.get("type")

    # restart allowed anytime
    if t == "restart":
        _restart(g)
        return g

    # ignore any further actions during game_over
    if st["game_over"]:
        return g

    cur = g["players"][g["turn"] % len(g["players"])]
    if move.get("who") != cur:
        return g
    you = st["actors"].get(cur)
    if not you or you["hp"] <= 0:
        return g

    if t == "self_ko":
        _apply_damage(st, cur, you["hp"])
        if not st["game_over"]:
            _advance_turn(g)
        return g

    if t == "face":
        d = move.get("dir")
        if d in DIRECTIONS:
            you["facing"] = d
        return g

    if t == "step":
        d = move.get("dir")
        steps = int(move.get("steps", 1))
        if d in DIRECTIONS:
            dc, dr = DIRECTIONS[d]
            if steps not in (1, 2):
                steps = 1
            if steps == 2 and not you["has_agility_boots"]:
                steps = 1
            c, r = you["col"], you["row"]
            ok = True
            for _ in range(steps):
                nc, nr = c + dc, r + dr
                if not _in_bounds(nc, nr):
                    ok = False; break
                if _occupied(st, nc, nr, except_name=cur):
                    ok = False; break
                ob = _ob_at(st, nc, nr)
                if ob and ob["type"] == "wall":
                    ok = False; break
                c, r = nc, nr
            if ok:
                you["col"], you["row"] = c, r
                _pickup_if_item(st, you)
        _advance_turn(g)
        return g

    if t == "end_turn":
        _advance_turn(g)
        return g

    if t == "toggle_grenade":
        if you["has_grenade"] and you["grenade_count"] > 0:
            you["consumable_selected"] = None if you["consumable_selected"] == "Grenade" else "Grenade"
        return g

    if t == "shoot" and you["has_deagle"]:
        for c, r in _deagle_tiles(st, you):
            for name, a in st["actors"].items():
                if name == cur or a["hp"] <= 0:
                    continue
                if a["col"] == c and a["row"] == r:
                    _apply_damage(st, name, 1)
                    _advance_turn(g)
                    return g
        _advance_turn(g)
        return g

    if t == "shotgun" and you["has_shotgun"]:
        fan = set(_shotgun_tiles(st, you))
        for name, a in st["actors"].items():
            if name == cur or a["hp"] <= 0:
                continue
            if (a["col"], a["row"]) in fan:
                _apply_damage(st, name, 1)
        _advance_turn(g)
        return g

    if t == "throw_grenade" and you["grenade_count"] > 0 and you["consumable_selected"] == "Grenade":
        tgt = move.get("target") or {}
        tc, tr = tgt.get("col"), tgt.get("row")
        area = set(_grenade_tiles(st, you))
        if tc is not None and tr is not None and (tc, tr) in area:
            for name, a in st["actors"].items():
                if name == cur or a["hp"] <= 0:
                    continue
                if (a["col"], a["row"]) in area:
                    _apply_damage(st, name, 1)
            you["grenade_count"] -= 1
            if you["grenade_count"] <= 0:
                you["consumable_selected"] = None
            _advance_turn(g)
        return g

    return g
