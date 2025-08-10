from obstacle import Item

class Consumable(Item):
    def __init__(self, col: int, row: int, *, name: str = "Consumable", description: str | None = None):
        super().__init__(col, row, name=name, is_weapon=False, is_tool=False, is_consumable=True)
        self.description = description

class Grenade(Consumable):
    def __init__(self, col: int, row: int):
        super().__init__(col, row, name="Grenade",
                         description="Right-click a red tile in the 3×3 slab ahead to throw. Ignores walls. One use.")
    def on_pickup(self, player, game=None) -> bool:
        # allow stacking grenades; duplicates are fine because they have a count
        player.grenade_count += 1
        return True

class Shield(Consumable):
    def __init__(self, col: int, row: int):
        super().__init__(col, row, name="Shield",
                         description="Blocks the next damage you would take, then breaks.")
    def on_pickup(self, player, game=None) -> bool:
        if player.has_shield:
            return False
        player.has_shield = True
        return True
