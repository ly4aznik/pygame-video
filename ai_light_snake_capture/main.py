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
WINDOW_TITLE = "AI Light Snake Capture"
FPS = 60
CELL_SIZE = 10
GRID_COLS = 34
GRID_ROWS = 29
BOARD_LEFT = (WIDTH - GRID_COLS * CELL_SIZE) // 2
BOARD_TOP = 75
BOARD_WIDTH = GRID_COLS * CELL_SIZE
BOARD_HEIGHT = GRID_ROWS * CELL_SIZE
SCORE_TOP = BOARD_TOP + BOARD_HEIGHT + 11
MOVE_TICKS_PER_SECOND = 2.7625
MATCH_TIME_LIMIT_SECONDS = 180
WINDOW_RECORD_FPS = 30
WINDOW_RECORD_CAPTURE_SIZE = (WIDTH, HEIGHT)
WINDOW_RECORD_OUTPUT_SIZE = (1080, 1920)
WINDOW_RECORD_END_DELAY_SECONDS = 1.0
WINDOW_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_recordings")
SAFE_HOME_MOVE_LIMIT = 6

BG = (246, 248, 242)
PANEL = (255, 255, 250)
GRID = (222, 228, 218)
WHITE = (42, 50, 62)
MUTED = (126, 137, 139)
DANGER = (210, 93, 96)
SAFE = (80, 145, 103)
NEUTRAL_CELL = (250, 251, 246)

YELLOW = (221, 177, 76)
GREEN = (104, 166, 129)
CORAL = (198, 104, 101)
BLUE = (92, 139, 184)
PURPLE = (150, 124, 180)
TEAL = (86, 159, 164)

Vec = Tuple[int, int]
Cell = Tuple[int, int]
Color = Tuple[int, int, int]

DIRS: List[Vec] = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def regular_hex_points(pad: int = 1) -> List[Tuple[int, int]]:
    center_x = BOARD_LEFT + BOARD_WIDTH / 2
    center_y = BOARD_TOP + BOARD_HEIGHT / 2
    side = min((BOARD_WIDTH - pad * 2) / 2, (BOARD_HEIGHT - pad * 2) / math.sqrt(3))
    points = []
    for index in range(6):
        angle = math.radians(index * 60)
        points.append((int(round(center_x + math.cos(angle) * side)), int(round(center_y + math.sin(angle) * side))))
    return points


def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[int, int]]) -> bool:
    px, py = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > py) != (y2 > py):
            cross_x = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < cross_x:
                inside = not inside
        previous = current
    return inside


def playable_cells() -> List[Cell]:
    polygon = regular_hex_points()
    cells: List[Cell] = []
    for y in range(GRID_ROWS):
        for x in range(GRID_COLS):
            center = (
                BOARD_LEFT + x * CELL_SIZE + CELL_SIZE / 2,
                BOARD_TOP + y * CELL_SIZE + CELL_SIZE / 2,
            )
            if point_in_polygon(center, polygon):
                cells.append((x, y))
    return cells


ALL_CELLS: List[Cell] = playable_cells()
PLAYABLE_CELLS: Set[Cell] = set(ALL_CELLS)


class StrategyKind(Enum):
    BUILDER = "Build safe loops"
    RAIDER = "Chase open trails"
    GUARDIAN = "Guard home edge"
    SPRINTER = "Fast wide loops"
    THIEF = "Steal border gaps"
    SCOUT = "Scout fresh space"


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Color
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
        layer = pygame.Surface((int(self.radius * 4), int(self.radius * 4)), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*self.color, alpha), (layer.get_width() // 2, layer.get_height() // 2), int(self.radius))
        surface.blit(layer, (self.x - layer.get_width() / 2, self.y - layer.get_height() / 2))


@dataclass(eq=False)
class LightSnake:
    name: str
    color: Color
    strategy: StrategyKind
    head: Cell
    direction: Vec
    speed: float
    territory: Set[Cell]
    alive: bool = True
    energy: float = 0.0
    trail: List[Cell] = field(default_factory=list)
    motion_trail: List[Tuple[float, float, float]] = field(default_factory=list)
    opening_steps: List[Vec] = field(default_factory=list)
    safe_moves: int = 0
    cuts: int = 0
    captures: int = 0
    best_capture: int = 0
    final_cells: int = 0
    last_gain: int = 0
    death_reason: str = ""
    death_flash: float = 0.0

    @property
    def protected(self) -> bool:
        return self.alive and not self.trail and self.head in self.territory

    @property
    def score(self) -> int:
        owned = len(self.territory) if self.alive else max(self.final_cells, len(self.territory))
        return owned + self.cuts * 35 + self.captures * 6 + self.best_capture

    @property
    def owned_cells(self) -> int:
        return len(self.territory) if self.alive else max(self.final_cells, len(self.territory))

    def status(self) -> str:
        if not self.alive:
            return "dead"
        if self.trail:
            return "trail"
        return "safe"

    def add_motion_trail(self) -> None:
        x, y = cell_center(self.head)
        self.motion_trail.append((x, y, 0.30))
        if len(self.motion_trail) > 12:
            self.motion_trail.pop(0)

    def update_timers(self, dt: float) -> None:
        next_trail = []
        for x, y, life in self.motion_trail:
            life -= dt
            if life > 0:
                next_trail.append((x, y, life))
        self.motion_trail = next_trail
        if self.death_flash > 0:
            self.death_flash -= dt

    def draw_head(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        for x, y, life in self.motion_trail:
            alpha = int(60 * life / 0.30)
            layer = pygame.Surface((CELL_SIZE * 2, CELL_SIZE * 2), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*self.color, alpha), (CELL_SIZE, CELL_SIZE), CELL_SIZE // 2)
            surface.blit(layer, (x - CELL_SIZE, y - CELL_SIZE))

        x, y = cell_center(self.head)
        if self.protected:
            glow = pygame.Surface((CELL_SIZE * 3, CELL_SIZE * 3), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*self.color, 46), (glow.get_width() // 2, glow.get_height() // 2), CELL_SIZE)
            surface.blit(glow, (x - glow.get_width() / 2, y - glow.get_height() / 2))

        body_color = self.color if self.alive else tuple(max(55, int(c * 0.48)) for c in self.color)
        head_color = tuple(min(255, c + 48) for c in body_color)
        radius = CELL_SIZE // 2
        pygame.draw.circle(surface, body_color, (x, y), radius)
        pygame.draw.circle(surface, head_color, (x, y - 2), max(2, radius - 2))

        dx, dy = self.direction
        px, py = -dy, dx
        eye_a = (x + dx * 3 + px * 3, y + dy * 3 + py * 3 - 1)
        eye_b = (x + dx * 3 - px * 3, y + dy * 3 - py * 3 - 1)
        pygame.draw.circle(surface, (35, 45, 54), eye_a, 2)
        pygame.draw.circle(surface, (35, 45, 54), eye_b, 2)

        if self.trail:
            pygame.draw.circle(surface, DANGER, (x, y), radius + 2, 1)

        if self.alive:
            label = font.render(self.name, True, WHITE)
            surface.blit(label, label.get_rect(center=(x, y - 14)))

        if self.death_flash > 0:
            flash_radius = int(27 * self.death_flash)
            pygame.draw.circle(surface, (*DANGER, 90), (x, y), flash_radius, 2)


def cell_center(cell: Cell) -> Tuple[int, int]:
    return BOARD_LEFT + cell[0] * CELL_SIZE + CELL_SIZE // 2, BOARD_TOP + cell[1] * CELL_SIZE + CELL_SIZE // 2


def add_vec(a: Cell, b: Vec) -> Cell:
    return a[0] + b[0], a[1] + b[1]


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def opposite(a: Vec, b: Vec) -> bool:
    return a[0] == -b[0] and a[1] == -b[1]


def mix(a: Color, b: Color, amount: float) -> Color:
    return tuple(int(a[i] * (1.0 - amount) + b[i] * amount) for i in range(3))


def board_outline_points() -> List[Tuple[int, int]]:
    return regular_hex_points(pad=1)


def rect_cells(left: int, top: int, width: int, height: int) -> Set[Cell]:
    return {(x, y) for x in range(left, left + width) for y in range(top, top + height)}


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
        self.font_small = pygame.font.SysFont("arial", 10, bold=True)
        self.font_ui = pygame.font.SysFont("arial", 13, bold=True)
        self.font_title = pygame.font.SysFont("arial", 27, bold=True)
        self.font_subtitle = pygame.font.SysFont("arial", 15, bold=True)
        self.font_winner = pygame.font.SysFont("arial", 38, bold=True)
        self.snakes: List[LightSnake] = []
        self.particles: List[Particle] = []
        self.paused = False
        self.game_over = False
        self.winner: Optional[LightSnake] = None
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.max_match_seconds = max(1, time_limit)
        self.window_recorder = WindowRecorder(
            enabled=record_window,
            window_title=WINDOW_TITLE,
            output_root=window_record_dir,
            session_prefix="light_snakes",
            video_filename="light_snakes_window.mp4",
            music_filename="light_snakes_window_music.mp4",
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
        self.snakes = []
        self.particles = []
        self.paused = False
        self.game_over = False
        self.winner = None
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.create_snakes()

    def create_snakes(self) -> None:
        # Tune speed, starting cell, and one-cell home zone here.
        configs = [
            ("GOLD", YELLOW, StrategyKind.BUILDER, (32, 14), (-1, 0), 1.00, {(32, 14)}, [(-1, 0), (0, 1), (1, 0), (0, -1)]),
            ("MINT", GREEN, StrategyKind.GUARDIAN, (25, 28), (-1, 0), 0.96, {(25, 28)}, [(-1, 0), (0, -1), (1, 0), (0, 1)]),
            ("ROSE", CORAL, StrategyKind.RAIDER, (8, 28), (1, 0), 0.98, {(8, 28)}, [(1, 0), (0, -1), (-1, 0), (0, 1)]),
            ("AZUR", BLUE, StrategyKind.SPRINTER, (1, 14), (1, 0), 1.06, {(1, 14)}, [(1, 0), (0, 1), (-1, 0), (0, -1)]),
            ("VIO", PURPLE, StrategyKind.THIEF, (8, 0), (1, 0), 1.07, {(8, 0)}, [(1, 0), (0, 1), (-1, 0), (0, -1)]),
            ("TEAL", TEAL, StrategyKind.SCOUT, (25, 0), (-1, 0), 1.12, {(25, 0)}, [(-1, 0), (0, 1), (1, 0), (0, -1)]),
        ]
        for name, color, strategy, start, direction, speed, territory, opening_steps in configs:
            self.snakes.append(
                LightSnake(name, color, strategy, start, direction, speed, set(territory), opening_steps=list(opening_steps))
            )

    def in_bounds(self, cell: Cell) -> bool:
        return cell in PLAYABLE_CELLS

    def cell_owner(self, cell: Cell) -> Optional[LightSnake]:
        for snake in self.snakes:
            if cell in snake.territory:
                return snake
        return None

    def is_enemy_territory(self, snake: LightSnake, cell: Cell) -> bool:
        owner = self.cell_owner(cell)
        return owner is not None and owner is not snake

    def owned_by(self, snake: LightSnake) -> Set[Cell]:
        return set(snake.territory)

    def all_territory(self) -> Set[Cell]:
        cells: Set[Cell] = set()
        for snake in self.snakes:
            cells.update(snake.territory)
        return cells

    def trail_owner_at(self, cell: Cell, exclude: Optional[LightSnake] = None) -> Optional[LightSnake]:
        for snake in self.snakes:
            if snake is exclude or not snake.alive:
                continue
            if cell in snake.trail:
                return snake
        return None

    def alive_head_at(self, cell: Cell, exclude: Optional[LightSnake] = None) -> Optional[LightSnake]:
        for snake in self.snakes:
            if snake is exclude or not snake.alive:
                continue
            if snake.head == cell:
                return snake
        return None

    def neutral_cells(self) -> Set[Cell]:
        owned = self.all_territory()
        return {cell for cell in ALL_CELLS if cell not in owned}

    def frontier_outside_cells(self, snake: LightSnake) -> Set[Cell]:
        result: Set[Cell] = set()
        for cell in snake.territory:
            for direction in DIRS:
                nxt = add_vec(cell, direction)
                if self.in_bounds(nxt) and nxt not in snake.territory and not self.is_enemy_territory(snake, nxt):
                    result.add(nxt)
        return result

    def own_border_cells(self, snake: LightSnake) -> Set[Cell]:
        result: Set[Cell] = set()
        for cell in snake.territory:
            if any(self.in_bounds(add_vec(cell, direction)) and add_vec(cell, direction) not in snake.territory for direction in DIRS):
                result.add(cell)
        return result

    def enemy_territory_cells(self, snake: LightSnake) -> Set[Cell]:
        cells: Set[Cell] = set()
        for other in self.snakes:
            if other is not snake:
                cells.update(other.territory)
        return cells

    def neutral_cells_near_enemy(self, snake: LightSnake) -> Set[Cell]:
        enemy_cells = self.enemy_territory_cells(snake)
        return {
            cell
            for cell in self.neutral_cells()
            if any(add_vec(cell, direction) in enemy_cells for direction in DIRS)
        }

    def enemy_trail_cells(self, snake: LightSnake) -> Set[Cell]:
        cells: Set[Cell] = set()
        for other in self.snakes:
            if other is not snake and other.alive:
                cells.update(other.trail)
        return cells

    def move_options(self, snake: LightSnake, allow_reverse: bool = False) -> List[Vec]:
        options = []
        for direction in DIRS:
            if not allow_reverse and opposite(direction, snake.direction):
                continue
            nxt = add_vec(snake.head, direction)
            if not self.in_bounds(nxt):
                continue
            if self.is_enemy_territory(snake, nxt):
                continue
            if self.alive_head_at(nxt, exclude=snake):
                continue
            options.append(direction)
        if not options and not allow_reverse:
            return self.move_options(snake, allow_reverse=True)
        return options

    def path_to_cells(self, snake: LightSnake, targets: Set[Cell]) -> Optional[Vec]:
        if not targets:
            return None
        if snake.head in targets:
            return None

        blocked = self.enemy_territory_cells(snake)
        alive_heads = {s.head for s in self.snakes if s is not snake and s.alive}
        seen = {snake.head}
        queue: List[Tuple[Cell, Vec]] = []
        nearest_target = min(targets, key=lambda cell: manhattan(snake.head, cell))

        first_steps = self.move_options(snake)
        first_steps.sort(key=lambda d: manhattan(add_vec(snake.head, d), nearest_target))
        for direction in first_steps:
            nxt = add_vec(snake.head, direction)
            if nxt in blocked or nxt in alive_heads or nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, direction))

        index = 0
        while index < len(queue):
            cell, first_direction = queue[index]
            index += 1
            if cell in targets:
                return first_direction
            for direction in DIRS:
                nxt = add_vec(cell, direction)
                if not self.in_bounds(nxt) or nxt in seen or nxt in blocked or nxt in alive_heads:
                    continue
                seen.add(nxt)
                queue.append((nxt, first_direction))
        return None

    def path_to_cell(self, snake: LightSnake, target: Cell) -> Optional[Vec]:
        return self.path_to_cells(snake, {target})

    def tail_threat_distance(self, snake: LightSnake) -> int:
        if not snake.trail:
            return 99
        enemies = [s for s in self.snakes if s is not snake and s.alive]
        if not enemies:
            return 99
        return min(manhattan(enemy.head, cell) for enemy in enemies for cell in snake.trail)

    def head_pressure_at(self, snake: LightSnake, cell: Cell) -> float:
        pressure = 0.0
        for other in self.snakes:
            if other is snake or not other.alive:
                continue
            distance = manhattan(cell, other.head)
            if other.protected and distance <= 1:
                pressure += 8.0
            elif distance <= 1:
                pressure += 3.0
            elif distance == 2:
                pressure += 1.1
        if cell[0] <= 0 or cell[0] >= GRID_COLS - 1:
            pressure += 0.6
        if cell[1] <= 0 or cell[1] >= GRID_ROWS - 1:
            pressure += 0.6
        return pressure

    def best_direction(
        self,
        snake: LightSnake,
        target: Optional[Cell],
        cautious: float,
        territory_bonus: float,
        trail_bonus: float = 28.0,
    ) -> Vec:
        options = self.move_options(snake)
        if not options:
            return snake.direction

        def score(direction: Vec) -> float:
            nxt = add_vec(snake.head, direction)
            value = random.random() * 0.7
            if target:
                value += manhattan(nxt, target)
            value += self.head_pressure_at(snake, nxt) * cautious
            owner = self.cell_owner(nxt)
            if owner is not None and owner is not snake:
                value += 1000.0
            if self.trail_owner_at(nxt, exclude=snake):
                value -= trail_bonus
            if snake.trail and nxt in snake.territory:
                value -= 12.0
            if not snake.trail and nxt not in snake.territory:
                value -= 1.5
            return value

        return min(options, key=score)

    def choose_direction(self, snake: LightSnake) -> Vec:
        if snake.opening_steps:
            direction = snake.opening_steps.pop(0)
            nxt = add_vec(snake.head, direction)
            if self.in_bounds(nxt) and not self.alive_head_at(nxt, exclude=snake):
                return direction

        adjacent_tail = self.adjacent_enemy_tail_direction(snake)
        if adjacent_tail and (
            (snake.strategy == StrategyKind.RAIDER and random.random() < 0.62)
            or (snake.strategy != StrategyKind.RAIDER and random.random() < 0.55)
        ):
            return adjacent_tail

        if snake.trail:
            return self.outside_direction(snake)
        forced_exit = self.force_exit_direction(snake)
        if forced_exit:
            return forced_exit
        return self.inside_direction(snake)

    def force_exit_direction(self, snake: LightSnake) -> Optional[Vec]:
        if snake.safe_moves < self.safe_home_limit(snake):
            return None
        exits = self.frontier_outside_cells(snake)
        if not exits:
            return None
        step = self.path_to_cells(snake, exits)
        if step:
            return step

        options = self.move_options(snake, allow_reverse=True)
        outside_steps = [direction for direction in options if add_vec(snake.head, direction) in exits]
        if outside_steps:
            return min(outside_steps, key=lambda direction: self.head_pressure_at(snake, add_vec(snake.head, direction)))
        return None

    def safe_home_limit(self, snake: LightSnake) -> int:
        if snake.strategy == StrategyKind.SPRINTER:
            return 3
        if snake.strategy == StrategyKind.GUARDIAN:
            return SAFE_HOME_MOVE_LIMIT + 2
        return SAFE_HOME_MOVE_LIMIT

    def adjacent_enemy_tail_direction(self, snake: LightSnake) -> Optional[Vec]:
        choices = []
        for direction in self.move_options(snake):
            nxt = add_vec(snake.head, direction)
            owner = self.trail_owner_at(nxt, exclude=snake)
            if owner:
                choices.append((direction, owner))
        if not choices:
            return None
        choices.sort(key=lambda item: (0 if item[1].strategy == StrategyKind.SPRINTER else 1, -len(item[1].trail)))
        return choices[0][0]

    def inside_direction(self, snake: LightSnake) -> Vec:
        if snake.strategy == StrategyKind.BUILDER:
            exits = self.frontier_outside_cells(snake)
            step = self.path_to_cells(snake, exits)
            if step and (snake.head in self.own_border_cells(snake) or random.random() < 0.72):
                return step
            border = self.own_border_cells(snake)
            if border:
                target = min(border, key=lambda cell: manhattan(snake.head, cell) + random.random() * 2)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.8, 2.0)

        if snake.strategy == StrategyKind.RAIDER:
            trails = self.enemy_trail_cells(snake)
            step = self.path_to_cells(snake, trails)
            if step:
                return step
            enemy_edges = self.neutral_cells_near_enemy(snake)
            if enemy_edges:
                target = min(enemy_edges, key=lambda cell: manhattan(snake.head, cell))
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.9, 5.0)

        if snake.strategy == StrategyKind.THIEF:
            trails = self.enemy_trail_cells(snake)
            if trails:
                target = min(trails, key=lambda cell: manhattan(snake.head, cell))
                step = self.path_to_cell(snake, target)
                if step:
                    return step
            enemy_edges = self.neutral_cells_near_enemy(snake)
            if enemy_edges:
                target = min(enemy_edges, key=lambda cell: manhattan(snake.head, cell) - self.head_pressure_at(snake, cell))
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.8, 6.2)

        if snake.strategy == StrategyKind.GUARDIAN:
            close_trails = {cell for cell in self.enemy_trail_cells(snake) if manhattan(snake.head, cell) <= 8}
            step = self.path_to_cells(snake, close_trails)
            if step:
                return step
            if random.random() < 0.34:
                exits = self.frontier_outside_cells(snake)
                target = min(exits, key=lambda cell: manhattan(snake.head, cell)) if exits else None
                if target:
                    return self.path_to_cell(snake, target) or self.best_direction(snake, target, 1.4, 1.8)
            border = self.own_border_cells(snake)
            if border:
                target = min(border, key=lambda cell: manhattan(snake.head, cell) + random.random() * 4)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 1.7, 1.2)

        if snake.strategy == StrategyKind.SPRINTER:
            outside = self.neutral_cells()
            if outside:
                target = max(outside, key=lambda cell: manhattan(snake.head, cell) - self.head_pressure_at(snake, cell) * 2)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.7, 3.0)

        if snake.strategy == StrategyKind.SCOUT:
            exits = self.frontier_outside_cells(snake)
            if exits:
                target = min(exits, key=lambda cell: manhattan(snake.head, cell) + self.head_pressure_at(snake, cell) * 2)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.9, 2.5)

        exits = self.frontier_outside_cells(snake)
        target = min(exits, key=lambda cell: manhattan(snake.head, cell)) if exits else None
        return self.best_direction(snake, target, 1.0, 2.0)

    def outside_direction(self, snake: LightSnake) -> Vec:
        home = set(snake.territory)
        return_step = self.path_to_cells(snake, home)
        threat = self.tail_threat_distance(snake)

        if snake.strategy == StrategyKind.BUILDER:
            limit = 9
            if len(snake.trail) >= limit or threat <= 2:
                if return_step:
                    return return_step
            target = self.choose_nearby_open_cell(snake, prefer_enemy=False)
            return self.path_to_cell(snake, target) or self.best_direction(snake, target, 1.0, 2.0)

        if snake.strategy == StrategyKind.RAIDER:
            tail_step = self.path_to_cells(snake, self.enemy_trail_cells(snake))
            if tail_step and threat > 2 and random.random() < 0.72:
                return tail_step
            if len(snake.trail) >= 10 or threat <= 3:
                if return_step:
                    return return_step
            enemy_edges = self.neutral_cells_near_enemy(snake)
            target = min(enemy_edges, key=lambda cell: manhattan(snake.head, cell)) if enemy_edges else self.choose_nearby_open_cell(snake, True)
            return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.9, 5.5)

        if snake.strategy == StrategyKind.THIEF:
            tail_step = self.path_to_cells(snake, self.enemy_trail_cells(snake))
            if tail_step and threat > 1:
                return tail_step
            if len(snake.trail) >= 10 or threat <= 2:
                if return_step:
                    return return_step
            target = self.choose_nearby_open_cell(snake, prefer_enemy=True)
            return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.85, 6.0)

        if snake.strategy == StrategyKind.GUARDIAN:
            if len(snake.trail) >= 5 or threat <= 3:
                if return_step:
                    return return_step
            target = self.choose_nearby_open_cell(snake, prefer_enemy=False)
            return self.path_to_cell(snake, target) or self.best_direction(snake, target, 1.7, 1.5)

        if snake.strategy == StrategyKind.SPRINTER:
            if len(snake.trail) >= 12 or threat <= 2:
                if return_step:
                    return return_step
            target = self.choose_far_open_cell(snake)
            return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.7, 3.0)

        if snake.strategy == StrategyKind.SCOUT:
            if len(snake.trail) >= 7 or threat <= 2:
                if return_step:
                    return return_step
            target = self.choose_nearby_open_cell(snake, prefer_enemy=False)
            return self.path_to_cell(snake, target) or self.best_direction(snake, target, 1.1, 2.0)

        if return_step:
            return return_step
        return self.best_direction(snake, None, 1.0, 2.0)

    def choose_nearby_open_cell(self, snake: LightSnake, prefer_enemy: bool) -> Cell:
        candidates = self.neutral_cells_near_enemy(snake) if prefer_enemy else self.neutral_cells()
        if not candidates:
            candidates = {
                cell
                for cell in ALL_CELLS
                if cell not in snake.territory and cell not in snake.trail and not self.is_enemy_territory(snake, cell)
            }
        if not candidates:
            return snake.head
        return min(candidates, key=lambda cell: manhattan(snake.head, cell) + self.head_pressure_at(snake, cell) * 2 + random.random() * 3)

    def choose_far_open_cell(self, snake: LightSnake) -> Cell:
        candidates = {
            cell
            for cell in ALL_CELLS
            if cell not in snake.territory and cell not in snake.trail and not self.is_enemy_territory(snake, cell)
        }
        if not candidates:
            return snake.head
        return max(candidates, key=lambda cell: manhattan(snake.head, cell) - self.head_pressure_at(snake, cell) * 2 + random.random() * 2)

    def update(self, dt: float) -> None:
        self.window_recorder.monitor()
        if self.paused:
            return

        for snake in self.snakes:
            snake.update_timers(dt)
        for particle in self.particles:
            particle.update(dt)
        self.particles = [particle for particle in self.particles if particle.life > 0]

        if self.game_over:
            self.end_timer += dt
            self.window_recorder.stop_after_game_over(self.end_timer)
            return

        self.match_time += dt
        if self.match_time >= self.max_match_seconds:
            self.finish_match_by_time_limit()
            return

        movers: List[LightSnake] = []
        for snake in self.snakes:
            if not snake.alive:
                continue
            snake.energy += snake.speed * MOVE_TICKS_PER_SECOND * dt
            if snake.energy >= 1.0:
                snake.energy -= 1.0
                movers.append(snake)

        if movers:
            self.resolve_moves(movers)
        self.check_game_over()

    def resolve_moves(self, movers: List[LightSnake]) -> None:
        proposals: Dict[LightSnake, Cell] = {}
        proposed_directions: Dict[LightSnake, Vec] = {}
        dead: Dict[LightSnake, str] = {}
        stalled: Set[LightSnake] = set()
        tail_cutters: Dict[LightSnake, LightSnake] = {}

        for snake in movers:
            direction = self.choose_direction(snake)
            nxt = add_vec(snake.head, direction)
            proposed_directions[snake] = direction
            proposals[snake] = nxt
            if not self.in_bounds(nxt):
                stalled.add(snake)
                continue
            if self.is_enemy_territory(snake, nxt):
                stalled.add(snake)
                continue
            if self.alive_head_at(nxt, exclude=snake):
                stalled.add(snake)
                continue
            tail_owner = self.trail_owner_at(nxt, exclude=snake)
            if tail_owner and tail_owner not in dead:
                dead[tail_owner] = "TAIL CUT"
                tail_cutters[tail_owner] = snake

        head_groups: Dict[Cell, List[LightSnake]] = {}
        for snake, nxt in proposals.items():
            if snake in dead or snake in stalled:
                continue
            head_groups.setdefault(nxt, []).append(snake)

        for group in head_groups.values():
            if len(group) >= 2:
                stalled.update(group)

        for victim, attacker in tail_cutters.items():
            if victim in dead and attacker.alive and attacker not in dead:
                attacker.cuts += 1
                self.emit_cut_particles(victim.trail[:], attacker.color)

        for snake, reason in list(dead.items()):
            self.kill_snake(snake, reason)

        for snake in stalled:
            if snake.alive and not snake.trail and snake.head in snake.territory:
                snake.safe_moves += 1

        for snake in movers:
            if not snake.alive or snake in stalled:
                continue
            nxt = proposals[snake]
            snake.direction = proposed_directions[snake]
            snake.add_motion_trail()
            snake.head = nxt
            if nxt in snake.territory:
                if snake.trail:
                    self.close_loop(snake)
                else:
                    snake.safe_moves += 1
            else:
                if nxt not in snake.trail:
                    snake.trail.append(nxt)
                snake.safe_moves = 0
                snake.last_gain = 0

    def close_loop(self, snake: LightSnake) -> None:
        boundary = set(snake.territory) | set(snake.trail)
        reachable: Set[Cell] = set()
        queue: List[Cell] = []

        for cell in ALL_CELLS:
            if cell in boundary:
                continue
            touches_outside = any(add_vec(cell, direction) not in PLAYABLE_CELLS for direction in DIRS)
            if touches_outside and cell not in reachable:
                reachable.add(cell)
                queue.append(cell)

        index = 0
        while index < len(queue):
            cell = queue[index]
            index += 1
            for direction in DIRS:
                nxt = add_vec(cell, direction)
                if not self.in_bounds(nxt) or nxt in boundary or nxt in reachable:
                    continue
                reachable.add(nxt)
                queue.append(nxt)

        enclosed = {cell for cell in ALL_CELLS if cell not in boundary and cell not in reachable}
        gained = set(snake.trail) | enclosed
        if gained:
            self.claim_cells(snake, gained)
            snake.captures += 1
            snake.last_gain = len(gained)
            snake.best_capture = max(snake.best_capture, len(gained))
            self.emit_capture_particles(gained, snake.color)
        snake.trail = []
        snake.safe_moves = 0

    def claim_cells(self, snake: LightSnake, cells: Set[Cell]) -> None:
        for other in self.snakes:
            if other is snake:
                continue
            other.territory.difference_update(cells)
        snake.territory.update(cells)

    def kill_snake(self, snake: LightSnake, reason: str) -> None:
        if not snake.alive:
            return
        snake.alive = False
        snake.final_cells = max(snake.final_cells, len(snake.territory))
        snake.death_reason = reason
        snake.death_flash = 1.0
        burst_cells = [snake.head] + snake.trail[:10]
        for cell in burst_cells:
            self.emit_death_particles(cell, snake.color)
        snake.trail = []

    def emit_capture_particles(self, cells: Set[Cell], color: Color) -> None:
        sample = list(cells)
        random.shuffle(sample)
        for cell in sample[:28]:
            x, y = cell_center(cell)
            angle = random.random() * math.tau
            speed = random.uniform(18, 62)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.55, 0.55, 2))

    def emit_cut_particles(self, trail: List[Cell], color: Color) -> None:
        if not trail:
            return
        sample = trail[:]
        random.shuffle(sample)
        for cell in sample[:16]:
            x, y = cell_center(cell)
            angle = random.random() * math.tau
            speed = random.uniform(35, 105)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.62, 0.62, 2.5))

    def emit_death_particles(self, cell: Cell, color: Color) -> None:
        x, y = cell_center(cell)
        for _ in range(5):
            angle = random.random() * math.tau
            speed = random.uniform(35, 125)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.75, 0.75, 3))

    def check_game_over(self) -> None:
        alive = [snake for snake in self.snakes if snake.alive]
        if len(alive) == 1:
            self.winner = alive[0]
            self.finish_reason = "LAST LIGHT"
            self.game_over = True
        elif len(alive) == 0:
            self.winner = max(self.snakes, key=lambda snake: (snake.score, snake.owned_cells, snake.cuts))
            self.finish_reason = "BEST SCORE"
            self.game_over = True

    def finish_match_by_time_limit(self) -> None:
        if self.game_over:
            return
        self.winner = max(self.snakes, key=lambda snake: (snake.score, snake.owned_cells, snake.cuts, int(snake.alive)))
        self.finish_reason = "TIME LIMIT"
        self.game_over = True
        self.end_timer = 0.0

    def draw(self) -> None:
        self.screen.fill(BG)
        self.draw_header()
        self.draw_board()
        self.draw_trails()
        for snake in self.snakes:
            snake.draw_head(self.screen, self.font_small)
        for particle in self.particles:
            particle.draw(self.screen)
        self.draw_scoreboard()
        if self.game_over and self.winner:
            self.draw_winner_screen()
        if self.paused:
            self.draw_pause()
        pygame.display.flip()
        self.window_recorder.start_if_pending()

    def draw_header(self) -> None:
        title = self.font_title.render("AI LIGHT SNAKES", True, WHITE)
        subtitle = self.font_subtitle.render("Whose light owns the board?", True, (94, 125, 145))
        remaining = max(0, int(self.max_match_seconds - self.match_time))
        timer = self.font_small.render(f"{remaining // 60:02d}:{remaining % 60:02d}", True, MUTED)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 24)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 50)))
        self.screen.blit(timer, timer.get_rect(center=(WIDTH // 2, 66)))

    def draw_board(self) -> None:
        outline = board_outline_points()
        pygame.draw.polygon(self.screen, (253, 254, 249), outline)

        for cell in ALL_CELLS:
            owner = self.cell_owner(cell)
            x, y = cell_center(cell)
            rect = pygame.Rect(x - CELL_SIZE // 2 + 1, y - CELL_SIZE // 2 + 1, CELL_SIZE - 2, CELL_SIZE - 2)
            if not owner:
                pygame.draw.rect(self.screen, NEUTRAL_CELL, rect, border_radius=3)
                pygame.draw.rect(self.screen, GRID, rect, 1, border_radius=3)
                continue
            amount = 0.33 if owner.alive else 0.18
            fill = mix(NEUTRAL_CELL, owner.color, amount)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            pygame.draw.rect(self.screen, GRID, rect, 1, border_radius=3)
            if owner.alive:
                shine = mix(fill, (255, 255, 255), 0.35)
                pygame.draw.circle(self.screen, shine, (x - 3, y - 3), 2)

        pygame.draw.polygon(self.screen, (205, 214, 204), outline, 1)

    def draw_trails(self) -> None:
        for snake in self.snakes:
            if not snake.trail:
                continue
            for index, cell in enumerate(snake.trail):
                x, y = cell_center(cell)
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 170.0 + index * 0.75)
                rect = pygame.Rect(x - CELL_SIZE // 2 + 3, y - CELL_SIZE // 2 + 3, CELL_SIZE - 6, CELL_SIZE - 6)
                pygame.draw.rect(self.screen, mix(PANEL, snake.color, 0.78), rect, border_radius=4)
                pygame.draw.rect(self.screen, DANGER if pulse > 0.7 else snake.color, rect, 1, border_radius=4)

            if len(snake.trail) >= 2:
                points = [cell_center(cell) for cell in snake.trail]
                pygame.draw.lines(self.screen, snake.color, False, points, 2)

    def draw_scoreboard(self) -> None:
        rect = pygame.Rect(12, SCORE_TOP, WIDTH - 24, HEIGHT - SCORE_TOP - 12)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=4)
        pygame.draw.rect(self.screen, (207, 216, 207), rect, 1, border_radius=4)
        headers = ["NAME / AI STYLE", "CELLS", "CUT", "STATUS"]
        xs = [22, 198, 240, 282]
        for header, x in zip(headers, xs):
            self.screen.blit(self.font_small.render(header, True, MUTED), (x, SCORE_TOP + 8))
        for index, snake in enumerate(self.snakes):
            y = SCORE_TOP + 22 + index * 30
            pygame.draw.circle(self.screen, snake.color, (24, y + 5), 4)
            status = snake.status()
            status_color = SAFE if status == "safe" else DANGER if status == "dead" else snake.color
            texts = [
                (snake.name, 33, snake.color),
                (str(snake.owned_cells), 205, WHITE),
                (str(snake.cuts), 246, WHITE),
                (status, 282, status_color),
            ]
            for text, x, color in texts:
                self.screen.blit(self.font_ui.render(text, True, color), (x, y))
            self.screen.blit(self.font_ui.render(snake.strategy.value, True, WHITE), (33, y + 13))

    def draw_winner_screen(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((246, 248, 242, 205))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(35, 205, WIDTH - 70, 210)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=4)
        pygame.draw.rect(self.screen, self.winner.color, panel, 2, border_radius=4)
        winner_text = self.font_winner.render("WINNER", True, self.winner.color)
        name_text = self.font_title.render(self.winner.name, True, WHITE)
        strat_text = self.font_subtitle.render(self.winner.strategy.value, True, (94, 125, 145))
        score_text = self.font_subtitle.render(f"Cells {self.winner.owned_cells}  Cuts {self.winner.cuts}", True, WHITE)
        reason_text = self.font_small.render(self.finish_reason, True, MUTED)
        restart_text = self.font_ui.render("Press R for new match", True, MUTED)
        for surf, y in [(winner_text, 242), (name_text, 288), (strat_text, 325), (score_text, 352), (reason_text, 372), (restart_text, 390)]:
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))

    def draw_pause(self) -> None:
        label = self.font_title.render("PAUSED", True, WHITE)
        self.screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    def save_screenshot(self) -> None:
        pygame.image.save(self.screen, f"light_snakes_screenshot_{pygame.time.get_ticks()}.png")

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
    parser = argparse.ArgumentParser(description="AI Light Snake Capture pygame simulation")
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
        default="",
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
