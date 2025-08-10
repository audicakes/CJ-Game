# obstacle.py
# Obstacle hierarchy + Item integrated here (with type flags).

class Obstacle:
    """
    Superclass for anything that sits on a tile by itself.
    """
    def __init__(self, col: int, row: int, *, blocks_movement: bool, blocks_shots: bool, color=(90, 90, 90)):
        self.col = col
        self.row = row
        self.blocks_movement = blocks_movement
        self.blocks_shots = blocks_shots
        self.color = color

    def pos(self):
        return (self.col, self.row)

class Wall(Obstacle):
    """
    Blocks player movement AND shots (line-of-sight).
    """
    def __init__(self, col: int, row: int):
        super().__init__(col, row, blocks_movement=True, blocks_shots=True, color=(70, 88, 120))


class Water(Obstacle):
    """
    Does NOT block player movement; shots can pass through.
    """
    def __init__(self, col: int, row: int):
        super().__init__(col, row, blocks_movement=False, blocks_shots=False, color=(40, 110, 140))

class Item(Obstacle):
    """
    Collectible item placed on the grid. Does NOT block movement or shots.
    Flags indicate category for future logic/routing.
    """
    def __init__(self, col: int, row: int, *, name: str = "Item",
                 is_weapon: bool = False, is_tool: bool = False, is_consumable: bool = False):
        super().__init__(col, row, blocks_movement=False, blocks_shots=False, color=(185, 185, 185))
        self.name = name
        self.is_weapon = is_weapon
        self.is_tool = is_tool
        self.is_consumable = is_consumable

    def on_pickup(self, player, game=None) -> None:
        """Override in subclasses (e.g., Deagle sets player.has_deagle=True, Grenade increments count)."""
        pass
