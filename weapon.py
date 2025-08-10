from obstacle import Item

class Weapon(Item):
    def __init__(self, col: int, row: int, *, name: str = "Weapon", description: str | None = None):
        super().__init__(col, row, name=name, is_weapon=True, is_tool=False, is_consumable=False)
        self.description = description

class Deagle(Weapon):
    def __init__(self, col: int, row: int):
        super().__init__(col, row, name="Deagle",
                         description="Right-click a red tile on your facing line to shoot.")
    def on_pickup(self, player, game=None) -> bool:
        if player.has_deagle:   # prevent duplicate
            return False
        player.has_deagle = True
        return True

class Shotgun(Weapon):
    def __init__(self, col: int, row: int):
        super().__init__(col, row, name="Shotgun",
                         description="Right-click a red tile in the 3-wide fan ahead to blast.")
    def on_pickup(self, player, game=None) -> bool:
        if player.has_shotgun:
            return False
        player.has_shotgun = True
        return True
