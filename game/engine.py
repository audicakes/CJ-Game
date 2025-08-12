# game/engine.py
from copy import deepcopy
import random

# --- Board / rules config ---
GRID_COLUMNS = 11
GRID_ROWS = 8
MAX_HP = 5
DEAGLE_BASE_RANGE_TILES = 5
SHOTGUN_BASE_DEPTH = 2
UZI_BASE_DEPTH = 3  # 3x3 slab depth for Akimbo Uzis (scope can add +1)
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

def _random_empty_tile(st):
    """Return (c, r) for a random empty, non-obstacle tile (None if full)."""
    occupied = {(a["col"], a["row"]) for a in st["actors"].values() if a["hp"] > 0}
    blocked  = {(ob["col"], ob["row"]) for ob in st["obstacles"]}  # walls & water both block items
    items    = {(it["col"], it["row"]) for it in st["items"]}
    used = occupied | blocked | items
    for _ in range(2000):
        c = random.randrange(0, GRID_COLUMNS)
        r = random.randrange(0, GRID_ROWS)
        if (c, r) not in used:
            return (c, r)
    # Fallback deterministic sweep
    for r in range(GRID_ROWS):
        for c in range(GRID_COLUMNS):
            if (c, r) not in used:
                return (c, r)
    return None

def _spawn_one_item_if_none_left(st, kind):
    """If there are no items of 'kind' on the board, spawn exactly one."""
    if any(it["type"] == kind for it in st["items"]):
        return
    pos = _random_empty_tile(st)
    if pos:
        c, r = pos
        st["items"].append({"type": kind, "col": c, "row": r})

def _dist(a, b):
    # Chebyshev distance fits grid movement well; you could use Manhattan if you prefer.
    return max(abs(a[0]-b[0]), abs(a[1]-b[1]))

def _spawn_position(st):
    """Pick the empty, non-wall tile with the largest min distance to all actors."""
    occupied = {(a["col"], a["row"]) for a in st["actors"].values() if a["hp"] > 0}
    walls = {(ob["col"], ob["row"]) for ob in st["obstacles"] if ob["type"] == "wall"}

    # Precompute existing actor positions
    others = [(a["col"], a["row"]) for a in st["actors"].values() if a["hp"] > 0]

    best_pos = None
    best_score = -1

    for r in range(GRID_ROWS):
        for c in range(GRID_COLUMNS):
            pos = (c, r)
            if pos in occupied or pos in walls:
                continue

            if others:
                mind = min(_dist(pos, o) for o in others)
            else:
                mind = 999  # first player can take any spot

            # Small tie-breakers so we avoid edges/walls even if distance ties
            near_wall = 1 if any((c+dc, r+dr) in walls for dc,dr in [(-1,0),(1,0),(0,-1),(0,1)]) else 0
            edge_penalty = 1 if (c in (0, GRID_COLUMNS-1) or r in (0, GRID_ROWS-1)) else 0

            score = (mind * 10) - (near_wall * 2) - (edge_penalty * 1)

            if score > best_score:
                best_score = score
                best_pos = pos

    return best_pos or (0, 0)


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
    base = num_players * 5
    n_items = random.randint(max(1, base), base)
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
        "has_deagle": False, "has_shotgun": False, "has_uzis": False, "has_quickshot": False,
        "has_agility_boots": False, "has_scope": False, "has_shield": False,
        "has_grenade": False, "grenade_count": 0, "consumable_selected": None, #consumable is grenade only ig 
        "scope_toggled": False, "piercing_toggled": False,
        "last_water_pos": None, "has_piercing": False, "piercing_count": 0,
        "has_lucky_clover": False, "shotgun_cooldown": 0, "qs_move_used": False

    }
    g["players"].append(name)
    _gen_level(st, max(2, len(g["players"])))
    return g

# ---------- highlight helpers ----------
def _deagle_tiles(st, p):
    if not p["has_deagle"]: return []
    rng = DEAGLE_BASE_RANGE_TILES + (1 if (p.get("has_scope") and p.get("scope_toggled")) else 0)
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
    depth_max = SHOTGUN_BASE_DEPTH + (1 if (p.get("has_scope") and p.get("scope_toggled")) else 0)
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

def _uzis_tiles(st, p):
    """
    3x3 slab in front, EXCLUDING the middle column (i.e., only side -1 and +1),
    depth = UZI_BASE_DEPTH (+1 if Scope is toggled). Walls can block per side.
    """
    if not p.get("has_uzis"):
        return []
    depth_max = UZI_BASE_DEPTH + (1 if (p.get("has_scope") and p.get("scope_toggled")) else 0)
    dc, dr = DIRECTIONS[p["facing"]]
    horizontal = p["facing"] in ("left", "right")
    pc, pr = (0, 1) if horizontal else (1, 0)
    # We exclude the center column (side==0), and track wall blocking per side
    blocked = {-1: False, 1: False}
    out = set()
    for d in range(1, depth_max + 1):
        for side in (-1, 1):  # NO center
            if blocked[side]:
                continue
            tc = p["col"] + dc * d + pc * side
            tr = p["row"] + dr * d + pr * side
            if not _in_bounds(tc, tr):
                continue
            # check walls along this mini-ray to reach (tc,tr)
            blocked_here = False
            for s in range(1, d + 1):
                cc = p["col"] + dc * s + pc * side
                rr = p["row"] + dr * s + pr * side
                ob = _ob_at(st, cc, rr)
                if ob and ob["type"] == "wall":
                    blocked_here = True
                    break
            if blocked_here:
                blocked[side] = True
                continue
            out.add((tc, tr))
    return sorted(out)

def _uzis_tiles_ignore_walls(st, p):
    """Akimbo Uzis area when walls are ignored: 3x(depth) slab excluding center lane."""
    if not p.get("has_uzis"):
        return []
    depth_max = UZI_BASE_DEPTH + (1 if (p.get("has_scope") and p.get("scope_toggled")) else 0)
    dc, dr = DIRECTIONS[p["facing"]]
    horizontal = p["facing"] in ("left", "right")
    pc, pr = (0, 1) if horizontal else (1, 0)
    tiles = []
    for d in range(1, depth_max + 1):
        for side in (-1, 1):  # exclude center lane
            c = p["col"] + dc * d + pc * side
            r = p["row"] + dr * d + pr * side
            if _in_bounds(c, r):
                tiles.append((c, r))
    return tiles

def weapon_tiles_ignore_walls(st, p, pattern, range_or_depth, width=1, exclude_center=False):
    """
    Generalized tile generator for weapons that ignore walls.
    pattern: 'line' or 'fan'
    range_or_depth: int, max tiles forward
    width: for 'fan', how many tiles wide at each depth (odd number, e.g., 3)
    exclude_center: if True (fan only), omits the center lane (side == 0)
    """
    tiles = []
    dc, dr = DIRECTIONS[p["facing"]]
    if pattern == "line":
        c, r = p["col"] + dc, p["row"] + dr
        for _ in range(range_or_depth):
            if not _in_bounds(c, r):
                break
            tiles.append((c, r))
            c += dc
            r += dr
    elif pattern == "fan":
        half_span = (width - 1) // 2
        horizontal = p["facing"] in ("left", "right")
        pc, pr = (0, 1) if horizontal else (1, 0)
        for d in range(1, range_or_depth + 1):
            for side in range(-half_span, half_span + 1):
                if exclude_center and side == 0:
                    continue
                tc = p["col"] + dc * d + pc * side
                tr = p["row"] + dr * d + pr * side
                if _in_bounds(tc, tr):
                    tiles.append((tc, tr))
    return tiles

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

def _maybe_clover_bonus(st, attacker_name, victims):
    atk = st["actors"].get(attacker_name)
    if not atk or not atk.get("has_lucky_clover") or not victims:
        return
    # 50% chance to add +1 to exactly one victim of THIS shot
    if random.random() < 0.5:
        _apply_damage(st, random.choice(victims), 1)
        atk["has_lucky_clover"] = False  # consumed when it procs

# ---------- pickups ----------
def _pickup_if_item(st, p):
    it = _item_at(st, p["col"], p["row"])
    if not it:
        return
    t = it["type"]
    consumed = True
    #kev
    if t == "mystery_weapon":
        # only one weapon at a time
        p["has_deagle"] = False
        p["has_shotgun"] = False
        p["has_uzis"]   = False
        p["has_quickshot"] = False
        give = random.choice(["deagle", "shotgun", "uzis", "quickshot"])
        if give == "deagle":      p["has_deagle"] = True
        elif give == "shotgun":   p["has_shotgun"] = True
        elif give == "uzis":      p["has_uzis"] = True
        else:                     p["has_quickshot"] = True

    elif t == "mystery_item":
        picks = []
        if not p["has_agility_boots"]: picks.append("agility")
        if not p["has_scope"]:         picks.append("scope")
        if not p["has_shield"]:        picks.append("shield")
        if not p["has_grenade"]:       picks.append("grenade")
        if not p["has_piercing"]:      picks.append("piercing")
        if not p["has_lucky_clover"]:  picks.append("clover")

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
            elif give == "piercing":
                p["has_piercing"] = True
                p["piercing_count"] = max(p["piercing_count"], 0) + 1
            elif give == "clover":
                p["has_lucky_clover"] = True
    if consumed:
        # Remove the picked-up item from the map
        st["items"] = [x for x in st["items"] if not (x["col"] == it["col"] and x["row"] == it["row"])]
        # Keep at least one of each item type on the board
        _spawn_one_item_if_none_left(st, "mystery_weapon")
        _spawn_one_item_if_none_left(st, "mystery_item")


# ---------- damage / turn ----------
def _alive_names(st):
    return [n for n,a in st["actors"].items() if a["hp"] > 0]

def _apply_damage(st, victim_name, amount=1): #kev
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
        p["consumable_selected"] = None          # only Grenade uses this
        p["scope_toggled"] = False               # Scope is per-turn
        p["piercing_toggled"] = False            # Piercing “armed” flag resets each turn
    # decrement shotgun cooldown if active
    if p.get("shotgun_cooldown", 0) > 0:
        p["shotgun_cooldown"] -= 1
    # allow Quickshot free-move again next turn
    p["qs_move_used"] = False

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
    # Reset stats/inventory
    for a in st["actors"].values():
        a.update({ #kev
            "hp": MAX_HP,
            "has_deagle": False, "has_shotgun": False, "has_uzis": False, "has_quickshot": False, "qs_move_used": False,
            "has_agility_boots": False, "has_scope": False, "has_shield": False,
            "has_grenade": False, "grenade_count": 0, "has_piercing": False, "piercing_count": 0,
            "consumable_selected": None, "scope_toggled": False, "piercing_toggled": False,
            "last_water_pos": None, "facing": "right",
            "has_piercing": False, "piercing_count": 0, "has_lucky_clover": False, "shotgun_cooldown": 0,
        })
    # Greedy farthest placement for all current players
    names = list(g["players"])
    # Clear positions temporarily
    for a in st["actors"].values():
        a["col"], a["row"] = -999, -999
    placed = []
    walls = {(ob["col"], ob["row"]) for ob in st["obstacles"] if ob["type"] == "wall"}
    def best_spot():
        best = None; best_score = -1
        for r in range(GRID_ROWS):
            for c in range(GRID_COLUMNS):
                pos = (c, r)
                if pos in walls or pos in placed:
                    continue
                # distance to already placed actors (use large if none placed yet)
                mind = min((_dist(pos, p) for p in placed), default=999)
                # tie-breakers
                near_wall = 1 if any((c+dc, r+dr) in walls for dc,dr in [(-1,0),(1,0),(0,-1),(0,1)]) else 0
                edge_penalty = 1 if (c in (0, GRID_COLUMNS-1) or r in (0, GRID_ROWS-1)) else 0
                score = (mind * 10) - (near_wall * 2) - (edge_penalty * 1)
                if score > best_score:
                    best_score = score; best = pos
        return best
    for name in names:
        pos = best_spot() or (0, 0)
        st["actors"][name]["col"], st["actors"][name]["row"] = pos
        placed.append(pos)
    # Regenerate obstacles/items fresh for this player count
    _gen_level(st, max(2, len(names)))
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
    
    # Quickshot gating: after using the free move, only face/aim, quickshot, or end_turn are allowed
    if you.get("has_quickshot") and you.get("qs_move_used", False) and t not in ("face", "quickshot", "end_turn", "toggle_scope", "toggle_piercing"):
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
        # Quickshot rule: after the free move, you cannot step again this turn
        if you.get("has_quickshot") and you.get("qs_move_used", False):
            return g
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
                # Quickshot: one free move that does NOT end the turn
                if you.get("has_quickshot") and not you.get("qs_move_used", False):
                    you["qs_move_used"] = True
                    return g
        _advance_turn(g)
        return g

    if t == "end_turn":
        _advance_turn(g)
        return g

    if t == "toggle_grenade":
        if you["has_grenade"] and you["grenade_count"] > 0:
            you["consumable_selected"] = None if you["consumable_selected"] == "Grenade" else "Grenade"
        return g
    if t == "toggle_piercing":
        if you.get("has_piercing") and you.get("piercing_count", 0) > 0:
            you["piercing_toggled"] = not you.get("piercing_toggled", False)
        return g
    if t == "toggle_scope":
        if you.get("has_scope"):
            you["scope_toggled"] = not you.get("scope_toggled", False)
        return g

    #kev
    if t == "shoot" and you["has_deagle"]:
        pierce = (you.get("piercing_toggled") and you.get("piercing_count", 0) > 0)
        tiles = weapon_tiles_ignore_walls(
            st, you, "line",
            DEAGLE_BASE_RANGE_TILES + (1 if (you.get("has_scope") and you.get("consumable_selected") == "Scope") else 0)
        )
        victims = []
        for c, r in tiles:
            for name, a in st["actors"].items():
                if name == cur or a["hp"] <= 0: continue
                if a["col"] == c and a["row"] == r:
                    victims.append(name)
            if victims and not pierce:  # normal shot stops at first victim
                break
        for v in victims:
            _apply_damage(st, v, 2)
        _maybe_clover_bonus(st, cur, victims)
        if pierce:
            you["piercing_count"] -= 1
            if you["piercing_count"] <= 0:
                you["has_piercing"] = False
                you["piercing_toggled"] = False
            else:
                you["piercing_toggled"] = True   # stay armed if charges remain
        _advance_turn(g)
        return g

    if t == "shotgun" and you["has_shotgun"]:
        # Prevent shooting if on cooldown
        if you.get("shotgun_cooldown", 0) > 0:
            return g
        pierce = (you.get("piercing_toggled") and you.get("piercing_count", 0) > 0)
        fan = set(weapon_tiles_ignore_walls(
            st, you, "fan",
            SHOTGUN_BASE_DEPTH + (1 if (you.get("has_scope") and you.get("consumable_selected") == "Scope") else 0),
            width=3
        ))
        victims = []
        for name, a in st["actors"].items():
            if name == cur or a["hp"] <= 0:
                continue
            if (a["col"], a["row"]) in fan:
                victims.append(name)
        for v in victims:
            _apply_damage(st, v, 2)
        _maybe_clover_bonus(st, cur, victims)
        if pierce:
            you["piercing_count"] -= 1
            if you["piercing_count"] <= 0:
                you["has_piercing"] = False
                you["piercing_toggled"] = False
            else:
                you["piercing_toggled"] = True   # stay armed if charges remain
        # Apply kickback (move backwards 1 tile if possible)
        dc, dr = DIRECTIONS[you["facing"]]
        back_c, back_r = you["col"] - dc, you["row"] - dr
        if _in_bounds(back_c, back_r) and not _occupied(st, back_c, back_r) and not (_ob_at(st, back_c, back_r) and _ob_at(st, back_c, back_r)["type"] == "wall"):
            you["col"], you["row"] = back_c, back_r
        # Set shotgun cooldown (1 turn)
        you["shotgun_cooldown"] = 2
        _advance_turn(g)
        return g

    if t == "uzi" and you.get("has_uzis"):
        pierce = (you.get("piercing_toggled") and you.get("piercing_count", 0) > 0)
        tiles = (
            weapon_tiles_ignore_walls(
                st, you, "fan",
                UZI_BASE_DEPTH + (1 if (you.get("has_scope") and you.get("consumable_selected") == "Scope") else 0),
                width=3,
                exclude_center=True
            )
            if pierce else _uzis_tiles(st, you)
        )
        victims = []
        for name, a in st["actors"].items():
            if name == cur or a["hp"] <= 0:
                continue
            if (a["col"], a["row"]) in tiles:
                victims.append(name)
        for v in victims:
            _apply_damage(st, v, 1)
        _maybe_clover_bonus(st, cur, victims)
        if pierce:
            you["piercing_count"] -= 1
            if you["piercing_count"] <= 0:
                you["has_piercing"] = False
                you["piercing_toggled"] = False
            else:
                you["piercing_toggled"] = True   # stay armed if charges remain
        _advance_turn(g)
        return g
    
    if t == "quickshot" and you.get("has_quickshot"):
        pierce = (you.get("piercing_toggled") and you.get("piercing_count", 0) > 0)
        # Range: 1 tile forward (+1 if Scope is toggled this turn). Walls block. Stops at first victim.
        dc, dr = DIRECTIONS[you["facing"]]
        rng = 1 + (1 if (you.get("has_scope") and you.get("consumable_selected") == "Scope") else 0)
        victims = []
        c, r = you["col"], you["row"]
        for _ in range(rng):
            c += dc; r += dr
            if not _in_bounds(c, r):
                break
            ob = _ob_at(st, c, r)
            if ob and ob["type"] == "wall":
                break
            # first victim in range
            for name, a in st["actors"].items():
                if name == cur or a["hp"] <= 0: 
                    continue
                if a["col"] == c and a["row"] == r:
                    victims.append(name)
                    break
            if victims:
                break
        for v in victims:
            _apply_damage(st, v, 1)
        _maybe_clover_bonus(st, cur, victims)
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
                    _apply_damage(st, name, 2)
            you["grenade_count"] -= 1
            if you["grenade_count"] <= 0:
                you["consumable_selected"] = None
            _advance_turn(g)
        return g

    return g
