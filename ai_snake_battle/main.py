import argparse
import math
import os
import random
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from window_recorder import WindowRecorder

import pygame


# ---------------------------
# Quick tuning constants
# ---------------------------
WIDTH, HEIGHT = 360, 640
WINDOW_TITLE = "AI Snake Battle"
FPS = 60
CELL_SIZE = 15
GRID_COLS = 15
GRID_ROWS = 22
BOARD_LEFT = (WIDTH - GRID_COLS * CELL_SIZE) // 2
BOARD_TOP = 75
BOARD_WIDTH = GRID_COLS * CELL_SIZE
BOARD_HEIGHT = GRID_ROWS * CELL_SIZE
SCORE_TOP = BOARD_TOP + BOARD_HEIGHT + 11
MOVE_TICKS_PER_SECOND = 4.75
FOOD_COUNT = 9
INITIAL_LENGTH = 5
MATCH_TIME_LIMIT_SECONDS = 180
WINDOW_RECORD_FPS = 30
WINDOW_RECORD_CAPTURE_SIZE = (WIDTH, HEIGHT)
WINDOW_RECORD_OUTPUT_SIZE = (1080, 1920)
WINDOW_RECORD_END_DELAY_SECONDS = 1.0
WINDOW_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_recordings")

BG = (246, 248, 242)
PANEL = (255, 255, 250)
GRID = (222, 228, 218)
WHITE = (42, 50, 62)
MUTED = (126, 137, 139)
DANGER = (210, 93, 96)

Vec = Tuple[int, int]
Cell = Tuple[int, int]

DIRS: List[Vec] = [(1, 0), (-1, 0), (0, 1), (0, -1)]


class StrategyKind(Enum):
    GREEDY = "Greedy"
    CAREFUL = "Careful"
    AGGRESSIVE = "Aggressive"
    HUNTER = "Hunter"
    CHAOTIC = "Chaotic"


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
class Food:
    cell: Cell
    born_time: float = 0.0
    pulse: float = random.random() * 10.0

    def draw(self, surface: pygame.Surface, now: float) -> None:
        x, y = cell_center(self.cell)
        age = min(1.0, (now - self.born_time) * 4.0)
        glow_radius = int((CELL_SIZE * 0.65 + CELL_SIZE * 0.2 * math.sin(now * 5 + self.pulse)) * age)
        glow = pygame.Surface((glow_radius * 4, glow_radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(
            glow,
            (232, 126, 122, 42),
            (glow.get_width() // 2, glow.get_height() // 2),
            glow_radius * 2,
        )
        surface.blit(glow, (x - glow.get_width() / 2, y - glow.get_height() / 2))
        pygame.draw.circle(surface, (218, 112, 105), (x, y), max(1, int(CELL_SIZE * 0.38 * age)))
        pygame.draw.circle(surface, (255, 219, 176), (x - 2, y - 2), max(1, int(CELL_SIZE * 0.16 * age)))
        pygame.draw.line(surface, (105, 158, 112), (x + 2, y - 6), (x + 6, y - 11), 2)


@dataclass(eq=False)
class Snake:
    name: str
    color: Tuple[int, int, int]
    strategy: StrategyKind
    body: List[Cell]
    direction: Vec
    speed: float
    score: int = 0
    alive: bool = True
    energy: float = 0.0
    trail: List[Tuple[float, float, float]] = field(default_factory=list)
    death_flash: float = 0.0

    @property
    def head(self) -> Cell:
        return self.body[0]

    @property
    def length(self) -> int:
        return len(self.body)

    def add_trail(self) -> None:
        x, y = cell_center(self.head)
        self.trail.append((x, y, 0.35))
        if len(self.trail) > 14:
            self.trail.pop(0)

    def update_trail(self, dt: float) -> None:
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
            alpha = int(90 * life / 0.35)
            layer = pygame.Surface((CELL_SIZE * 2, CELL_SIZE * 2), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*self.color, alpha), (CELL_SIZE, CELL_SIZE), CELL_SIZE // 2)
            surface.blit(layer, (x - CELL_SIZE, y - CELL_SIZE))

        for index, cell in enumerate(reversed(self.body)):
            real_index = len(self.body) - 1 - index
            cx, cy = cell_center(cell)
            shade = 0.55 + 0.45 * (1 - real_index / max(1, len(self.body)))
            color = tuple(min(255, int(c * shade + 25)) for c in self.color)
            rect = pygame.Rect(cx - CELL_SIZE // 2 + 2, cy - CELL_SIZE // 2 + 2, CELL_SIZE - 4, CELL_SIZE - 4)
            pygame.draw.rect(surface, color, rect, border_radius=6)

        hx, hy = cell_center(self.head)
        head_color = tuple(min(255, c + 55) for c in self.color)
        pygame.draw.circle(surface, head_color, (hx, hy), CELL_SIZE // 2)
        eye_offset = 4
        pygame.draw.circle(surface, (35, 45, 54), (hx - eye_offset, hy - 2), 2)
        pygame.draw.circle(surface, (35, 45, 54), (hx + eye_offset, hy - 2), 2)

        if self.alive:
            label = font.render(self.name, True, WHITE)
            label_rect = label.get_rect(center=(hx, hy - 10))
            surface.blit(label, label_rect)

        if self.death_flash > 0:
            radius = int(25 * self.death_flash)
            pygame.draw.circle(surface, (*DANGER, 90), (hx, hy), radius, 2)


def cell_center(cell: Cell) -> Tuple[int, int]:
    return BOARD_LEFT + cell[0] * CELL_SIZE + CELL_SIZE // 2, BOARD_TOP + cell[1] * CELL_SIZE + CELL_SIZE // 2


def add_vec(a: Cell, b: Vec) -> Cell:
    return a[0] + b[0], a[1] + b[1]


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def opposite(a: Vec, b: Vec) -> bool:
    return a[0] == -b[0] and a[1] == -b[1]


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
        self.snakes: List[Snake] = []
        self.foods: List[Food] = []
        self.particles: List[Particle] = []
        self.paused = False
        self.game_over = False
        self.winner: Optional[Snake] = None
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.max_match_seconds = max(1, time_limit)
        self.window_recorder = WindowRecorder(
            enabled=record_window,
            window_title=WINDOW_TITLE,
            output_root=window_record_dir,
            session_prefix="snake_battle",
            video_filename="snake_battle_window.mp4",
            music_filename="snake_battle_window_music.mp4",
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
        self.foods = []
        self.particles = []
        self.game_over = False
        self.winner = None
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.create_snakes()
        for _ in range(FOOD_COUNT):
            self.spawn_food()

    def create_snakes(self) -> None:
        # Edit this list to add, remove, recolor, or retune AI players.
        configs = [
            ("GREEDY", (221, 177, 76), StrategyKind.GREEDY, (4, 4), (1, 0), 1.05),
            ("CAREFUL", (104, 166, 129), StrategyKind.CAREFUL, (10, 4), (-1, 0), 0.92),
            ("AGGRO", (198, 104, 101), StrategyKind.AGGRESSIVE, (4, 16), (1, 0), 1.12),
            ("HUNTER", (92, 139, 184), StrategyKind.HUNTER, (10, 16), (-1, 0), 1.0),
            ("CHAOS", (150, 124, 180), StrategyKind.CHAOTIC, (7, 10), (0, -1), 1.2),
        ]
        for name, color, strategy, start, direction, speed in configs:
            body = [add_vec(start, (-direction[0] * i, -direction[1] * i)) for i in range(INITIAL_LENGTH)]
            self.snakes.append(Snake(name, color, strategy, body, direction, speed))

    def occupied_cells(self, include_dead: bool = True) -> Dict[Cell, Snake]:
        occupied: Dict[Cell, Snake] = {}
        for snake in self.snakes:
            if include_dead or snake.alive:
                for cell in snake.body:
                    occupied[cell] = snake
        return occupied

    def spawn_food(self) -> None:
        occupied = set(self.occupied_cells().keys())
        occupied.update(food.cell for food in self.foods)
        free = [(x, y) for x in range(GRID_COLS) for y in range(GRID_ROWS) if (x, y) not in occupied]
        if not free:
            return
        self.foods.append(Food(random.choice(free), pygame.time.get_ticks() / 1000.0))

    def in_bounds(self, cell: Cell) -> bool:
        return 0 <= cell[0] < GRID_COLS and 0 <= cell[1] < GRID_ROWS

    def legal_dirs(self, snake: Snake) -> List[Vec]:
        return [d for d in DIRS if snake.length <= 1 or not opposite(d, snake.direction)]

    def safe_dirs(self, snake: Snake, avoid_heads: bool = True) -> List[Vec]:
        result = []
        occupied = self.occupied_cells(include_dead=True)
        if snake.body:
            occupied.pop(snake.body[-1], None)
        for direction in self.legal_dirs(snake):
            nxt = add_vec(snake.head, direction)
            if not self.in_bounds(nxt):
                continue
            if nxt in occupied:
                continue
            if avoid_heads and self.head_threat_score(snake, nxt) >= 8:
                continue
            result.append(direction)
        if avoid_heads and not result:
            return self.safe_dirs(snake, avoid_heads=False)
        return result

    def choose_direction(self, snake: Snake) -> Vec:
        # Every strategy returns one grid direction. Change these methods to alter AI behavior.
        if snake.strategy == StrategyKind.GREEDY:
            return self.greedy_direction(snake)
        if snake.strategy == StrategyKind.CAREFUL:
            return self.careful_direction(snake)
        if snake.strategy == StrategyKind.AGGRESSIVE:
            return self.aggressive_direction(snake)
        if snake.strategy == StrategyKind.HUNTER:
            return self.hunter_direction(snake)
        return self.chaotic_direction(snake)

    def dirs_toward(self, snake: Snake, target: Cell, dirs: Optional[List[Vec]] = None) -> List[Vec]:
        choices = dirs if dirs is not None else [d for d in DIRS if not opposite(d, snake.direction)]
        return sorted(choices, key=lambda d: manhattan(add_vec(snake.head, d), target))

    def nearest_food(self, snake: Snake) -> Optional[Food]:
        if not self.foods:
            return None
        return min(self.foods, key=lambda food: manhattan(snake.head, food.cell))

    def head_threat_score(self, snake: Snake, cell: Cell) -> float:
        score = 0.0
        for other in self.snakes:
            if other is snake or not other.alive:
                continue
            if cell == other.head and other.length >= snake.length:
                score += 20
            for direction in self.legal_dirs(other):
                possible = add_vec(other.head, direction)
                if possible == cell:
                    if other.length >= snake.length:
                        score += 8
                    else:
                        score += 1.5
        return score

    def open_space(self, snake: Snake, start: Cell, limit: int = 90) -> int:
        if not self.in_bounds(start):
            return 0
        blocked = set(self.occupied_cells(include_dead=True).keys())
        if snake.body:
            blocked.discard(snake.body[-1])
        if start in blocked:
            return 0

        seen = {start}
        queue = [start]
        index = 0
        while index < len(queue) and len(seen) < limit:
            cell = queue[index]
            index += 1
            for direction in DIRS:
                nxt = add_vec(cell, direction)
                if not self.in_bounds(nxt) or nxt in blocked or nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return len(seen)

    def path_to_nearest_food(self, snake: Snake) -> Optional[Vec]:
        if not self.foods:
            return None

        targets = {food.cell for food in self.foods}
        blocked = set(self.occupied_cells(include_dead=True).keys())
        if snake.body:
            blocked.discard(snake.body[-1])
        blocked.discard(snake.head)

        first_steps = self.safe_dirs(snake)
        first_steps.sort(key=lambda d: manhattan(add_vec(snake.head, d), self.nearest_food(snake).cell))

        seen = {snake.head}
        queue: List[Tuple[Cell, Vec]] = []
        for direction in first_steps:
            nxt = add_vec(snake.head, direction)
            if nxt in blocked or nxt in seen:
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
                if not self.in_bounds(nxt) or nxt in blocked or nxt in seen:
                    continue
                if nxt not in targets and self.head_threat_score(snake, nxt) >= 8:
                    continue
                seen.add(nxt)
                queue.append((nxt, first_direction))
        return None

    def path_to_food(self, snake: Snake, target: Cell, avoid_heads: bool = True) -> Optional[Vec]:
        blocked = set(self.occupied_cells(include_dead=True).keys())
        if snake.body:
            blocked.discard(snake.body[-1])
        blocked.discard(snake.head)

        first_steps = self.safe_dirs(snake, avoid_heads=avoid_heads)
        first_steps.sort(key=lambda d: manhattan(add_vec(snake.head, d), target))

        seen = {snake.head}
        queue: List[Tuple[Cell, Vec]] = []
        for direction in first_steps:
            nxt = add_vec(snake.head, direction)
            if nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, direction))

        index = 0
        while index < len(queue):
            cell, first_direction = queue[index]
            index += 1
            if cell == target:
                return first_direction
            for direction in DIRS:
                nxt = add_vec(cell, direction)
                if not self.in_bounds(nxt) or nxt in blocked or nxt in seen:
                    continue
                if avoid_heads and nxt != target and self.head_threat_score(snake, nxt) >= 8:
                    continue
                seen.add(nxt)
                queue.append((nxt, first_direction))
        return None

    def smarter_score(self, snake: Snake, direction: Vec, target: Optional[Cell], danger_weight: float, space_weight: float) -> float:
        nxt = add_vec(snake.head, direction)
        target_cost = manhattan(nxt, target) if target else 0
        open_cells = self.open_space(snake, nxt)
        danger = self.danger_score(snake, direction) * danger_weight
        cramped = max(0, snake.length + 4 - open_cells) * 3
        space_bonus = open_cells * space_weight
        return target_cost + danger + cramped - space_bonus

    def greedy_direction(self, snake: Snake) -> Vec:
        food = self.nearest_food(snake)
        safe = self.safe_dirs(snake)
        options = safe or self.legal_dirs(snake)
        if food:
            path_step = self.path_to_food(snake, food.cell, avoid_heads=True)
            if path_step:
                return path_step

            direct_steps = self.dirs_toward(snake, food.cell, options)
            direct_safe = [d for d in direct_steps if d in safe]
            if direct_safe:
                return direct_safe[0]
            return direct_steps[0]
        return random.choice(options)

    def danger_score(self, snake: Snake, direction: Vec) -> float:
        nxt = add_vec(snake.head, direction)
        score = 0.0
        if nxt[0] <= 1 or nxt[0] >= GRID_COLS - 2:
            score += 3
        if nxt[1] <= 1 or nxt[1] >= GRID_ROWS - 2:
            score += 3
        occupied = self.occupied_cells(include_dead=True)
        for d in DIRS:
            around = add_vec(nxt, d)
            if around in occupied:
                score += 1.4
        for other in self.snakes:
            if other is snake or not other.alive:
                continue
            if manhattan(nxt, other.head) <= 2 and other.length >= snake.length:
                score += 4
        score += self.head_threat_score(snake, nxt)
        return score

    def careful_direction(self, snake: Snake) -> Vec:
        safe = self.safe_dirs(snake)
        if not safe:
            return self.greedy_direction(snake)
        food = self.nearest_food(snake)
        if not food:
            return max(safe, key=lambda d: self.open_space(snake, add_vec(snake.head, d)) - self.danger_score(snake, d) * 3)

        food_path = self.path_to_nearest_food(snake)
        if food_path:
            nxt = add_vec(snake.head, food_path)
            enough_room = self.open_space(snake, nxt) >= max(8, min(18, snake.length + 2))
            if enough_room or nxt == food.cell:
                return food_path

        return min(safe, key=lambda d: self.smarter_score(snake, d, food.cell, 2.2, 0.02))

    def nearest_enemy(self, snake: Snake) -> Optional[Snake]:
        enemies = [s for s in self.snakes if s is not snake and s.alive]
        if not enemies:
            return None
        return min(enemies, key=lambda s: manhattan(snake.head, s.head))

    def aggressive_direction(self, snake: Snake) -> Vec:
        enemy = self.nearest_enemy(snake)
        safe = self.safe_dirs(snake)
        options = safe or self.legal_dirs(snake)
        if enemy:
            # Aiming near the enemy head makes this snake visibly cut across paths.
            target_options = [add_vec(enemy.head, d) for d in DIRS] + [enemy.head]
            target_options = [c for c in target_options if self.in_bounds(c)]
            target = min(target_options, key=lambda c: manhattan(snake.head, c))
            return min(options, key=lambda d: self.smarter_score(snake, d, target, 1.0, 0.05))
        return self.greedy_direction(snake)

    def hunter_direction(self, snake: Snake) -> Vec:
        enemies = [s for s in self.snakes if s is not snake and s.alive]
        nearby = [s for s in enemies if manhattan(snake.head, s.head) < 13]
        if nearby:
            target_snake = min(nearby, key=lambda s: (s.length, manhattan(snake.head, s.head)))
            flank_cells = [add_vec(target_snake.head, d) for d in DIRS]
            flank_cells = [c for c in flank_cells if self.in_bounds(c)]
            target = min(flank_cells, key=lambda c: manhattan(snake.head, c)) if flank_cells else target_snake.head
            safe = self.safe_dirs(snake)
            options = safe or self.legal_dirs(snake)
            return min(options, key=lambda d: self.smarter_score(snake, d, target, 1.5, 0.08))
        return self.careful_direction(snake)

    def chaotic_direction(self, snake: Snake) -> Vec:
        safe = self.safe_dirs(snake)
        options = safe or self.legal_dirs(snake)
        if random.random() < 0.38:
            return random.choice(options)
        if random.random() < 0.78 and self.foods:
            return min(options, key=lambda d: self.smarter_score(snake, d, self.nearest_food(snake).cell, 0.9, 0.03) + random.random() * 2)
        return random.choice(options)

    def update(self, dt: float) -> None:
        self.window_recorder.monitor()
        if self.paused:
            return
        for snake in self.snakes:
            snake.update_trail(dt)
        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

        if self.game_over:
            self.end_timer += dt
            self.window_recorder.stop_after_game_over(self.end_timer)
            return

        self.match_time += dt
        if self.match_time >= self.max_match_seconds:
            self.finish_match_by_time_limit()
            return

        movers: List[Snake] = []
        for snake in self.snakes:
            if not snake.alive:
                continue
            snake.energy += snake.speed * MOVE_TICKS_PER_SECOND * dt
            if snake.energy >= 1:
                snake.energy -= 1
                movers.append(snake)

        if movers:
            self.resolve_moves(movers)
        while len(self.foods) < FOOD_COUNT:
            self.spawn_food()
        self.check_game_over()

    def resolve_moves(self, movers: List[Snake]) -> None:
        food_by_cell = {food.cell: food for food in self.foods}
        proposals: Dict[Snake, Cell] = {}
        will_eat: Dict[Snake, bool] = {}
        dead: Dict[Snake, str] = {}

        for snake in movers:
            snake.direction = self.choose_direction(snake)
            proposals[snake] = add_vec(snake.head, snake.direction)
            will_eat[snake] = proposals[snake] in food_by_cell

        occupied_after_tail = self.occupied_cells(include_dead=True)
        removed_tails: Dict[Snake, Cell] = {}
        for snake in movers:
            if snake.alive and not will_eat[snake] and snake.body:
                removed_tails[snake] = snake.body[-1]
                occupied_after_tail.pop(snake.body[-1], None)

        for snake, nxt in proposals.items():
            if nxt[0] < 0 or nxt[0] >= GRID_COLS or nxt[1] < 0 or nxt[1] >= GRID_ROWS:
                dead[snake] = "wall"
            elif nxt in occupied_after_tail:
                dead[snake] = "body"

        head_groups: Dict[Cell, List[Snake]] = {}
        for snake, nxt in proposals.items():
            if snake not in dead:
                head_groups.setdefault(nxt, []).append(snake)

        for group in head_groups.values():
            if len(group) < 2:
                continue
            max_len = max(s.length for s in group)
            winners = [s for s in group if s.length == max_len]
            if len(winners) == 1:
                for snake in group:
                    if snake is not winners[0]:
                        dead[snake] = "head"
            else:
                for snake in group:
                    dead[snake] = "head"

        # Head swaps are also dramatic head-to-head collisions.
        for a in movers:
            for b in movers:
                if a is b or a in dead or b in dead:
                    continue
                if proposals[a] == b.head and proposals[b] == a.head:
                    if a.length > b.length:
                        dead[b] = "swap"
                    elif b.length > a.length:
                        dead[a] = "swap"
                    else:
                        dead[a] = "swap"
                        dead[b] = "swap"

        # If a snake dies this tick, its tail does not move away; it becomes part of the corpse.
        for corpse, tail_cell in removed_tails.items():
            if corpse not in dead:
                continue
            for snake, nxt in proposals.items():
                if snake is corpse or snake in dead:
                    continue
                if nxt == tail_cell:
                    dead[snake] = "corpse"

        for snake in dead:
            self.kill_snake(snake)

        eaten_foods: List[Food] = []
        for snake in movers:
            if not snake.alive:
                continue
            nxt = proposals[snake]
            snake.add_trail()
            snake.body.insert(0, nxt)
            if will_eat[snake]:
                snake.score += 10
                eaten_foods.append(food_by_cell[nxt])
                self.emit_food_particles(nxt, snake.color)
            else:
                snake.body.pop()

        if eaten_foods:
            eaten = set(eaten_foods)
            self.foods = [food for food in self.foods if food not in eaten]

    def kill_snake(self, snake: Snake) -> None:
        if not snake.alive:
            return
        snake.alive = False
        snake.death_flash = 1.0
        for cell in snake.body[:12]:
            self.emit_death_particles(cell, snake.color)

    def emit_food_particles(self, cell: Cell, color: Tuple[int, int, int]) -> None:
        x, y = cell_center(cell)
        for _ in range(18):
            angle = random.random() * math.tau
            speed = random.uniform(40, 105)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.55, 0.55, 2))

    def emit_death_particles(self, cell: Cell, color: Tuple[int, int, int]) -> None:
        x, y = cell_center(cell)
        for _ in range(5):
            angle = random.random() * math.tau
            speed = random.uniform(35, 130)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.8, 0.8, 3))

    def check_game_over(self) -> None:
        alive = [snake for snake in self.snakes if snake.alive]
        if len(alive) == 1:
            self.winner = alive[0]
            self.finish_reason = "LAST SNAKE"
            self.game_over = True
        elif len(alive) == 0:
            self.winner = max(self.snakes, key=lambda s: (s.score, s.length))
            self.finish_reason = "BEST SCORE"
            self.game_over = True

    def finish_match_by_time_limit(self) -> None:
        if self.game_over:
            return
        self.winner = max(self.snakes, key=lambda s: (s.score, s.length, int(s.alive)))
        self.finish_reason = "TIME LIMIT"
        self.game_over = True
        self.end_timer = 0.0

    def draw(self) -> None:
        now = pygame.time.get_ticks() / 1000.0
        self.screen.fill(BG)
        self.draw_header()
        self.draw_board()
        for food in self.foods:
            food.draw(self.screen, now)
        for snake in self.snakes:
            snake.draw(self.screen, self.font_small)
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
        title = self.font_title.render("AI SNAKE BATTLE", True, WHITE)
        subtitle = self.font_subtitle.render("Which strategy wins?", True, (94, 125, 145))
        remaining = max(0, int(self.max_match_seconds - self.match_time))
        timer = self.font_small.render(f"{remaining // 60:02d}:{remaining % 60:02d}", True, MUTED)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 24)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 50)))
        self.screen.blit(timer, timer.get_rect(center=(WIDTH // 2, 66)))

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

    def draw_scoreboard(self) -> None:
        rect = pygame.Rect(12, SCORE_TOP, WIDTH - 24, HEIGHT - SCORE_TOP - 12)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=4)
        pygame.draw.rect(self.screen, (207, 216, 207), rect, 1, border_radius=4)
        headers = ["NAME", "AI", "SCORE", "LEN", "STATUS"]
        xs = [22, 92, 178, 231, 274]
        for header, x in zip(headers, xs):
            self.screen.blit(self.font_small.render(header, True, MUTED), (x, SCORE_TOP + 8))
        for index, snake in enumerate(self.snakes):
            y = SCORE_TOP + 22 + index * 15
            pygame.draw.circle(self.screen, snake.color, (24, y + 5), 4)
            texts = [
                (snake.name, 33, snake.color),
                (snake.strategy.value, 92, WHITE),
                (str(snake.score), 185, WHITE),
                (str(snake.length), 236, WHITE),
                ("alive" if snake.alive else "dead", 274, (80, 145, 103) if snake.alive else DANGER),
            ]
            for text, x, color in texts:
                self.screen.blit(self.font_ui.render(text, True, color), (x, y))

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
        score_text = self.font_subtitle.render(f"Score {self.winner.score}  Length {self.winner.length}", True, WHITE)
        reason_text = self.font_small.render(self.finish_reason, True, MUTED)
        restart_text = self.font_ui.render("Press R for new match", True, MUTED)
        for surf, y in [(winner_text, 242), (name_text, 288), (strat_text, 325), (score_text, 352), (reason_text, 372), (restart_text, 390)]:
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))

    def draw_pause(self) -> None:
        label = self.font_title.render("PAUSED", True, WHITE)
        self.screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    def save_screenshot(self) -> None:
        pygame.image.save(self.screen, f"screenshot_{pygame.time.get_ticks()}.png")

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
    parser = argparse.ArgumentParser(description="AI Snake Battle pygame simulation")
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
