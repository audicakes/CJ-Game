from obstacle import Item

class Tool(Item):
    def __init__(self, col: int, row: int, *, name: str = "Tool", description: str | None = None):
        super().__init__(col, row, name=name, is_weapon=False, is_tool=True, is_consumable=False)
        self.description = description
    def on_pickup(self, player, game=None) -> bool:
        return True

class AgilityBoots(Tool):
    def __init__(self, col: int, row: int):
        super().__init__(col, row, name="Agility Boots",
                         description="Hold Shift + Arrow to move 2 tiles straight.")
    def on_pickup(self, player, game=None) -> bool:
        if player.has_agility_boots:
            return False
        player.has_agility_boots = True
        return True

class Scope(Tool):
    def __init__(self, col: int, row: int):
        super().__init__(col, row, name="Scope",
                         description="Your weapons reach 1 extra tile forward.")
    def on_pickup(self, player, game=None) -> bool:
        if player.has_scope:
            return False
        player.has_scope = True
        return True
