import pygame
import sys
import time
import random
from weapon import Deagle, Shotgun
from tool import AgilityBoots, Scope
from consumable import Grenade, Shield
from obstacle import Wall, Water, Item

# -----------------------------
# Config
# -----------------------------
GRID_COLUMNS = 11
GRID_ROWS = 8
CELL_SIZE = 72
CELL_MARGIN = 2
HUD_HEIGHT = 80
SIDEBAR_WIDTH = 260

MAP_WIDTH_PX = GRID_COLUMNS * CELL_SIZE
MAP_HEIGHT_PX = GRID_ROWS * CELL_SIZE
WINDOW_WIDTH = MAP_WIDTH_PX + SIDEBAR_WIDTH
WINDOW_HEIGHT = MAP_HEIGHT_PX + HUD_HEIGHT
FPS = 60

# Colors
BACKGROUND_COLOR = (11, 17, 24)
GRID_COLOR = (34, 48, 66)
WHITE = (240, 245, 250)
TEXT_MUTED = (138, 160, 181)
BUTTON_BG = (18, 27, 39)
BUTTON_BG_HOVER = (22, 34, 50)
BUTTON_BORDER = (38, 52, 70)
HUD_BG = (15, 22, 32)
SIDEBAR_BG = (16, 24, 35)

PLAYER_THEMES = [
    ("Red",   (239, 68, 68),  (248, 113, 113)),
    ("Blue",  (59, 130, 246), (96, 165, 250)),
    ("Amber", (234, 179, 8),  (250, 204, 21)),
    ("Green", (34, 197, 94),  (74, 222, 128)),
]
HP_COLOR = (34, 197, 94)
HP_EMPTY_COLOR = (52, 70, 87)
MOVE_HIGHLIGHT = (144, 238, 144, 110)   # light green
SHOOT_HIGHLIGHT = (255, 99, 71, 110)    # light red

MAX_HP = 3
DEAGLE_BASE_RANGE_TILES = 4
SHOTGUN_BASE_DEPTH = 2  # rows forward; width is always 3

DIRECTIONS = {
    'left':  (-1, 0),
    'right': ( 1, 0),
    'up':    ( 0,-1),
    'down':  ( 0, 1),
}

# -----------------------------
# Helpers
# -----------------------------
def in_bounds(col: int, row: int) -> bool:
    return 0 <= col < GRID_COLUMNS and 0 <= row < GRID_ROWS

def facing_from_delta(dx: int, dy: int) -> str:
    if abs(dx) >= abs(dy):
        return 'right' if dx > 0 else 'left'
    else:
        return 'down' if dy > 0 else 'up'

def wrap_text(font: pygame.font.Font, text: str, color, max_width: int) -> pygame.Surface:
    words = text.split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current: lines.append(current)
            current = w
    if current: lines.append(current)
    line_surfaces = [font.render(line, True, color) for line in lines]
    width = max((s.get_width() for s in line_surfaces), default=0)
    height = sum(s.get_height() for s in line_surfaces)
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    y = 0
    for s in line_surfaces:
        surface.blit(s, (0, y)); y += s.get_height()
    return surface

# -----------------------------
# Classes
# -----------------------------
class Player:
    def __init__(self, player_id, label, col, row, color, light_color, facing):
        self.id = player_id
        self.label = label
        self.col = col
        self.row = row
        self.color = color
        self.light_color = light_color
        self.facing = facing
        self.hp = MAX_HP
        self.blink_until = 0.0

        # inventory flags
        self.has_deagle = False
        self.has_shotgun = False
        self.has_agility_boots = False
        self.has_scope = False
        self.has_shield = False
        self.grenade_count = 0
        self.has_grenade = False  # Add this line

        # UI selection
        self.consumable_selected = None  # e.g., "Grenade"

        # hazards
        self.last_water_pos = None  # (col,row) recorded at end of previous turn if on water

    def position(self):
        return (self.col, self.row)

# -----------------------------
# Game State
# -----------------------------

class UnknownItem(Item):
    def __init__(self, col, row):
        super().__init__(col, row, name="Unknown", is_weapon=False, is_tool=False, is_consumable=False)

    def on_pickup(self, player, game=None):
        # List all possible item classes (no duplicates allowed)
        possible = []
        if not player.has_deagle:
            possible.append(Deagle)
        if not player.has_shotgun:
            possible.append(Shotgun)
        if not player.has_agility_boots:
            possible.append(AgilityBoots)
        if not player.has_scope:
            possible.append(Scope)
        if not player.has_shield:
            possible.append(Shield)
        if not player.has_grenade:  # We'll add this property below
            possible.append(Grenade)
        if not possible:
            return False  # nothing to give
        ItemClass = random.choice(possible)
        # Mark grenade as "owned" after pickup
        if ItemClass is Grenade:
            player.has_grenade = True
            player.grenade_count = 1
        else:
            ItemClass(self.col, self.row).on_pickup(player, game)
        return True

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Turn-Based Grid RPG – Python")
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)
        self.font_small = pygame.font.SysFont(None, 20)
        self.font_big = pygame.font.SysFont(None, 36, bold=True)

        self.current_player_index = 0
        self.game_over = False

        self.awaiting_player_count = True
        self.num_players = 2

        self.button_restart = pygame.Rect(MAP_WIDTH_PX - 150, 16, 120, 36)

        self.players = []
        self.obstacles = []
        self.items = []

        # Sidebar UI state
        self.sidebar_item_rects = []    # [(player_index, key, rect)]
        self.sidebar_hover_item = None  # (player_index, key, rect, description)
        self.mouse_pos = (0, 0)

    # -------------------------
    # Random generation / setup
    # -------------------------
    def setup_players(self, count: int):
        self.players = []
        used_positions = set()
        for i in range(count):
            name, color, light = PLAYER_THEMES[i]
            while True:
                col = random.randrange(0, GRID_COLUMNS)
                row = random.randrange(0, GRID_ROWS)
                if (col, row) not in used_positions:
                    used_positions.add((col, row))
                    break
            facing = random.choice(list(DIRECTIONS.keys()))
            self.players.append(Player(i, name, col, row, color, light, facing))
        return used_positions

    def generate_random_level(self):
        self.game_over = False
        self.current_player_index = 0
        for player in self.players:
            player.hp = MAX_HP
            player.blink_until = 0.0
            player.has_deagle = False
            player.has_shotgun = False
            player.has_agility_boots = False
            player.has_scope = False
            player.has_shield = False
            player.has_grenade = False   # Add this line
            player.grenade_count = 0
            player.consumable_selected = None
            player.last_water_pos = None

        used_positions = set((p.col, p.row) for p in self.players)

        # obstacles
        self.obstacles = []
        min_obstacles = (GRID_COLUMNS * GRID_ROWS) // 10
        max_obstacles = (GRID_COLUMNS * GRID_ROWS) // 6
        obstacle_count = random.randint(min_obstacles, max_obstacles)
        tries_total = 0
        while len(self.obstacles) < obstacle_count and tries_total < obstacle_count * 50:
            tries_total += 1
            col = random.randrange(0, GRID_COLUMNS)
            row = random.randrange(0, GRID_ROWS)
            if (col, row) in used_positions:
                continue
            used_positions.add((col, row))
            self.obstacles.append(Wall(col, row) if random.random() < 0.6 else Water(col, row))

        # items: players*2 ± 2 (at least 1)
        base_items = self.num_players * 2
        min_items = max(1, base_items - 2)
        max_items = base_items + 2
        target_item_count = random.randint(min_items, max_items)

        self.items = []
        placed = 0
        tries_items = 0
        while placed < target_item_count and tries_items < 2000:
            tries_items += 1
            col = random.randrange(0, GRID_COLUMNS)
            row = random.randrange(0, GRID_ROWS)
            if (col, row) in used_positions:
                continue
            used_positions.add((col, row))
            self.items.append(UnknownItem(col, row))
            placed += 1

        self.sidebar_hover_item = None

    def full_reset_with_player_count(self, count: int):
        self.awaiting_player_count = False
        self.num_players = count
        self.setup_players(count)
        self.generate_random_level()

    # -------------------------
    # Derived state
    # -------------------------
    def alive_player_indices(self):
        return [i for i, p in enumerate(self.players) if p.hp > 0]

    def other_player_indices(self):
        return [i for i in range(len(self.players)) if i != self.current_player_index and self.players[i].hp > 0]

    def is_occupied(self, col: int, row: int) -> bool:
        return any(p.col == col and p.row == row and p.hp > 0 for p in self.players)

    def obstacle_at(self, col: int, row: int):
        for ob in self.obstacles:
            if ob.col == col and ob.row == row:
                return ob
        return None

    def item_at(self, col: int, row: int):
        for it in self.items:
            if it.col == col and it.row == row:
                return it
        return None

    def player_inventory(self, player: Player):
        """Return list of tuples (key, display_name, description)."""
        inventory = []
        if player.has_deagle:
            inventory.append(("Deagle", "Deagle", "Right-click a red tile on your facing line to shoot."))
        if player.has_shotgun:
            inventory.append(("Shotgun", "Shotgun", "Right-click a red tile in the 3-wide fan ahead to blast."))
        if player.has_agility_boots:
            inventory.append(("Agility Boots", "Agility Boots", "Hold Shift + Arrow to move 2 tiles straight."))
        if player.has_scope:
            inventory.append(("Scope", "Scope", "Your weapons reach 1 extra tile forward."))
        if player.has_grenade and player.grenade_count > 0:
            inventory.append(("Grenade", f"Grenade", "Right-click a red tile in the 3×3 slab ahead to throw. Ignores walls. One use."))
        if player.has_shield:
            inventory.append(("Shield", "Shield", "Blocks the next damage you would take, then breaks."))
        return inventory

    # -------------------------
    # Logic
    # -------------------------
    def tiles_for_move(self, player: Player):
        tiles = []
        for dcol, drow in [(-1,0),(1,0),(0,-1),(0,1)]:
            col1, row1 = player.col + dcol, player.row + drow
            if in_bounds(col1, row1) and not self.is_occupied(col1, row1):
                ob1 = self.obstacle_at(col1, row1)
                if not (ob1 and ob1.blocks_movement):
                    tiles.append((col1, row1))
                    if player.has_agility_boots:
                        col2, row2 = col1 + dcol, row1 + drow
                        if in_bounds(col2, row2) and not self.is_occupied(col2, row2):
                            ob2 = self.obstacle_at(col2, row2)
                            if not (ob2 and ob2.blocks_movement):
                                tiles.append((col2, row2))
        return tiles

    def deagle_range_tiles(self, player: Player):
        if not player.has_deagle:
            return []
        rng = DEAGLE_BASE_RANGE_TILES + (1 if player.has_scope else 0)
        tiles = []
        dcol, drow = DIRECTIONS[player.facing]
        col, row = player.col + dcol, player.row + drow
        steps = 0
        while in_bounds(col, row) and steps < rng:
            tiles.append((col, row))
            ob = self.obstacle_at(col, row)
            steps += 1
            if ob and ob.blocks_shots:
                break
            col += dcol
            row += drow
        return tiles

    def shotgun_fan_tiles(self, player: Player):
        if not player.has_shotgun:
            return []
        depth_max = SHOTGUN_BASE_DEPTH + (1 if player.has_scope else 0)
        tiles = set()
        dcol, drow = DIRECTIONS[player.facing]
        # perpendicular unit
        if player.facing in ('left', 'right'):
            pcol, prow = (0, 1)
        else:
            pcol, prow = (1, 0)
        for depth in range(1, depth_max + 1):
            for side in (-1, 0, 1):
                tcol = player.col + dcol*depth + pcol*side
                trow = player.row + drow*depth + prow*side
                if not in_bounds(tcol, trow): 
                    continue
                # Walk forward, then sideways; any wall on the way blocks only tiles behind it
                blocked = False
                # forward steps
                for k in range(1, depth+1):
                    pc, pr = player.col + dcol*k, player.row + drow*k
                    ob = self.obstacle_at(pc, pr)
                    if ob and ob.blocks_shots:
                        # If the wall is before the target tile, block this tile and all further ones in this direction
                        if (pc, pr) != (tcol, trow):
                            blocked = True
                            break
                if blocked:
                    continue
                # sideways at the end (skip if side==0)
                if side != 0:
                    pc, pr = tcol, trow
                    ob = self.obstacle_at(pc, pr)
                    if ob and ob.blocks_shots:
                        continue  # can't shoot into a wall on the side
                tiles.add((tcol, trow))
        return sorted(list(tiles))

    def grenade_slab_tiles(self, player: Player):
        if player.grenade_count <= 0 or player.consumable_selected != "Grenade":
            return []
        tiles = []
        dcol, drow = DIRECTIONS[player.facing]
        # perpendicular unit
        if player.facing in ('left', 'right'):
            pcol, prow = (0, 1)
        else:
            pcol, prow = (1, 0)
        for depth in range(1, 4):
            for side in (-1, 0, 1):
                col = player.col + dcol*depth + pcol*side
                row = player.row + drow*depth + prow*side
                if in_bounds(col, row):
                    tiles.append((col, row))
        return tiles

    def collect_if_item(self, player: Player):
        item = self.item_at(player.col, player.row)
        if not item:
            return
        consumed = True
        if hasattr(item, "on_pickup"):
            res = item.on_pickup(player, game=self)
            consumed = (res is not False)  # treat None as consumed
        if consumed:
            self.items = [x for x in self.items if x is not item]  # remove from board

    def apply_damage(self, victim: Player, amount=1):
        # Shield check
        if victim.has_shield and amount > 0:
            victim.has_shield = False
            victim.blink_until = time.time() + 0.4  # small flash to indicate shield proc
            return
        victim.hp = max(0, victim.hp - amount)
        victim.blink_until = time.time() + 0.8
        alive_count = sum(1 for pl in self.players if pl.hp > 0)
        if alive_count <= 1:
            self.game_over = True

    def try_move_exact(self, player: Player, dcol: int, drow: int, steps: int) -> bool:
        if steps not in (1, 2): steps = 1
        if steps == 2 and not player.has_agility_boots: steps = 1
        col, row = player.col, player.row
        for _ in range(steps):
            next_col, next_row = col + dcol, row + drow
            if not in_bounds(next_col, next_row): return False
            if self.is_occupied(next_col, next_row): return False
            ob = self.obstacle_at(next_col, next_row)
            if ob and ob.blocks_movement: return False
            col, row = next_col, next_row
        player.col, player.row = col, row
        self.collect_if_item(player)
        return True

    def apply_start_of_turn_effects(self):
        """Drowning check: starting your turn on the same water tile as last turn."""
        cur = self.players[self.current_player_index]
        if cur.hp <= 0: return
        ob = self.obstacle_at(cur.col, cur.row)
        if isinstance(ob, Water):
            if cur.last_water_pos == (cur.col, cur.row):
                self.apply_damage(cur, 1)

    def end_of_turn_bookkeeping(self, finished_player: Player):
        ob = self.obstacle_at(finished_player.col, finished_player.row)
        finished_player.last_water_pos = (finished_player.col, finished_player.row) if isinstance(ob, Water) else None
        # clear any selected consumable
        finished_player.consumable_selected = None

    def advance_turn(self):
        finished = self.players[self.current_player_index]
        self.end_of_turn_bookkeeping(finished)
        for _ in range(len(self.players)):
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            if self.players[self.current_player_index].hp > 0:
                break
        self.apply_start_of_turn_effects()

    # -------------------------
    # Rendering
    # -------------------------
    def draw_button(self, rect: pygame.Rect, label: str):
        hover = rect.collidepoint(self.mouse_pos)
        bg = BUTTON_BG_HOVER if hover else BUTTON_BG
        pygame.draw.rect(self.screen, bg, rect, border_radius=10)
        pygame.draw.rect(self.screen, BUTTON_BORDER, rect, width=1, border_radius=10)
        txt = self.font.render(label, True, WHITE)
        self.screen.blit(txt, (rect.x + (rect.w - txt.get_width())//2, rect.y + (rect.h - txt.get_height())//2))

    def draw_grid_and_hud(self):
        self.screen.fill(BACKGROUND_COLOR)
        pygame.draw.rect(self.screen, HUD_BG, (0, 0, MAP_WIDTH_PX, HUD_HEIGHT))
        pygame.draw.rect(self.screen, SIDEBAR_BG, (MAP_WIDTH_PX, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT))

        # SAFE: if players aren't initialized yet (e.g., on the player-count screen),
        # don't index into self.players.
        if self.players and 0 <= self.current_player_index < len(self.players):
            turn_label = self.players[self.current_player_index].label  # GUI shows color label
        else:
            turn_label = "—"
        turn_txt = f"Turn: {turn_label}"
        self.screen.blit(self.font_big.render(turn_txt, True, WHITE), (16, 12))

        hud_help = "Left Click: Face  |  Arrows: Move  |  Right Click: Shoot/Throw  |  Q: Self-KO  |  R: Restart"
        self.screen.blit(self.font.render(hud_help, True, TEXT_MUTED), (16, 48))
        self.draw_button(self.button_restart, "Restart (R)")

        # grid
        for col in range(GRID_COLUMNS + 1):
            x = col * CELL_SIZE
            pygame.draw.line(self.screen, GRID_COLOR, (x, HUD_HEIGHT), (x, HUD_HEIGHT + MAP_HEIGHT_PX))
        for row in range(GRID_ROWS + 1):
            y = HUD_HEIGHT + row * CELL_SIZE
            pygame.draw.line(self.screen, GRID_COLOR, (0, y), (MAP_WIDTH_PX, y))

        # obstacles
        for ob in self.obstacles:
            x = ob.col * CELL_SIZE + CELL_MARGIN
            y = HUD_HEIGHT + ob.row * CELL_SIZE + CELL_MARGIN
            w = CELL_SIZE - 2 * CELL_MARGIN
            h = CELL_SIZE - 2 * CELL_MARGIN
            pygame.draw.rect(self.screen, ob.color, (x, y, w, h), border_radius=6)

        # items
        for it in self.items:
            x = it.col * CELL_SIZE + CELL_MARGIN
            y = HUD_HEIGHT + it.row * CELL_SIZE + CELL_MARGIN
            w = CELL_SIZE - 2 * CELL_MARGIN
            h = CELL_SIZE - 2 * CELL_MARGIN
            base = (185, 185, 185)
            pygame.draw.rect(self.screen, base, (x, y, w, h), border_radius=6)
            qm = self.font_big.render("?", True, (40, 40, 40))
            self.screen.blit(qm, (x + (w - qm.get_width())//2, y + (h - qm.get_height())//2))

    def draw_highlights(self):
        current = self.players[self.current_player_index]
        if current.hp <= 0:
            return
        overlay = pygame.Surface((MAP_WIDTH_PX, WINDOW_HEIGHT), pygame.SRCALPHA)

        # move tiles
        for dcol, drow in [(-1,0),(1,0),(0,-1),(0,1)]:
            col1, row1 = current.col + dcol, current.row + drow
            if in_bounds(col1, row1) and not self.is_occupied(col1, row1):
                if not (self.obstacle_at(col1, row1) and self.obstacle_at(col1, row1).blocks_movement):
                    pygame.draw.rect(overlay, MOVE_HIGHLIGHT,
                                     (col1*CELL_SIZE+CELL_MARGIN, HUD_HEIGHT + row1*CELL_SIZE+CELL_MARGIN,
                                      CELL_SIZE-2*CELL_MARGIN, CELL_SIZE-2*CELL_MARGIN), border_radius=4)
                    if current.has_agility_boots:
                        col2, row2 = col1 + dcol, row1 + drow
                        if in_bounds(col2, row2) and not self.is_occupied(col2, row2):
                            if not (self.obstacle_at(col2, row2) and self.obstacle_at(col2, row2).blocks_movement):
                                pygame.draw.rect(overlay, MOVE_HIGHLIGHT,
                                                 (col2*CELL_SIZE+CELL_MARGIN, HUD_HEIGHT + row2*CELL_SIZE+CELL_MARGIN,
                                                  CELL_SIZE-2*CELL_MARGIN, CELL_SIZE-2*CELL_MARGIN), border_radius=4)

        # deagle tiles
        for col, row in self.deagle_range_tiles(current):
            pygame.draw.rect(overlay, SHOOT_HIGHLIGHT,
                             (col*CELL_SIZE+CELL_MARGIN, HUD_HEIGHT + row*CELL_SIZE+CELL_MARGIN,
                              CELL_SIZE-2*CELL_MARGIN, CELL_SIZE-2*CELL_MARGIN), border_radius=4)

        # shotgun tiles
        for col, row in self.shotgun_fan_tiles(current):
            pygame.draw.rect(overlay, SHOOT_HIGHLIGHT,
                             (col*CELL_SIZE+CELL_MARGIN, HUD_HEIGHT + row*CELL_SIZE+CELL_MARGIN,
                              CELL_SIZE-2*CELL_MARGIN, CELL_SIZE-2*CELL_MARGIN), border_radius=8)

        # grenade area if selected
        for col, row in self.grenade_slab_tiles(current):
            pygame.draw.rect(overlay, SHOOT_HIGHLIGHT,
                             (col*CELL_SIZE+CELL_MARGIN, HUD_HEIGHT + row*CELL_SIZE+CELL_MARGIN,
                              CELL_SIZE-2*CELL_MARGIN, CELL_SIZE-2*CELL_MARGIN), border_radius=8)

        self.screen.blit(overlay, (0, 0))

    def draw_players(self):
        now = time.time()
        for i, player in enumerate(self.players):
            if player.hp <= 0:
                continue
            cx = player.col*CELL_SIZE + CELL_SIZE//2
            cy = HUD_HEIGHT + player.row*CELL_SIZE + CELL_SIZE//2
            radius = int(CELL_SIZE*0.32)

            if i == self.current_player_index and not self.game_over:
                glow = pygame.Surface((CELL_SIZE*2, CELL_SIZE*2), pygame.SRCALPHA)
                pygame.draw.circle(glow, (94,234,212,90), (CELL_SIZE, CELL_SIZE), int(radius*1.4))
                self.screen.blit(glow, (cx-CELL_SIZE, cy-CELL_SIZE), special_flags=pygame.BLEND_PREMULTIPLIED)

            tint = player.color
            if now < player.blink_until:
                phase = int((now*1000) // 120) % 2
                tint = player.light_color if phase == 0 else player.color

            pygame.draw.circle(self.screen, tint, (cx, cy), radius)
            pygame.draw.circle(self.screen, (255,255,255,50), (cx, cy), radius, width=2)

            # eyes
            eye_offset = int(radius*0.35)
            forward = int(radius*0.35)
            eye1x, eye1y = cx - eye_offset, cy
            eye2x, eye2y = cx + eye_offset, cy
            if player.facing == 'left':
                eye1x -= forward; eye2x -= forward
            elif player.facing == 'right':
                eye1x += forward; eye2x += forward
            elif player.facing == 'up':
                eye1y -= forward; eye2y -= forward
            elif player.facing == 'down':
                eye1y += forward; eye2y += forward
            eye_r = max(3, int(radius*0.12))
            pygame.draw.circle(self.screen, (255,255,255), (eye1x, eye1y), eye_r)
            pygame.draw.circle(self.screen, (255,255,255), (eye2x, eye2y), eye_r)
            pupil_shift = int(radius*0.08)
            p1x, p1y, p2x, p2y = eye1x, eye1y, eye2x, eye2y
            if player.facing == 'left':
                p1x -= pupil_shift; p2x -= pupil_shift
            elif player.facing == 'right':
                p1x += pupil_shift; p2x += pupil_shift
            elif player.facing == 'up':
                p1y -= pupil_shift; p2y -= pupil_shift
            elif player.facing == 'down':
                p1y += pupil_shift; p2y += pupil_shift
            pupil_r = max(2, int(radius*0.06))
            pygame.draw.circle(self.screen, BACKGROUND_COLOR, (p1x, p1y), pupil_r)
            pygame.draw.circle(self.screen, BACKGROUND_COLOR, (p2x, p2y), pupil_r)

    def draw_sidebar(self):
        self.screen.blit(self.font_big.render("Status", True, WHITE), (MAP_WIDTH_PX + 16, 12))
        self.sidebar_item_rects = []

        count = max(1, len(self.players))
        section_height = (WINDOW_HEIGHT - HUD_HEIGHT) // count
        top = HUD_HEIGHT
        for i, player in enumerate(self.players):
            y0 = top + i * section_height
            if i > 0:
                pygame.draw.line(self.screen, (28, 42, 58), (MAP_WIDTH_PX + 8, y0), (MAP_WIDTH_PX + SIDEBAR_WIDTH - 8, y0), 1)
            self.screen.blit(self.font.render(player.label, True, WHITE), (MAP_WIDTH_PX + 16, y0 + 12))
            # HP pips
            hp_x = MAP_WIDTH_PX + 16
            hp_y = y0 + 40
            for k in range(MAX_HP):
                color = HP_COLOR if k < player.hp else HP_EMPTY_COLOR
                pygame.draw.rect(self.screen, color, (hp_x + k*26, hp_y, 22, 12), border_radius=4)

            # Inventory
            inv_y_start = hp_y + 28
            self.screen.blit(self.font.render("Items:", True, TEXT_MUTED), (MAP_WIDTH_PX + 16, inv_y_start))

            items = self.player_inventory(player)
            line_height = 22
            item_text_x = MAP_WIDTH_PX + 90
            current_y = inv_y_start
            for key, display_name, description in items:
                current_y += line_height
                text_surface = self.font.render(display_name, True, WHITE)

                # selection highlight for grenade
                is_selected = (key == "Grenade" and player.consumable_selected == "Grenade")
                if is_selected:
                    highlight_rect = pygame.Rect(item_text_x - 6, current_y - text_surface.get_height() - 2,
                                                 SIDEBAR_WIDTH - (item_text_x - MAP_WIDTH_PX) - 16,
                                                 text_surface.get_height() + 6)
                    pygame.draw.rect(self.screen, (28, 42, 58), highlight_rect, border_radius=6)
                    pygame.draw.rect(self.screen, (40, 56, 76), highlight_rect, 1, border_radius=6)

                # clickable area
                item_rect = pygame.Rect(item_text_x, current_y - text_surface.get_height(),
                                        SIDEBAR_WIDTH - (item_text_x - MAP_WIDTH_PX) - 16,
                                        text_surface.get_height()+4)
                self.screen.blit(text_surface, (item_text_x, current_y - text_surface.get_height()))
                self.sidebar_item_rects.append((i, key, item_rect, description))

        # Tooltip on hover
        if self.sidebar_hover_item:
            _, _, rect, description = self.sidebar_hover_item
            if description:
                pad = 8
                max_w = SIDEBAR_WIDTH - 24
                wrapped = wrap_text(self.font_small, description, WHITE, max_w - pad*2)
                box_w = wrapped.get_width() + pad*2
                box_h = wrapped.get_height() + pad*2
                mx, my = self.mouse_pos
                box_x = min(max(mx + 12, MAP_WIDTH_PX + 8), MAP_WIDTH_PX + SIDEBAR_WIDTH - box_w - 8)
                box_y = min(max(my + 12, HUD_HEIGHT + 8), WINDOW_HEIGHT - box_h - 8)
                box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
                pygame.draw.rect(self.screen, (24, 36, 50), box_rect, border_radius=6)
                pygame.draw.rect(self.screen, (40, 56, 76), box_rect, 1, border_radius=6)
                self.screen.blit(wrapped, (box_rect.x + pad, box_rect.y + pad))

    def draw_start_overlay(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,160))
        self.screen.blit(overlay, (0,0))
        t1 = self.font_big.render("Choose number of players (2-4)", True, WHITE)
        t2 = self.font.render("Press 2, 3, or 4", True, WHITE)
        self.screen.blit(t1, (WINDOW_WIDTH//2 - t1.get_width()//2, WINDOW_HEIGHT//2 - 40))
        self.screen.blit(t2, (WINDOW_WIDTH//2 - t2.get_width()//2, WINDOW_HEIGHT//2 + 4))

    def draw_win_overlay(self):
        overlay = pygame.Surface((MAP_WIDTH_PX, MAP_HEIGHT_PX), pygame.SRCALPHA)
        overlay.fill((0,0,0,140))
        self.screen.blit(overlay, (0, HUD_HEIGHT))
        alive = [p for p in self.players if p.hp > 0]
        if len(alive) == 1:
            txt = self.font_big.render(f"{alive[0].label} wins!", True, WHITE)
        else:
            txt = self.font_big.render("Game Over!", True, WHITE)
        self.screen.blit(txt, (MAP_WIDTH_PX//2 - txt.get_width()//2, HUD_HEIGHT + MAP_HEIGHT_PX//2 - txt.get_height()//2))
        hint = self.font.render("Press R to Restart", True, WHITE)
        self.screen.blit(hint, (MAP_WIDTH_PX//2 - hint.get_width()//2, HUD_HEIGHT + MAP_HEIGHT_PX//2 + 20))

    # -------------------------
    # Input handling
    # -------------------------
    def grid_from_mouse(self, pos):
        x, y = pos
        if y < HUD_HEIGHT or x >= MAP_WIDTH_PX:
            return None
        col = x // CELL_SIZE
        row = (y - HUD_HEIGHT) // CELL_SIZE
        if in_bounds(col, row):
            return (col, row)
        return None

    def handle_sidebar_click(self, pos):
        # Toggle grenade selection only
        for (player_index, key, rect, _desc) in self.sidebar_item_rects:
            if rect.collidepoint(pos) and key == "Grenade" and player_index == self.current_player_index:
                player = self.players[player_index]
                if player.grenade_count <= 0:
                    player.consumable_selected = None
                    return True
                player.consumable_selected = None if player.consumable_selected == "Grenade" else "Grenade"
                return True
        return False

    def handle_left_click(self, pos):
        if self.button_restart.collidepoint(pos):
            self.awaiting_player_count = True
            return
        if pos[0] >= MAP_WIDTH_PX:
            self.handle_sidebar_click(pos)
            return
        if self.game_over or self.awaiting_player_count:
            return
        grid = self.grid_from_mouse(pos)
        if grid is None:
            return
        gx, gy = grid
        current = self.players[self.current_player_index]
        dx = gx - current.col
        dy = gy - current.row
        if dx == 0 and dy == 0:
            return
        current.facing = facing_from_delta(dx, dy)

    def handle_right_click(self, pos):
        if self.game_over or self.awaiting_player_count:
            return
        current = self.players[self.current_player_index]
        if current.hp <= 0:
            return

        grid = self.grid_from_mouse(pos)
        if grid is None:
            return

        # Grenade selected?
        if current.consumable_selected == "Grenade" and current.grenade_count > 0:
            slab = set(self.grenade_slab_tiles(current))
            if grid in slab:
                for idx in self.other_player_indices():
                    target = self.players[idx]
                    if (target.col, target.row) in slab:
                        self.apply_damage(target, 1)
                current.grenade_count -= 1
                current.consumable_selected = None if current.grenade_count <= 0 else "Grenade"
                self.advance_turn()
            return

        # Deagle?
        if current.has_deagle:
            line_tiles = self.deagle_range_tiles(current)
            if grid in line_tiles:
                # damage only the closest victim up to the clicked tile
                dcol, drow = DIRECTIONS[current.facing]
                # iterate from nearest to farthest
                check_col, check_row = current.col + dcol, current.row + drow
                while in_bounds(check_col, check_row):
                    if (check_col, check_row) == grid or (check_col, check_row) in line_tiles:
                        # is there a target here?
                        for idx in self.other_player_indices():
                            t = self.players[idx]
                            if (t.col, t.row) == (check_col, check_row):
                                self.apply_damage(t, 1)
                                self.advance_turn()
                                return
                        # continue marching until reach click or end-of-line
                        if (check_col, check_row) == grid:
                            break
                        check_col += dcol; check_row += drow
                    else:
                        break
                # no victim -> still end turn for firing
                self.advance_turn()
                return

        # Shotgun?
        if current.has_shotgun:
            fan = set(self.shotgun_fan_tiles(current))
            if grid in fan:
                # apply damage to all opponents that are within computed fan (already blocked by walls)
                hit_any = False
                for idx in self.other_player_indices():
                    t = self.players[idx]
                    if (t.col, t.row) in fan:
                        self.apply_damage(t, 1); hit_any = True
                self.advance_turn()
                return

    # -------------------------
    # Main Loop
    # -------------------------
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.MOUSEMOTION:
                    self.mouse_pos = event.pos
                    self.sidebar_hover_item = None
                    if self.mouse_pos[0] >= MAP_WIDTH_PX:
                        for (pi, key, rect, desc) in self.sidebar_item_rects:
                            if rect.collidepoint(self.mouse_pos):
                                self.sidebar_hover_item = (pi, key, rect, desc)
                                break

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_left_click(event.pos)
                    elif event.button == 3:
                        self.handle_right_click(event.pos)

                elif event.type == pygame.KEYDOWN:
                    if self.awaiting_player_count:
                        if event.key in (pygame.K_2, pygame.K_3, pygame.K_4):
                            n = {pygame.K_2:2, pygame.K_3:3, pygame.K_4:4}[event.key]
                            self.full_reset_with_player_count(n)
                        elif event.key == pygame.K_r:
                            self.awaiting_player_count = True
                        continue

                    if event.key == pygame.K_r:
                        self.awaiting_player_count = True
                        continue

                    # Self-KO
                    if event.key == pygame.K_q and not self.game_over:
                        current = self.players[self.current_player_index]
                        if current.hp > 0:
                            self.apply_damage(current, current.hp)
                            if not self.game_over:
                                self.advance_turn()
                        continue

                    if self.game_over:
                        continue

                    current = self.players[self.current_player_index]
                    if current.hp <= 0:
                        continue

                    modifiers = pygame.key.get_mods()
                    wants_two = bool(modifiers & pygame.KMOD_SHIFT) and current.has_agility_boots
                    step_len = 2 if wants_two else 1

                    moved = False
                    if event.key == pygame.K_LEFT:
                        current.facing = 'left'
                        moved = self.try_move_exact(current, -1, 0, step_len)
                    elif event.key == pygame.K_RIGHT:
                        current.facing = 'right'
                        moved = self.try_move_exact(current, 1, 0, step_len)
                    elif event.key == pygame.K_UP:
                        current.facing = 'up'
                        moved = self.try_move_exact(current, 0, -1, step_len)
                    elif event.key == pygame.K_DOWN:
                        current.facing = 'down'
                        moved = self.try_move_exact(current, 0, 1, step_len)

                    if moved:
                        self.advance_turn()

            # draw
            self.draw_grid_and_hud()
            if not self.awaiting_player_count:
                self.draw_highlights()
                self.draw_players()
                self.draw_sidebar()

            if self.awaiting_player_count:
                self.draw_start_overlay()
            elif self.game_over:
                self.draw_win_overlay()

            pygame.display.flip()

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()