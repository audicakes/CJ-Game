# game/engine.py
from copy import deepcopy

def new_room():
    return {"players": [], "state": {}, "turn": 0}

def join(game, name):
    g = deepcopy(game)
    if name not in g["players"]:
        g["players"].append(name)
    return g

def apply_move(game, move):
    g = deepcopy(game)
    t = g.get("turn", 0)
    # TODO: apply your move to g["state"] here
    if g["players"]:
        g["turn"] = (t + 1) % len(g["players"])
    return g
