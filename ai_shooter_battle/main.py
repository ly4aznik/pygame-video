import argparse
import math
import os
import random
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from window_recorder import WindowRecorder

import pygame


# ---------------------------
# Quick tuning constants
# ---------------------------
WIDTH, HEIGHT = 360, 640
WINDOW_TITLE = "AI Shooter Battle"
FPS = 60
CELL_SIZE = 14
GRID_COLS = 25
GRID_ROWS = 22
BOARD_LEFT = (WIDTH - GRID_COLS * CELL_SIZE) // 2
BOARD_TOP = 75
BOARD_WIDTH = GRID_COLS * CELL_SIZE
BOARD_HEIGHT = GRID_ROWS * CELL_SIZE
SCORE_TOP = BOARD_TOP + BOARD_HEIGHT + 11
MOVE_TICKS_PER_SECOND = 1.87
MEDKIT_COUNT = 5
MAX_HP = 100
MEDKIT_HEAL = 30
MATCH_TIME_LIMIT_SECONDS = 180
START_DELAY_SECONDS = 1.0
WINDOW_RECORD_FPS = 30
WINDOW_RECORD_CAPTURE_SIZE = (WIDTH, HEIGHT)
WINDOW_RECORD_OUTPUT_SIZE = (1080, 1920)
WINDOW_RECORD_END_DELAY_SECONDS = 1.0
WINDOW_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_recordings")
DEFAULT_MUSIC_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "music",
    "hot-pursuit-kevin-macleod.mp3",
)

BG = (246, 248, 242)
PANEL = (255, 255, 250)
GRID = (222, 228, 218)
WHITE = (42, 50, 62)
MUTED = (126, 137, 139)
DANGER = (210, 93, 96)
WALL = (190, 199, 188)
WALL_DARK = (151, 164, 153)
HEAL = (104, 166, 129)
TEAM_COLORS = {
    "BLUE": (92, 139, 184),
    "RED": (198, 104, 101),
}

Vec = Tuple[int, int]
Cell = Tuple[int, int]

DIRS: List[Vec] = [(1, 0), (-1, 0), (0, 1), (0, -1)]
SHOT_DIRS: List[Vec] = DIRS + [(1, 1), (1, -1), (-1, 1), (-1, -1)]


class StrategyKind(Enum):
    LOOTER = "Scout"
    MEDIC = "Medic"
    SNIPER = "Sniper"
    RUSHER = "Rush"
    COVER = "Cover"


class PickupKind(Enum):
    MEDKIT = "medkit"


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Tuple[int, int, int]
    life: float
    max_life: float
    radius: float

    def update(self, dt: float) -> None:
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.96
        self.vy *= 0.96

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0:
            return
        alpha = max(0, min(255, int(255 * self.life / self.max_life)))
        color = (*self.color, alpha)
        layer = pygame.Surface((int(self.radius * 4), int(self.radius * 4)), pygame.SRCALPHA)
        pygame.draw.circle(layer, color, (layer.get_width() // 2, layer.get_height() // 2), int(self.radius))
        surface.blit(layer, (self.x - layer.get_width() / 2, self.y - layer.get_height() / 2))


@dataclass(eq=False)
class Pickup:
    cell: Cell
    kind: PickupKind
    born_time: float = 0.0
    pulse: float = field(default_factory=lambda: random.random() * 10.0)

    def draw(self, surface: pygame.Surface, now: float) -> None:
        x, y = cell_center(self.cell)
        age = min(1.0, (now - self.born_time) * 4.0)
        pulse = 0.5 + 0.5 * math.sin(now * 5.0 + self.pulse)
        glow_radius = int((CELL_SIZE * 0.55 + CELL_SIZE * 0.18 * pulse) * age)
        glow_color = (104, 166, 129, 46)
        glow = pygame.Surface((glow_radius * 4, glow_radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(
            glow,
            glow_color,
            (glow.get_width() // 2, glow.get_height() // 2),
            glow_radius * 2,
        )
        surface.blit(glow, (x - glow.get_width() / 2, y - glow.get_height() / 2))

        rect_size = max(4, int(CELL_SIZE * 0.62 * age))
        rect = pygame.Rect(0, 0, rect_size, rect_size)
        rect.center = (x, y)
        pygame.draw.rect(surface, (236, 250, 236), rect, border_radius=3)
        pygame.draw.rect(surface, (104, 166, 129), rect, 1, border_radius=3)
        pygame.draw.line(surface, (104, 166, 129), (x - 3, y), (x + 3, y), 2)
        pygame.draw.line(surface, (104, 166, 129), (x, y - 3), (x, y + 3), 2)


@dataclass(eq=False)
class Fighter:
    name: str
    color: Tuple[int, int, int]
    strategy: StrategyKind
    team: str
    cell: Cell
    direction: Vec
    speed: float
    hp: int = MAX_HP
    score: int = 0
    kills: int = 0
    alive: bool = True
    energy: float = 0.0
    cooldown: float = 0.0
    trail: List[Tuple[float, float, float]] = field(default_factory=list)
    death_flash: float = 0.0
    cover_stand_ticks: int = 0
    rail_shots: int = 0

    def add_trail(self) -> None:
        x, y = cell_center(self.cell)
        self.trail.append((x, y, 0.32))
        if len(self.trail) > 12:
            self.trail.pop(0)

    def update_timers(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)
        next_trail = []
        for x, y, life in self.trail:
            life -= dt
            if life > 0:
                next_trail.append((x, y, life))
        self.trail = next_trail
        if self.death_flash > 0:
            self.death_flash -= dt

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        for x, y, life in self.trail:
            alpha = int(72 * life / 0.32)
            layer = pygame.Surface((CELL_SIZE * 2, CELL_SIZE * 2), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*self.color, alpha), (CELL_SIZE, CELL_SIZE), CELL_SIZE // 2)
            surface.blit(layer, (x - CELL_SIZE, y - CELL_SIZE))

        x, y = cell_center(self.cell)
        if not self.alive:
            body_color = tuple(max(45, int(c * 0.48)) for c in self.color)
        else:
            body_color = self.color
        light = tuple(min(255, c + 44) for c in body_color)

        feet_y = y + 5
        body_top = y - 2
        pygame.draw.line(surface, body_color, (x - 2, body_top + 4), (x - 5, feet_y), 2)
        pygame.draw.line(surface, body_color, (x + 2, body_top + 4), (x + 5, feet_y), 2)
        pygame.draw.line(surface, body_color, (x - 2, y + 1), (x - 6, y + 2), 2)
        pygame.draw.line(surface, body_color, (x + 2, y + 1), (x + 6, y + 2), 2)
        pygame.draw.rect(surface, body_color, pygame.Rect(x - 4, y - 2, 8, 9), border_radius=3)
        pygame.draw.circle(surface, light, (x, y - 6), 4)
        pygame.draw.circle(surface, (35, 45, 54), (x - 1, y - 7), 1)

        gun_end = (x + self.direction[0] * 8, y + self.direction[1] * 8)
        pygame.draw.line(surface, (68, 75, 80), (x, y), gun_end, 2)

        if self.alive:
            pygame.draw.circle(surface, TEAM_COLORS.get(self.team, self.color), (x, y), CELL_SIZE // 2 + 2, 1)
            health_w = 17
            health_rect = pygame.Rect(x - health_w // 2, y - 18, health_w, 4)
            pygame.draw.rect(surface, (215, 220, 210), health_rect, border_radius=2)
            fill = pygame.Rect(health_rect.left, health_rect.top, int(health_w * self.hp / MAX_HP), 4)
            health_color = (45, 190, 93) if self.hp > 40 else (232, 75, 78)
            pygame.draw.rect(surface, health_color, fill, border_radius=2)
            pygame.draw.rect(surface, (255, 255, 250), health_rect, 1, border_radius=2)
            label = font.render(self.name, True, WHITE)
            surface.blit(label, label.get_rect(center=(x, y + 16)))

        if self.death_flash > 0:
            radius = int(24 * self.death_flash)
            pygame.draw.circle(surface, (*DANGER, 90), (x, y), radius, 2)


@dataclass
class Bullet:
    x: float
    y: float
    direction: Vec
    owner: Fighter
    color: Tuple[int, int, int]
    damage: int
    speed: float = 210.0
    life: float = 1.8

    def update(self, dt: float) -> None:
        self.life -= dt
        length = math.hypot(self.direction[0], self.direction[1])
        self.x += self.direction[0] / length * self.speed * dt
        self.y += self.direction[1] / length * self.speed * dt

    def draw(self, surface: pygame.Surface) -> None:
        length = math.hypot(self.direction[0], self.direction[1])
        tail = (self.x - self.direction[0] / length * 7, self.y - self.direction[1] / length * 7)
        pygame.draw.line(surface, self.color, tail, (self.x, self.y), 4)
        pygame.draw.circle(surface, (255, 246, 204), (int(self.x), int(self.y)), 4)


@dataclass
class RailBeam:
    start: Tuple[int, int]
    end: Tuple[int, int]
    color: Tuple[int, int, int]
    life: float = 1.0
    max_life: float = 1.0

    def update(self, dt: float) -> None:
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0:
            return
        alpha = max(0, min(255, int(210 * self.life / self.max_life)))
        pulse = self.life / self.max_life
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        bright = tuple(min(255, c + 55) for c in self.color)
        pygame.draw.line(layer, (*bright, alpha), self.start, self.end, 6)
        pygame.draw.line(layer, (255, 255, 250, alpha), self.start, self.end, 2)
        start_radius = max(2, int(10 * pulse))
        end_radius = max(2, int(13 * pulse))
        pygame.draw.circle(layer, (*bright, min(255, alpha + 35)), self.start, start_radius)
        pygame.draw.circle(layer, (255, 255, 250, alpha), self.start, max(1, start_radius // 2))
        pygame.draw.circle(layer, (*bright, min(255, alpha + 35)), self.end, end_radius, 2)
        pygame.draw.circle(layer, (255, 255, 250, alpha), self.end, max(1, end_radius // 3))
        surface.blit(layer, (0, 0))


def cell_center(cell: Cell) -> Tuple[int, int]:
    return BOARD_LEFT + cell[0] * CELL_SIZE + CELL_SIZE // 2, BOARD_TOP + cell[1] * CELL_SIZE + CELL_SIZE // 2


def pixel_to_cell(x: float, y: float) -> Cell:
    return int((x - BOARD_LEFT) // CELL_SIZE), int((y - BOARD_TOP) // CELL_SIZE)


def add_vec(a: Cell, b: Vec) -> Cell:
    return a[0] + b[0], a[1] + b[1]


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Game:
    def __init__(
        self,
        record_window: bool = False,
        window_record_fps: int = WINDOW_RECORD_FPS,
        window_record_dir: str = WINDOW_RECORDINGS_DIR,
        music_path: str = "",
        music_volume: float = 0.25,
        time_limit: int = MATCH_TIME_LIMIT_SECONDS,
    ) -> None:
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.SysFont("arial", 8, bold=True)
        self.font_ui = pygame.font.SysFont("arial", 11, bold=True)
        self.font_title = pygame.font.SysFont("arial", 26, bold=True)
        self.font_subtitle = pygame.font.SysFont("arial", 13, bold=True)
        self.font_winner = pygame.font.SysFont("arial", 36, bold=True)
        self.fighters: List[Fighter] = []
        self.pickups: List[Pickup] = []
        self.bullets: List[Bullet] = []
        self.rail_beams: List[RailBeam] = []
        self.particles: List[Particle] = []
        self.walls: Set[Cell] = set()
        self.paused = False
        self.game_over = False
        self.start_screen = True
        self.start_timer = 0.0
        self.start_pressed_anim = 0.0
        self.winner: Optional[Fighter] = None
        self.winner_team = ""
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.max_match_seconds = max(1, time_limit)
        self.window_recorder = WindowRecorder(
            enabled=record_window,
            window_title=WINDOW_TITLE,
            output_root=window_record_dir,
            session_prefix="shooter_battle",
            video_filename="shooter_battle_window.mp4",
            music_filename="shooter_battle_window_music.mp4",
            fps=window_record_fps,
            capture_size=WINDOW_RECORD_CAPTURE_SIZE,
            output_size=WINDOW_RECORD_OUTPUT_SIZE,
            end_delay_seconds=WINDOW_RECORD_END_DELAY_SECONDS,
            music_path=music_path,
            music_volume=music_volume,
        )
        self.restart()

    def restart(self) -> None:
        self.window_recorder.new_match()
        self.fighters = []
        self.pickups = []
        self.bullets = []
        self.rail_beams = []
        self.particles = []
        self.walls = self.create_walls()
        self.game_over = False
        self.start_screen = True
        self.start_timer = 0.0
        self.start_pressed_anim = 0.0
        self.winner = None
        self.winner_team = ""
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.create_fighters()
        for _ in range(MEDKIT_COUNT):
            self.spawn_pickup(PickupKind.MEDKIT)

    def create_walls(self) -> Set[Cell]:
        # Low cover blocks movement and bullets, so fighters can visibly hide.
        groups = [
            [(4, 5), (5, 5)],
            [(19, 5), (20, 5)],
            [(12, 8), (12, 9)],
            [(8, 12), (9, 12)],
            [(15, 12), (16, 12)],
            [(4, 16), (5, 16)],
            [(19, 16), (20, 16)],
            [(1, 10), (2, 10)],
            [(22, 11), (23, 11)],
        ]
        return {cell for group in groups for cell in group}

    def create_fighters(self) -> None:
        configs = [
            ("BOB", TEAM_COLORS["BLUE"], StrategyKind.LOOTER, "BLUE", (5, 3), (0, 1), 1.08),
            ("NICK", TEAM_COLORS["BLUE"], StrategyKind.SNIPER, "BLUE", (12, 3), (0, 1), 1.0),
            ("MAX", TEAM_COLORS["BLUE"], StrategyKind.RUSHER, "BLUE", (19, 3), (0, 1), 1.32),
            ("TOM", TEAM_COLORS["RED"], StrategyKind.RUSHER, "RED", (5, 18), (0, -1), 1.32),
            ("SAM", TEAM_COLORS["RED"], StrategyKind.SNIPER, "RED", (12, 18), (0, -1), 1.0),
            ("LEO", TEAM_COLORS["RED"], StrategyKind.COVER, "RED", (19, 18), (0, -1), 1.02),
        ]
        for name, color, strategy, team, start, direction, speed in configs:
            self.fighters.append(Fighter(name, color, strategy, team, start, direction, speed))

    def in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell[0] < GRID_COLS and 0 <= cell[1] < GRID_ROWS

    def alive_cells(self, exclude: Optional[Fighter] = None) -> Dict[Cell, Fighter]:
        return {f.cell: f for f in self.fighters if f.alive and f is not exclude}

    def blocked_cells(self, exclude: Optional[Fighter] = None) -> Set[Cell]:
        return set(self.walls) | set(self.alive_cells(exclude).keys())

    def spawn_pickup(self, kind: PickupKind) -> None:
        occupied = self.blocked_cells()
        occupied.update(pickup.cell for pickup in self.pickups)
        free = [(x, y) for x in range(GRID_COLS) for y in range(GRID_ROWS) if (x, y) not in occupied]
        if not free:
            return
        self.pickups.append(Pickup(random.choice(free), kind, pygame.time.get_ticks() / 1000.0))

    def nearest_pickup(self, fighter: Fighter, kind: Optional[PickupKind] = None) -> Optional[Pickup]:
        pickups = [p for p in self.pickups if kind is None or p.kind == kind]
        if not pickups:
            return None
        return min(pickups, key=lambda p: manhattan(fighter.cell, p.cell))

    def nearest_enemy(self, fighter: Fighter) -> Optional[Fighter]:
        enemies = [f for f in self.fighters if f.alive and f.team != fighter.team]
        if not enemies:
            return None
        return min(enemies, key=lambda enemy: manhattan(fighter.cell, enemy.cell))

    def line_of_sight(self, a: Cell, b: Cell) -> bool:
        if a == b:
            return True
        delta_x = b[0] - a[0]
        delta_y = b[1] - a[1]
        if delta_x != 0 and delta_y != 0 and abs(delta_x) != abs(delta_y):
            return False
        if delta_x != 0 and delta_y == 0:
            pass
        elif delta_y != 0 and delta_x == 0:
            pass
        elif abs(delta_x) != abs(delta_y):
            return False
        dx = 0 if a[0] == b[0] else (1 if b[0] > a[0] else -1)
        dy = 0 if a[1] == b[1] else (1 if b[1] > a[1] else -1)
        current = add_vec(a, (dx, dy))
        while current != b:
            if current in self.walls:
                return False
            current = add_vec(current, (dx, dy))
        return True

    def direction_between(self, a: Cell, b: Cell) -> Optional[Vec]:
        if a[0] == b[0]:
            return (0, 1 if b[1] > a[1] else -1)
        if a[1] == b[1]:
            return (1 if b[0] > a[0] else -1, 0)
        if abs(b[0] - a[0]) == abs(b[1] - a[1]):
            return (1 if b[0] > a[0] else -1, 1 if b[1] > a[1] else -1)
        return None

    def visible_enemies(self, fighter: Fighter) -> List[Fighter]:
        enemies = [
            f
            for f in self.fighters
            if f.alive and f.team != fighter.team and self.line_of_sight(fighter.cell, f.cell)
        ]
        return sorted(enemies, key=lambda enemy: manhattan(fighter.cell, enemy.cell))

    def adjacent_wall_count(self, cell: Cell) -> int:
        return sum(1 for direction in DIRS if add_vec(cell, direction) in self.walls)

    def exposed_to_enemies(self, fighter: Fighter, cell: Cell) -> int:
        exposed = 0
        for enemy in self.fighters:
            if enemy.team == fighter.team or not enemy.alive:
                continue
            if self.line_of_sight(cell, enemy.cell):
                exposed += 1
        return exposed

    def bullet_danger(self, fighter: Fighter, cell: Cell) -> float:
        danger = 0.0
        cx, cy = cell_center(cell)
        for bullet in self.bullets:
            if bullet.owner.team == fighter.team:
                continue
            bullet_cell = pixel_to_cell(bullet.x, bullet.y)
            dx = cell[0] - bullet_cell[0]
            dy = cell[1] - bullet_cell[1]
            same_ray = (
                (bullet.direction[0] == 0 and dx == 0 and dy * bullet.direction[1] >= 0)
                or (bullet.direction[1] == 0 and dy == 0 and dx * bullet.direction[0] >= 0)
                or (
                    bullet.direction[0] != 0
                    and bullet.direction[1] != 0
                    and abs(dx) == abs(dy)
                    and dx * bullet.direction[0] >= 0
                    and dy * bullet.direction[1] >= 0
                )
            )
            ahead = same_ray
            if ahead and self.line_of_sight(bullet_cell, cell):
                danger += max(0.0, 5.0 - math.dist((bullet.x, bullet.y), (cx, cy)) / CELL_SIZE)
        return danger

    def danger_score_at(self, fighter: Fighter, cell: Cell) -> float:
        score = self.exposed_to_enemies(fighter, cell) * 4.0
        score += self.bullet_danger(fighter, cell) * 2.5
        for enemy in self.fighters:
            if enemy.team == fighter.team or not enemy.alive:
                continue
            distance = manhattan(cell, enemy.cell)
            if distance <= 2:
                score += 3.0 - distance
        if cell[0] <= 0 or cell[0] >= GRID_COLS - 1:
            score += 1.2
        if cell[1] <= 0 or cell[1] >= GRID_ROWS - 1:
            score += 1.2
        return score

    def move_options(self, fighter: Fighter, include_stay: bool = True) -> List[Optional[Vec]]:
        options: List[Optional[Vec]] = [None] if include_stay else []
        blocked = self.blocked_cells(exclude=fighter)
        for direction in DIRS:
            nxt = add_vec(fighter.cell, direction)
            if self.in_bounds(nxt) and nxt not in blocked:
                options.append(direction)
        return options

    def path_to_any(self, fighter: Fighter, targets: Set[Cell]) -> Optional[Vec]:
        if not targets:
            return None
        blocked = self.blocked_cells(exclude=fighter)
        seen = {fighter.cell}
        queue: List[Tuple[Cell, Vec]] = []
        first_steps = [d for d in DIRS if self.in_bounds(add_vec(fighter.cell, d)) and add_vec(fighter.cell, d) not in blocked]
        nearest_target = min(targets, key=lambda c: manhattan(fighter.cell, c))
        first_steps.sort(key=lambda d: manhattan(add_vec(fighter.cell, d), nearest_target))
        for direction in first_steps:
            nxt = add_vec(fighter.cell, direction)
            seen.add(nxt)
            queue.append((nxt, direction))
        index = 0
        while index < len(queue):
            cell, first = queue[index]
            index += 1
            if cell in targets:
                return first
            for direction in DIRS:
                nxt = add_vec(cell, direction)
                if not self.in_bounds(nxt) or nxt in blocked or nxt in seen:
                    continue
                seen.add(nxt)
                queue.append((nxt, first))
        return None

    def nearest_cover_cells(self, fighter: Fighter, prefer_hidden: bool) -> Set[Cell]:
        blocked = self.blocked_cells(exclude=fighter)
        cells: Set[Cell] = set()
        for x in range(GRID_COLS):
            for y in range(GRID_ROWS):
                cell = (x, y)
                if cell in blocked:
                    continue
                if self.adjacent_wall_count(cell) == 0:
                    continue
                if prefer_hidden and self.exposed_to_enemies(fighter, cell) > 0:
                    continue
                cells.add(cell)
        return cells

    def choose_move(self, fighter: Fighter) -> Optional[Vec]:
        if fighter.strategy == StrategyKind.LOOTER:
            return self.looter_move(fighter)
        if fighter.strategy == StrategyKind.MEDIC:
            return self.medic_move(fighter)
        if fighter.strategy == StrategyKind.SNIPER:
            return self.sniper_move(fighter)
        if fighter.strategy == StrategyKind.RUSHER:
            return self.rusher_move(fighter)
        return self.cover_move(fighter)

    def score_direction(self, fighter: Fighter, direction: Optional[Vec], target: Optional[Cell], cautious: float) -> float:
        cell = fighter.cell if direction is None else add_vec(fighter.cell, direction)
        distance = manhattan(cell, target) if target else 0
        danger = self.danger_score_at(fighter, cell) * cautious
        cover_penalty = self.adjacent_wall_count(cell) * 1.8
        forward_bonus = self.forward_pressure(fighter, cell) * 0.45
        jitter = random.random() * 0.6
        return distance + danger + cover_penalty - forward_bonus + jitter

    def forward_pressure(self, fighter: Fighter, cell: Cell) -> int:
        return cell[1] if fighter.team == "BLUE" else GRID_ROWS - 1 - cell[1]

    def seek_pickup(self, fighter: Fighter, kind: PickupKind, cautious: float = 1.0) -> Optional[Vec]:
        pickups = {p.cell for p in self.pickups if p.kind == kind}
        path = self.path_to_any(fighter, pickups)
        if path:
            return path
        target = self.nearest_pickup(fighter, kind)
        options = self.move_options(fighter)
        return min(options, key=lambda d: self.score_direction(fighter, d, target.cell if target else None, cautious))

    def looter_move(self, fighter: Fighter) -> Optional[Vec]:
        if fighter.hp < 30 and self.danger_score_at(fighter, fighter.cell) > 13 and random.random() < 0.18:
            cover = self.nearest_cover_cells(fighter, prefer_hidden=True)
            path = self.path_to_any(fighter, cover)
            if path:
                return path
        enemy = self.nearest_enemy(fighter)
        options = self.move_options(fighter, include_stay=False)
        if not enemy:
            return random.choice(options) if options else None

        def scout_score(direction: Optional[Vec]) -> float:
            cell = fighter.cell if direction is None else add_vec(fighter.cell, direction)
            lane_bonus = -3.0 if self.line_of_sight(cell, enemy.cell) else 0.0
            range_score = abs(manhattan(cell, enemy.cell) - 4)
            danger = self.danger_score_at(fighter, cell) * 0.55
            cover_penalty = self.adjacent_wall_count(cell) * 1.2
            forward_bonus = -self.forward_pressure(fighter, cell) * 0.5
            return range_score + lane_bonus + danger + cover_penalty + forward_bonus + random.random() * 0.45

        return min(options, key=scout_score) if options else None

    def medic_move(self, fighter: Fighter) -> Optional[Vec]:
        if fighter.hp < 45:
            medkit = self.seek_pickup(fighter, PickupKind.MEDKIT, cautious=1.7)
            if medkit is not None:
                return medkit
        if fighter.hp < 35 and self.danger_score_at(fighter, fighter.cell) > 14:
            cover = self.nearest_cover_cells(fighter, prefer_hidden=True)
            path = self.path_to_any(fighter, cover)
            if path:
                return path
        enemy = self.nearest_enemy(fighter)
        options = self.move_options(fighter, include_stay=False)
        if not enemy:
            return random.choice(options) if options else None
        return min(options, key=lambda d: self.score_direction(fighter, d, enemy.cell, cautious=0.65)) if options else None

    def sniper_move(self, fighter: Fighter) -> Optional[Vec]:
        visible = self.visible_enemies(fighter)
        if visible and fighter.cooldown <= 0.12 and manhattan(fighter.cell, visible[0].cell) >= 6:
            return None
        enemy = self.nearest_enemy(fighter)
        options = self.move_options(fighter, include_stay=False)
        if not enemy:
            return random.choice(options) if options else None
        if not options:
            return None

        def score(direction: Optional[Vec]) -> float:
            cell = fighter.cell if direction is None else add_vec(fighter.cell, direction)
            distance_to_enemy = manhattan(cell, enemy.cell)
            ideal_range = 10
            range_score = abs(distance_to_enemy - ideal_range) * 1.25
            too_close_penalty = max(0, 6 - distance_to_enemy) * 4.5
            too_far_penalty = max(0, distance_to_enemy - 13) * 1.8
            lane_bonus = -7.0 if self.line_of_sight(cell, enemy.cell) else 0.0
            danger = self.danger_score_at(fighter, cell) * 0.45
            flank_bonus = -0.9 if cell[0] != fighter.cell[0] else 0.0
            return range_score + too_close_penalty + too_far_penalty + lane_bonus + danger + flank_bonus + random.random() * 0.45

        return min(options, key=score)

    def rusher_move(self, fighter: Fighter) -> Optional[Vec]:
        if fighter.hp < 24:
            medkit = self.seek_pickup(fighter, PickupKind.MEDKIT, cautious=0.35)
            if medkit is not None:
                return medkit
        enemy = self.nearest_enemy(fighter)
        if not enemy:
            options = self.move_options(fighter, include_stay=False)
            return random.choice(options) if options else None

        visible = self.line_of_sight(fighter.cell, enemy.cell)
        if visible and fighter.cooldown <= 0.08 and manhattan(fighter.cell, enemy.cell) <= 7:
            return None

        blocked = self.blocked_cells(exclude=fighter)
        attack_cells = {
            add_vec(enemy.cell, direction)
            for direction in DIRS
            if self.in_bounds(add_vec(enemy.cell, direction)) and add_vec(enemy.cell, direction) not in blocked
        }
        path = self.path_to_any(fighter, attack_cells)
        if path:
            return path

        options = self.move_options(fighter, include_stay=False)
        if not options:
            return None

        def rush_score(direction: Optional[Vec]) -> float:
            cell = add_vec(fighter.cell, direction) if direction else fighter.cell
            line_bonus = -5.0 if self.line_of_sight(cell, enemy.cell) else 0.0
            close_pressure = manhattan(cell, enemy.cell) * 1.35
            cover_penalty = self.adjacent_wall_count(cell) * 0.35
            danger = self.danger_score_at(fighter, cell) * 0.22
            forward_bonus = -self.forward_pressure(fighter, cell) * 0.35
            return close_pressure + line_bonus + cover_penalty + danger + forward_bonus + random.random() * 0.25

        return min(options, key=rush_score)

    def forced_attack_move(self, fighter: Fighter) -> Optional[Vec]:
        enemy = self.nearest_enemy(fighter)
        options = self.move_options(fighter, include_stay=False)
        if not enemy or not options:
            return random.choice(options) if options else None

        def attack_score(direction: Optional[Vec]) -> float:
            cell = add_vec(fighter.cell, direction) if direction else fighter.cell
            distance = manhattan(cell, enemy.cell) * 1.25
            line_bonus = -6.0 if self.line_of_sight(cell, enemy.cell) else 0.0
            forward_bonus = -self.forward_pressure(fighter, cell) * 0.55
            cover_penalty = self.adjacent_wall_count(cell) * 1.1
            danger = self.danger_score_at(fighter, cell) * 0.18
            return distance + line_bonus + forward_bonus + cover_penalty + danger + random.random() * 0.2

        return min(options, key=attack_score)

    def cover_move(self, fighter: Fighter) -> Optional[Vec]:
        visible = self.visible_enemies(fighter)
        if visible and fighter.cooldown <= 0.1 and manhattan(fighter.cell, visible[0].cell) <= 8:
            return None
        cover = self.nearest_cover_cells(fighter, prefer_hidden=True)
        path = self.path_to_any(fighter, cover)
        if fighter.hp < 32 and path and self.danger_score_at(fighter, fighter.cell) > 14:
            return path
        if fighter.hp < 42 and self.nearest_pickup(fighter, PickupKind.MEDKIT):
            return self.seek_pickup(fighter, PickupKind.MEDKIT, cautious=1.1)
        enemy = self.nearest_enemy(fighter)
        options = self.move_options(fighter, include_stay=False)
        if not enemy:
            return random.choice(options) if options else None
        return min(options, key=lambda d: self.score_direction(fighter, d, enemy.cell, cautious=0.75)) if options else None

    def choose_shot_target(self, fighter: Fighter) -> Optional[Fighter]:
        visible = self.visible_enemies(fighter)
        if not visible:
            return None
        if fighter.strategy == StrategyKind.SNIPER:
            return min(visible, key=lambda enemy: (enemy.hp, abs(manhattan(fighter.cell, enemy.cell) - 7)))
        if fighter.strategy == StrategyKind.RUSHER:
            return min(visible, key=lambda enemy: (enemy.hp, manhattan(fighter.cell, enemy.cell)))
        if fighter.strategy == StrategyKind.MEDIC and fighter.hp < 45:
            return None if random.random() < 0.35 else visible[0]
        if fighter.strategy == StrategyKind.COVER:
            covered = [enemy for enemy in visible if self.adjacent_wall_count(fighter.cell) > 0]
            return covered[0] if covered else visible[0]
        return min(visible, key=lambda enemy: (manhattan(fighter.cell, enemy.cell), enemy.hp))

    def shot_cooldown_for(self, fighter: Fighter) -> float:
        if fighter.strategy == StrategyKind.RUSHER:
            return 0.42
        if fighter.strategy == StrategyKind.SNIPER:
            return 3.06
        if fighter.strategy == StrategyKind.MEDIC:
            return 0.95
        if fighter.strategy == StrategyKind.COVER:
            return 0.78
        return 0.82

    def shot_damage_for(self, fighter: Fighter) -> int:
        if fighter.strategy == StrategyKind.SNIPER:
            return 8
        if fighter.strategy == StrategyKind.RUSHER:
            return 6
        return 7

    def railgun_trace(self, shooter: Fighter, direction: Vec) -> Tuple[Cell, List[Fighter]]:
        current = shooter.cell
        hit_targets: List[Fighter] = []
        fighters_by_cell = self.alive_cells(exclude=shooter)
        last_cell = shooter.cell
        while True:
            current = add_vec(current, direction)
            if not self.in_bounds(current):
                break
            if current in self.walls:
                break
            last_cell = current
            hit = fighters_by_cell.get(current)
            if hit and hit.team != shooter.team:
                hit_targets.append(hit)
        return last_cell, hit_targets

    def railgun_trace_from(self, origin: Cell, direction: Vec, shooter: Fighter) -> Tuple[Cell, List[Fighter]]:
        current = origin
        hit_targets: List[Fighter] = []
        fighters_by_cell = self.alive_cells(exclude=shooter)
        last_cell = origin
        while True:
            current = add_vec(current, direction)
            if not self.in_bounds(current):
                break
            if current in self.walls:
                break
            last_cell = current
            hit = fighters_by_cell.get(current)
            if hit and hit.team != shooter.team:
                hit_targets.append(hit)
        return last_cell, hit_targets

    def miss_rail_origin(self, shooter: Fighter, direction: Vec) -> Cell:
        offsets = [(-direction[1], direction[0]), (direction[1], -direction[0])]
        random.shuffle(offsets)
        blocked = self.blocked_cells(exclude=shooter)
        for offset in offsets:
            origin = add_vec(shooter.cell, offset)
            if self.in_bounds(origin) and origin not in blocked:
                return origin
        return shooter.cell

    def try_shoot(self, fighter: Fighter) -> None:
        if fighter.cooldown > 0 or not fighter.alive:
            return
        target = self.choose_shot_target(fighter)
        if not target:
            return
        direction = self.direction_between(fighter.cell, target.cell)
        if direction is None:
            return
        fighter.direction = direction
        x, y = cell_center(fighter.cell)
        if fighter.strategy == StrategyKind.SNIPER:
            fighter.rail_shots += 1
            misses = fighter.rail_shots % 4 == 0
            if misses:
                origin = self.miss_rail_origin(fighter, direction)
                end_cell, _ = self.railgun_trace(fighter, direction) if origin == fighter.cell else self.railgun_trace_from(origin, direction, fighter)
                self.rail_beams.append(RailBeam((x, y), cell_center(end_cell), fighter.color))
            else:
                end_cell, targets = self.railgun_trace(fighter, direction)
                self.rail_beams.append(RailBeam((x, y), cell_center(end_cell), fighter.color))
                for rail_target in targets:
                    self.damage_fighter(rail_target, fighter, self.shot_damage_for(fighter))
            fighter.cooldown = self.shot_cooldown_for(fighter)
            return
        self.bullets.append(
            Bullet(
                x + direction[0] * CELL_SIZE * 0.45,
                y + direction[1] * CELL_SIZE * 0.45,
                direction,
                fighter,
                fighter.color,
                self.shot_damage_for(fighter),
            )
        )
        fighter.cooldown = self.shot_cooldown_for(fighter)

    def move_fighter(self, fighter: Fighter) -> None:
        direction = self.choose_move(fighter)
        if direction is None:
            if self.adjacent_wall_count(fighter.cell) > 0:
                fighter.cover_stand_ticks += 1
                if fighter.cover_stand_ticks >= 3:
                    direction = self.forced_attack_move(fighter)
            else:
                fighter.cover_stand_ticks = 0
            if direction is None:
                return
        nxt = add_vec(fighter.cell, direction)
        if not self.in_bounds(nxt) or nxt in self.blocked_cells(exclude=fighter):
            if self.adjacent_wall_count(fighter.cell) > 0:
                fighter.cover_stand_ticks += 1
            else:
                fighter.cover_stand_ticks = 0
            return
        fighter.add_trail()
        fighter.cell = nxt
        fighter.direction = direction
        fighter.cover_stand_ticks = 0
        self.collect_pickups(fighter)

    def collect_pickups(self, fighter: Fighter) -> None:
        eaten: List[Pickup] = []
        for pickup in self.pickups:
            if pickup.cell != fighter.cell:
                continue
            eaten.append(pickup)
            before = fighter.hp
            fighter.hp = min(MAX_HP, fighter.hp + MEDKIT_HEAL)
            fighter.score += 3 + (fighter.hp - before) // 6
            self.emit_pickup_particles(pickup.cell, HEAL)
        if eaten:
            eaten_set = set(eaten)
            self.pickups = [pickup for pickup in self.pickups if pickup not in eaten_set]

    def update_bullets(self, dt: float) -> None:
        next_bullets: List[Bullet] = []
        fighters_by_cell = self.alive_cells()
        for bullet in self.bullets:
            bullet.update(dt)
            bullet_cell = pixel_to_cell(bullet.x, bullet.y)
            if bullet.life <= 0 or not self.in_bounds(bullet_cell):
                continue
            if bullet_cell in self.walls:
                self.emit_wall_particles(bullet_cell)
                continue
            hit = fighters_by_cell.get(bullet_cell)
            if hit and hit.team != bullet.owner.team:
                self.damage_fighter(hit, bullet.owner, bullet.damage)
                continue
            next_bullets.append(bullet)
        self.bullets = next_bullets

    def damage_fighter(self, fighter: Fighter, attacker: Fighter, damage: int) -> None:
        if not fighter.alive:
            return
        fighter.hp = max(0, fighter.hp - damage)
        attacker.score += 4
        self.emit_hit_particles(fighter.cell, attacker.color)
        if fighter.hp <= 0:
            self.kill_fighter(fighter, attacker)

    def kill_fighter(self, fighter: Fighter, attacker: Optional[Fighter] = None) -> None:
        if not fighter.alive:
            return
        fighter.alive = False
        fighter.death_flash = 1.0
        if attacker and attacker is not fighter:
            attacker.kills += 1
            attacker.score += 30
        self.emit_death_particles(fighter.cell, fighter.color)

    def emit_pickup_particles(self, cell: Cell, color: Tuple[int, int, int]) -> None:
        x, y = cell_center(cell)
        for _ in range(16):
            angle = random.random() * math.tau
            speed = random.uniform(35, 100)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.55, 0.55, 2))

    def emit_hit_particles(self, cell: Cell, color: Tuple[int, int, int]) -> None:
        x, y = cell_center(cell)
        for _ in range(8):
            angle = random.random() * math.tau
            speed = random.uniform(45, 120)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.45, 0.45, 2))

    def emit_wall_particles(self, cell: Cell) -> None:
        x, y = cell_center(cell)
        for _ in range(4):
            angle = random.random() * math.tau
            speed = random.uniform(18, 55)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, WALL_DARK, 0.35, 0.35, 2))

    def emit_death_particles(self, cell: Cell, color: Tuple[int, int, int]) -> None:
        x, y = cell_center(cell)
        for _ in range(26):
            angle = random.random() * math.tau
            speed = random.uniform(40, 140)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.78, 0.78, 3))

    def update(self, dt: float) -> None:
        self.window_recorder.monitor()
        if self.paused:
            return

        if self.start_screen:
            self.start_timer += dt
            if self.start_timer >= START_DELAY_SECONDS - 0.28:
                self.start_pressed_anim = min(1.0, self.start_pressed_anim + dt * 5.0)
            if self.start_timer >= START_DELAY_SECONDS:
                self.start_screen = False
                self.start_timer = 0.0
                self.start_pressed_anim = 0.0
            return

        for fighter in self.fighters:
            fighter.update_timers(dt)
        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        for beam in self.rail_beams:
            beam.update(dt)
        self.rail_beams = [beam for beam in self.rail_beams if beam.life > 0]
        self.update_bullets(dt)

        if self.game_over:
            self.end_timer += dt
            self.window_recorder.stop_after_game_over(self.end_timer)
            return

        self.match_time += dt
        if self.match_time >= self.max_match_seconds:
            self.finish_match_by_time_limit()
            return

        movers: List[Fighter] = []
        for fighter in self.fighters:
            if not fighter.alive:
                continue
            self.try_shoot(fighter)
            fighter.energy += fighter.speed * MOVE_TICKS_PER_SECOND * dt
            if fighter.energy >= 1:
                fighter.energy -= 1
                movers.append(fighter)

        random.shuffle(movers)
        for fighter in movers:
            if fighter.alive:
                self.move_fighter(fighter)
                self.try_shoot(fighter)

        while len([p for p in self.pickups if p.kind == PickupKind.MEDKIT]) < MEDKIT_COUNT:
            self.spawn_pickup(PickupKind.MEDKIT)
        self.check_game_over()

    def check_game_over(self) -> None:
        alive = [fighter for fighter in self.fighters if fighter.alive]
        alive_teams = sorted({fighter.team for fighter in alive})
        if len(alive_teams) == 1 and alive:
            self.winner_team = alive_teams[0]
            self.winner = max(alive, key=lambda f: (f.score, f.kills, f.hp))
            self.finish_reason = "TEAM WIN"
            self.game_over = True
        elif not alive:
            self.winner = max(self.fighters, key=lambda f: (f.score, f.kills, f.hp))
            self.winner_team = self.best_team()
            self.finish_reason = "BEST SCORE"
            self.game_over = True

    def finish_match_by_time_limit(self) -> None:
        if self.game_over:
            return
        self.winner_team = self.best_team()
        team_fighters = [fighter for fighter in self.fighters if fighter.team == self.winner_team]
        self.winner = max(team_fighters, key=lambda f: (f.score, f.kills, f.hp, int(f.alive)))
        self.finish_reason = "TIME LIMIT"
        self.game_over = True
        self.end_timer = 0.0

    def team_score(self, team: str) -> int:
        return sum(fighter.score for fighter in self.fighters if fighter.team == team)

    def team_hp(self, team: str) -> int:
        return sum(max(0, fighter.hp) for fighter in self.fighters if fighter.team == team and fighter.alive)

    def strategy_label(self, strategy: StrategyKind) -> str:
        labels = {
            StrategyKind.LOOTER: "Seeks firing lanes",
            StrategyKind.MEDIC: "Heals under fire",
            StrategyKind.SNIPER: "Holds long angles",
            StrategyKind.RUSHER: "Charges front line",
            StrategyKind.COVER: "Uses hard cover",
        }
        return labels[strategy]

    def best_team(self) -> str:
        teams = sorted({fighter.team for fighter in self.fighters})
        return max(
            teams,
            key=lambda team: (
                self.team_score(team),
                sum(1 for fighter in self.fighters if fighter.team == team and fighter.alive),
                self.team_hp(team),
            ),
        )

    def draw(self) -> None:
        now = pygame.time.get_ticks() / 1000.0
        self.screen.fill(BG)
        self.draw_header()
        self.draw_board()
        self.draw_walls()
        for pickup in self.pickups:
            pickup.draw(self.screen, now)
        for bullet in self.bullets:
            bullet.draw(self.screen)
        for beam in self.rail_beams:
            beam.draw(self.screen)
        for fighter in self.fighters:
            fighter.draw(self.screen, self.font_small)
        for particle in self.particles:
            particle.draw(self.screen)
        self.draw_scoreboard()
        if self.start_screen:
            self.draw_start_screen()
        if self.game_over and self.winner:
            self.draw_winner_screen()
        if self.paused:
            self.draw_pause()
        pygame.display.flip()
        self.window_recorder.start_if_pending()

    def draw_header(self) -> None:
        title = self.font_title.render("SHOOTER BATTLE", True, WHITE)
        subtitle = self.font_subtitle.render("Which team survives?", True, (94, 125, 145))
        remaining = max(0, int(self.max_match_seconds - self.match_time))
        timer = self.font_small.render(f"{remaining // 60:02d}:{remaining % 60:02d}", True, MUTED)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 24)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 50)))
        self.screen.blit(timer, timer.get_rect(center=(WIDTH // 2, 66)))

    def draw_start_screen(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((246, 248, 242, 188))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(35, 184, WIDTH - 70, 250)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=4)
        pygame.draw.rect(self.screen, (207, 216, 207), panel, 1, border_radius=4)

        title = self.font_title.render("SHOOTER BATTLE", True, WHITE)
        subtitle = self.font_subtitle.render("Which team survives?", True, (94, 125, 145))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 225)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 252)))

        remaining = max(0.0, START_DELAY_SECONDS - self.start_timer)
        countdown = self.font_winner.render(str(max(1, math.ceil(remaining))), True, MUTED)
        self.screen.blit(countdown, countdown.get_rect(center=(WIDTH // 2, 292)))

        colors = [(221, 177, 76), (104, 166, 129), (92, 139, 184), (198, 104, 101), (150, 124, 180)]
        track = pygame.Rect(88, 312, 184, 8)
        pygame.draw.line(self.screen, (222, 228, 218), (track.left, track.centery), (track.right, track.centery), 2)
        for index, color in enumerate(colors):
            phase = (self.start_timer * 190 + index * 35) % track.width
            dot_x = track.left + phase
            dot_y = track.centery + math.sin(self.start_timer * 8 + index) * 3
            pygame.draw.circle(self.screen, color, (int(dot_x), int(dot_y)), 4)

        press = 1.0 - 0.08 * self.start_pressed_anim
        button_w = int(184 * press)
        button_h = int(54 * press)
        button = pygame.Rect(0, 0, button_w, button_h)
        button.center = (WIDTH // 2, 352)
        button_color = (92, 139, 184) if self.start_pressed_anim < 0.75 else (80, 145, 103)
        shadow = button.move(0, 3 if self.start_pressed_anim < 0.75 else 1)
        pygame.draw.rect(self.screen, (205, 214, 204), shadow, border_radius=5)
        pygame.draw.rect(self.screen, button_color, button, border_radius=5)
        pygame.draw.rect(self.screen, tuple(min(255, c + 34) for c in button_color), button, 1, border_radius=5)
        label = self.font_title.render("START", True, PANEL)
        self.screen.blit(label, label.get_rect(center=button.center))

        hint_text = "auto start in 1 sec" if self.start_pressed_anim < 0.65 else "starting"
        hint = self.font_ui.render(hint_text, True, MUTED)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 395)))

    def draw_board(self) -> None:
        board_rect = pygame.Rect(BOARD_LEFT - 3, BOARD_TOP - 3, BOARD_WIDTH + 6, BOARD_HEIGHT + 6)
        pygame.draw.rect(self.screen, (253, 254, 249), board_rect, border_radius=6)
        pygame.draw.rect(self.screen, (205, 214, 204), board_rect, 1, border_radius=6)
        for x in range(GRID_COLS + 1):
            sx = BOARD_LEFT + x * CELL_SIZE
            pygame.draw.line(self.screen, GRID, (sx, BOARD_TOP), (sx, BOARD_TOP + BOARD_HEIGHT), 1)
        for y in range(GRID_ROWS + 1):
            sy = BOARD_TOP + y * CELL_SIZE
            pygame.draw.line(self.screen, GRID, (BOARD_LEFT, sy), (BOARD_LEFT + BOARD_WIDTH, sy), 1)

    def draw_walls(self) -> None:
        for cell in sorted(self.walls):
            x, y = cell_center(cell)
            rect = pygame.Rect(x - CELL_SIZE // 2 + 2, y - CELL_SIZE // 2 + 2, CELL_SIZE - 4, CELL_SIZE - 4)
            pygame.draw.rect(self.screen, WALL, rect, border_radius=3)
            pygame.draw.rect(self.screen, WALL_DARK, rect, 1, border_radius=3)
            pygame.draw.line(self.screen, (223, 229, 220), (rect.left + 2, rect.top + 2), (rect.right - 3, rect.top + 2), 1)

    def draw_scoreboard(self) -> None:
        rect = pygame.Rect(12, SCORE_TOP, WIDTH - 24, HEIGHT - SCORE_TOP - 12)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=4)
        pygame.draw.rect(self.screen, (207, 216, 207), rect, 1, border_radius=4)
        headers = ["BOT", "TEAM", "SCORE", "HP", "STATUS"]
        xs = [22, 177, 209, 252, 285]
        for header, x in zip(headers, xs):
            self.screen.blit(self.font_small.render(header, True, MUTED), (x, SCORE_TOP + 8))
        for index, fighter in enumerate(self.fighters):
            y = SCORE_TOP + 22 + index * 22
            team_color = TEAM_COLORS.get(fighter.team, fighter.color)
            pygame.draw.circle(self.screen, team_color, (24, y + 5), 4)
            pygame.draw.circle(self.screen, fighter.color, (24, y + 5), 2)
            self.screen.blit(self.font_ui.render(fighter.name, True, team_color), (33, y - 1))
            self.screen.blit(self.font_ui.render(self.strategy_label(fighter.strategy), True, WHITE), (33, y + 10))
            hp_text = str(max(0, fighter.hp))
            texts = [
                (fighter.team[0], 182, team_color),
                (str(fighter.score), 214, WHITE),
                (hp_text, 256, WHITE),
                ("alive" if fighter.alive else "dead", 285, (80, 145, 103) if fighter.alive else DANGER),
            ]
            for text, x, color in texts:
                self.screen.blit(self.font_ui.render(text, True, color), (x, y))

    def draw_winner_screen(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((246, 248, 242, 205))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(35, 205, WIDTH - 70, 210)
        team_color = TEAM_COLORS.get(self.winner_team, self.winner.color)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=4)
        pygame.draw.rect(self.screen, team_color, panel, 2, border_radius=4)
        winner_text = self.font_winner.render("WINNER", True, team_color)
        name_text = self.font_title.render(f"{self.winner_team} TEAM", True, WHITE)
        strat_text = self.font_subtitle.render(f"MVP {self.winner.name}  {self.strategy_label(self.winner.strategy)}", True, (94, 125, 145))
        score_text = self.font_subtitle.render(f"Team score {self.team_score(self.winner_team)}", True, WHITE)
        reason_text = self.font_small.render(self.finish_reason, True, MUTED)
        restart_text = self.font_ui.render("Press R for new match", True, MUTED)
        for surf, y in [(winner_text, 242), (name_text, 288), (strat_text, 325), (score_text, 352), (reason_text, 372), (restart_text, 390)]:
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))

    def draw_pause(self) -> None:
        label = self.font_title.render("PAUSED", True, WHITE)
        self.screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    def save_screenshot(self) -> None:
        pygame.image.save(self.screen, f"shooter_screenshot_{pygame.time.get_ticks()}.png")

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    self.restart()
                elif event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_s:
                    self.save_screenshot()
        return True

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            running = self.handle_events()
            self.update(dt)
            self.draw()
        self.window_recorder.stop()
        pygame.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Shooter Battle pygame simulation")
    parser.add_argument(
        "--record-window",
        action="store_true",
        help="record the pygame window with external ffmpeg and stop when the match ends",
    )
    parser.add_argument(
        "--record-fps",
        type=int,
        default=WINDOW_RECORD_FPS,
        help=f"external window recording FPS, default {WINDOW_RECORD_FPS}",
    )
    parser.add_argument(
        "--record-dir",
        default=WINDOW_RECORDINGS_DIR,
        help="folder for external window recordings",
    )
    parser.add_argument(
        "--music",
        default=DEFAULT_MUSIC_PATH,
        help="path to a local stock music file to add after the match recording finishes",
    )
    parser.add_argument(
        "--music-volume",
        type=float,
        default=0.25,
        help="background music volume from 0.0 to 1.0, default 0.25",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=MATCH_TIME_LIMIT_SECONDS,
        help=f"match time limit in seconds, default {MATCH_TIME_LIMIT_SECONDS}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    Game(
        record_window=args.record_window,
        window_record_fps=args.record_fps,
        window_record_dir=args.record_dir,
        music_path=args.music,
        music_volume=args.music_volume,
        time_limit=args.time_limit,
    ).run()
