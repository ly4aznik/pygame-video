import argparse
from array import array
import math
import os
import random
import struct
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
SAFE_HOME_MOVE_LIMIT = 1
BONUS_DETECTION_DISTANCE = GRID_COLS + GRID_ROWS
BONUS_BIG_SNAKE_MIN_DISTANCE = 10
BONUS_REACHABILITY_CHECK_LIMIT = 70
BONUS_RESPAWN_SECONDS = (7.0, 13.0)
ERASER_BALL_RADIUS = 8
ERASER_BALL_SPEED = 27.0

BG = (8, 10, 18)
PANEL = (18, 22, 35)
GRID = (38, 45, 65)
WHITE = (245, 247, 255)
MUTED = (170, 178, 200)
DANGER = (255, 70, 90)
SAFE = (90, 240, 150)
NEUTRAL_CELL = (13, 17, 29)

YELLOW = (255, 210, 75)
GREEN = (90, 240, 150)
CORAL = (255, 70, 90)
BLUE = (70, 150, 255)
PURPLE = (190, 100, 255)
TEAL = (55, 225, 225)
BONUS_COLOR = (255, 190, 70)
ERASER_COLOR = (255, 255, 255)

Vec = Tuple[int, int]
Cell = Tuple[int, int]
Color = Tuple[int, int, int]

DIRS: List[Vec] = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def make_sound(frequency: float, duration: float, volume: float, slide: float = 0.0) -> pygame.mixer.Sound:
    sample_rate = 44100
    frames = bytearray()
    count = int(sample_rate * duration)
    for index in range(count):
        progress = index / count
        pitch = frequency * (1.0 + slide * progress)
        envelope = math.sin(math.pi * progress) ** 0.45 * (1.0 - progress) ** 0.35
        wave = math.sin(math.tau * pitch * index / sample_rate)
        wave += 0.22 * math.sin(math.tau * pitch * 2.01 * index / sample_rate)
        sample = int(max(-1.0, min(1.0, wave * envelope * volume)) * 32767)
        frames.extend(struct.pack("<h", sample))
    return pygame.mixer.Sound(buffer=bytes(frames))


def make_voxel_sound(frequency: float, duration: float, volume: float, tone: str) -> pygame.mixer.Sound:
    sample_rate = 44100
    samples = array("h")
    count = int(sample_rate * duration)
    rng = random.Random(int(frequency * 100 + duration * 1000))
    for index in range(count):
        progress = index / count
        phase = math.tau * frequency * index / sample_rate
        if tone == "block":
            envelope = (1.0 - progress) ** 5
            wave = 0.58 * (1.0 if math.sin(phase) >= 0 else -1.0)
            wave += rng.uniform(-0.42, 0.42) * (1.0 - progress)
        elif tone == "glass":
            envelope = math.exp(-5.5 * progress)
            wave = math.sin(phase) + 0.48 * math.sin(phase * 2.01) + 0.24 * math.sin(phase * 3.98)
        elif tone == "sand":
            envelope = (1.0 - progress) ** 3
            wave = rng.uniform(-1.0, 1.0) * 0.72 + math.sin(phase) * 0.28
        elif tone == "bass":
            envelope = math.sin(math.pi * progress) ** 0.35 * (1.0 - progress) ** 1.8
            wave = math.sin(phase) + 0.3 * math.sin(phase * 0.5)
        else:
            envelope = math.exp(-4.0 * progress)
            wave = math.sin(phase) + 0.2 * math.sin(phase * 2.0)
        sample = int(max(-1.0, min(1.0, wave * envelope * volume)) * 32767)
        samples.append(sample)
    return pygame.mixer.Sound(buffer=samples.tobytes())


def make_ambient_melody() -> pygame.mixer.Sound:
    sample_rate = 44100
    beat = 0.55
    notes = [261.63, 329.63, 392.00, 493.88, 440.00, 392.00, 329.63, 293.66,
             261.63, 329.63, 440.00, 392.00, 293.66, 349.23, 329.63, 261.63]
    bass = [130.81, 130.81, 110.00, 110.00, 146.83, 146.83, 130.81, 130.81]
    total = int(sample_rate * beat * len(notes))
    samples = array("h")
    for index in range(total):
        time = index / sample_rate
        note_index = min(len(notes) - 1, int(time / beat))
        local = (time % beat) / beat
        note = notes[note_index]
        bass_note = bass[(note_index // 2) % len(bass)]
        pluck = math.exp(-3.7 * local)
        pad = 0.5 - 0.5 * math.cos(math.tau * min(1.0, local))
        wave = math.sin(math.tau * note * time) * pluck * 0.12
        wave += math.sin(math.tau * note * 2.002 * time) * pluck * 0.035
        wave += math.sin(math.tau * bass_note * time) * (0.055 + pad * 0.018)
        samples.append(int(max(-1.0, min(1.0, wave)) * 32767))
    return pygame.mixer.Sound(buffer=samples.tobytes())


class SoundBank:
    def __init__(self) -> None:
        self.enabled = False
        self.countdown_channel: Optional[pygame.mixer.Channel] = None
        self.music_channel: Optional[pygame.mixer.Channel] = None
        self.music = None
        self.start = self.big_capture = self.bonus = self.erase = self.death = self.finish = None
        self.countdown = self.countdown_final = None
        self.capture: List[pygame.mixer.Sound] = []
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(2)
            self.countdown_channel = pygame.mixer.Channel(0)
            self.music_channel = pygame.mixer.Channel(1)
            self.start = make_voxel_sound(392, .42, .28, "glass")
            self.capture = [make_voxel_sound(pitch, .075, .17, "block") for pitch in (196, 220, 247, 262)]
            self.big_capture = make_voxel_sound(294, .34, .28, "glass")
            self.bonus = make_voxel_sound(784, .55, .28, "glass")
            self.erase = make_voxel_sound(105, .18, .22, "sand")
            self.death = make_voxel_sound(123, .42, .30, "bass")
            self.countdown = make_voxel_sound(523, .15, .34, "block")
            self.countdown_final = make_voxel_sound(659, .27, .42, "glass")
            self.finish = make_voxel_sound(392, .82, .32, "glass")
            self.music = make_ambient_melody()
            self.music_channel.set_volume(0.7)
            self.music_channel.play(self.music, loops=-1)
            self.enabled = True
        except pygame.error:
            pass

    def play(self, sound: pygame.mixer.Sound) -> None:
        if self.enabled and sound:
            sound.play()

    def play_countdown(self, final: bool = False) -> None:
        sound = self.countdown_final if final else self.countdown
        if self.enabled and sound:
            if self.countdown_channel:
                self.countdown_channel.play(sound)
            else:
                sound.play()


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
    BUILDER = "Runs clean circles"
    RAIDER = "Builds triangles"
    GUARDIAN = "Hugs left wall"
    SPRINTER = "Sharp zigzags"
    THIEF = "Tight spiral"
    SCOUT = "Hunts fresh cells"


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


@dataclass
class Bonus:
    cell: Cell
    pulse: float = field(default_factory=lambda: random.random() * 10.0)

    def draw(self, surface: pygame.Surface, now: float) -> None:
        x, y = cell_center(self.cell)
        pulse = 0.5 + 0.5 * math.sin(now * 5.5 + self.pulse)
        glow_radius = int(CELL_SIZE * (1.2 + pulse * 0.45))
        glow = pygame.Surface((glow_radius * 4, glow_radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*BONUS_COLOR, 48), (glow.get_width() // 2, glow.get_height() // 2), glow_radius * 2)
        surface.blit(glow, (x - glow.get_width() / 2, y - glow.get_height() / 2))

        rect = pygame.Rect(0, 0, CELL_SIZE + 3, CELL_SIZE + 3)
        rect.center = (x, y)
        pygame.draw.rect(surface, (255, 239, 179), rect, border_radius=4)
        pygame.draw.rect(surface, BONUS_COLOR, rect, 2, border_radius=4)
        pygame.draw.line(surface, BONUS_COLOR, (x - 4, y), (x + 4, y), 2)
        pygame.draw.line(surface, BONUS_COLOR, (x, y - 4), (x, y + 4), 2)


@dataclass
class EraserBall:
    x: float
    y: float
    vx: float
    vy: float
    radius: int = ERASER_BALL_RADIUS

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surface: pygame.Surface) -> None:
        glow_radius = self.radius + 7
        glow = pygame.Surface((glow_radius * 4, glow_radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*ERASER_COLOR, 34), (glow.get_width() // 2, glow.get_height() // 2), glow_radius * 2)
        surface.blit(glow, (self.x - glow.get_width() / 2, self.y - glow.get_height() / 2))

        pygame.draw.circle(surface, (248, 250, 247), (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, ERASER_COLOR, (int(self.x), int(self.y)), self.radius, 2)
        pygame.draw.circle(surface, (177, 188, 190), (int(self.x - 3), int(self.y - 3)), max(2, self.radius // 3))


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
    head_size: int = 1
    cuts: int = 0
    captures: int = 0
    best_capture: int = 0
    final_cells: int = 0
    last_gain: int = 0
    death_reason: str = ""
    death_flash: float = 0.0
    pattern_step: int = 0
    pattern_index: int = 0

    @property
    def protected(self) -> bool:
        return self.alive and self.head in self.territory

    @property
    def score(self) -> int:
        owned = len(self.territory) if self.alive else max(self.final_cells, len(self.territory))
        return owned

    @property
    def owned_cells(self) -> int:
        return len(self.territory) if self.alive else max(self.final_cells, len(self.territory))

    def status(self) -> str:
        if self.head_size > 1:
            return "big"
        return "paint"

    def add_motion_trail(self) -> None:
        x, y = self.head_center()
        self.motion_trail.append((x, y, 0.30))
        if len(self.motion_trail) > 12:
            self.motion_trail.pop(0)

    def head_center(self) -> Tuple[int, int]:
        x, y = cell_center(self.head)
        if self.head_size <= 1:
            return x, y
        return x + CELL_SIZE // 2, y + CELL_SIZE // 2

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

        x, y = self.head_center()
        if self.protected:
            glow_size = CELL_SIZE * (self.head_size + 2)
            glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*self.color, 46), (glow.get_width() // 2, glow.get_height() // 2), CELL_SIZE * self.head_size)
            surface.blit(glow, (x - glow.get_width() / 2, y - glow.get_height() / 2))

        body_color = self.color if self.alive else tuple(max(55, int(c * 0.48)) for c in self.color)
        head_color = tuple(min(255, c + 48) for c in body_color)
        if self.head_size > 1:
            rect = pygame.Rect(0, 0, CELL_SIZE * 2 - 2, CELL_SIZE * 2 - 2)
            rect.center = (x, y)
            pygame.draw.rect(surface, body_color, rect, border_radius=7)
            inner = rect.inflate(-4, -4)
            pygame.draw.rect(surface, head_color, inner, border_radius=6)
        else:
            radius = CELL_SIZE // 2
            pygame.draw.circle(surface, body_color, (x, y), radius)
            pygame.draw.circle(surface, head_color, (x, y - 2), max(2, radius - 2))

        dx, dy = self.direction
        px, py = -dy, dx
        eye_forward = 5 if self.head_size > 1 else 3
        eye_spread = 4 if self.head_size > 1 else 3
        eye_a = (x + dx * eye_forward + px * eye_spread, y + dy * eye_forward + py * eye_spread - 1)
        eye_b = (x + dx * eye_forward - px * eye_spread, y + dy * eye_forward - py * eye_spread - 1)
        pygame.draw.circle(surface, (35, 45, 54), eye_a, 2)
        pygame.draw.circle(surface, (35, 45, 54), eye_b, 2)

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
        audio_source: str = "auto",
        audio_backend: str = "wasapi",
    ) -> None:
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.screen.fill(BG)
        pygame.display.flip()
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.SysFont("arial", 10, bold=True)
        self.font_ui = pygame.font.SysFont("arial", 13, bold=True)
        self.font_title = pygame.font.SysFont("arial", 27, bold=True)
        self.font_subtitle = pygame.font.SysFont("arial", 15, bold=True)
        self.font_winner = pygame.font.SysFont("arial", 38, bold=True)
        self.sounds = SoundBank()
        self.last_capture_sound = -1.0
        self.last_erase_sound = -1.0
        self.last_countdown_second: Optional[int] = None
        self.snakes: List[LightSnake] = []
        self.particles: List[Particle] = []
        self.bonus: Optional[Bonus] = None
        self.bonus_timer = 0.0
        self.initial_bonus_race = False
        self.eraser_ball: Optional[EraserBall] = None
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
            capture_audio=True,
            audio_source=audio_source,
            audio_backend=audio_backend,
            audio_volume=1.0,
            pipe_video=True,
        )
        self.restart()

    def restart(self) -> None:
        self.window_recorder.new_match()
        self.snakes = []
        self.particles = []
        self.bonus = None
        self.bonus_timer = 5.0
        self.initial_bonus_race = False
        self.eraser_ball = self.create_eraser_ball()
        self.paused = False
        self.game_over = False
        self.winner = None
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.last_countdown_second = None
        self.create_snakes()
        self.sounds.play(self.sounds.start)

    def create_eraser_ball(self) -> EraserBall:
        angle = random.uniform(0.0, math.tau)
        speed = ERASER_BALL_SPEED
        return EraserBall(
            BOARD_LEFT + BOARD_WIDTH / 2,
            BOARD_TOP + BOARD_HEIGHT / 2,
            math.cos(angle) * speed,
            math.sin(angle) * speed,
        )

    def create_snakes(self) -> None:
        # Tune speed, starting cell, and one-cell home zone here.
        configs = [
            ("MAX", YELLOW, StrategyKind.BUILDER, (32, 14), (-1, 0), 1.00, {(32, 14)}, [(-1, 0), (0, 1), (1, 0), (0, -1)]),
            ("LEO", GREEN, StrategyKind.GUARDIAN, (25, 28), (-1, 0), 0.96, {(25, 28)}, [(-1, 0), (0, -1), (1, 0), (0, 1)]),
            ("MIA", CORAL, StrategyKind.RAIDER, (8, 28), (1, 0), 0.98, {(8, 28)}, [(1, 0), (0, -1), (-1, 0), (0, 1)]),
            ("ZOE", BLUE, StrategyKind.SPRINTER, (1, 14), (1, 0), 1.06, {(1, 14)}, [(1, 0), (0, 1), (-1, 0), (0, -1)]),
            ("NOA", PURPLE, StrategyKind.THIEF, (8, 0), (1, 0), 1.07, {(8, 0)}, [(1, 0), (0, 1), (-1, 0), (0, -1)]),
            ("SAM", TEAL, StrategyKind.SCOUT, (25, 0), (-1, 0), 1.12, {(25, 0)}, [(-1, 0), (0, 1), (1, 0), (0, -1)]),
        ]
        for name, color, strategy, start, direction, speed, territory, opening_steps in configs:
            self.snakes.append(
                LightSnake(name, color, strategy, start, direction, speed, set(territory), opening_steps=list(opening_steps))
            )

    def in_bounds(self, cell: Cell) -> bool:
        return cell in PLAYABLE_CELLS

    def footprint_for(self, snake: LightSnake, head: Optional[Cell] = None, size: Optional[int] = None) -> Set[Cell]:
        anchor = snake.head if head is None else head
        head_size = snake.head_size if size is None else size
        return {
            (anchor[0] + dx, anchor[1] + dy)
            for dx in range(head_size)
            for dy in range(head_size)
        }

    def can_occupy(self, snake: LightSnake, head: Cell, size: Optional[int] = None) -> bool:
        footprint = self.footprint_for(snake, head, size)
        if any(cell not in PLAYABLE_CELLS for cell in footprint):
            return False
        if any(self.is_enemy_territory(snake, cell) for cell in footprint):
            return False
        for other in self.snakes:
            if other is snake or not other.alive:
                continue
            if footprint & self.footprint_for(other):
                return False
        return True

    def cell_owner(self, cell: Cell) -> Optional[LightSnake]:
        for snake in self.snakes:
            if cell in snake.territory:
                return snake
        return None

    def is_enemy_territory(self, snake: LightSnake, cell: Cell) -> bool:
        owner = self.cell_owner(cell)
        return owner is not None and owner is not snake

    def clear_cells(self, cells: Set[Cell]) -> None:
        if not cells:
            return
        for snake in self.snakes:
            snake.territory.difference_update(cells)

    def cells_touched_by_ball(self, ball: EraserBall) -> Set[Cell]:
        touch_radius = ball.radius + CELL_SIZE * 0.72
        return {
            cell
            for cell in ALL_CELLS
            if math.dist(cell_center(cell), (ball.x, ball.y)) <= touch_radius
        }

    def nearest_wall_normal(self, point: Tuple[float, float]) -> Tuple[float, float]:
        px, py = point
        polygon = board_outline_points()
        best_distance = float("inf")
        best_normal = (1.0, 0.0)

        for index, start in enumerate(polygon):
            end = polygon[(index + 1) % len(polygon)]
            ax, ay = start
            bx, by = end
            edge_x = bx - ax
            edge_y = by - ay
            length_sq = edge_x * edge_x + edge_y * edge_y
            if length_sq == 0:
                continue
            t = max(0.0, min(1.0, ((px - ax) * edge_x + (py - ay) * edge_y) / length_sq))
            closest = (ax + edge_x * t, ay + edge_y * t)
            dx = px - closest[0]
            dy = py - closest[1]
            distance = math.hypot(dx, dy)
            if distance < best_distance:
                best_distance = distance
                if distance > 0:
                    best_normal = (dx / distance, dy / distance)

        return best_normal

    def update_eraser_ball(self, dt: float) -> None:
        if not self.eraser_ball:
            return

        ball = self.eraser_ball
        previous = (ball.x, ball.y)
        ball.update(dt)
        polygon = board_outline_points()

        if not point_in_polygon((ball.x, ball.y), polygon):
            normal = self.nearest_wall_normal((ball.x, ball.y))
            dot = ball.vx * normal[0] + ball.vy * normal[1]
            ball.vx -= 2 * dot * normal[0]
            ball.vy -= 2 * dot * normal[1]
            ball.x, ball.y = previous
            ball.update(dt)

            if not point_in_polygon((ball.x, ball.y), polygon):
                center = (BOARD_LEFT + BOARD_WIDTH / 2, BOARD_TOP + BOARD_HEIGHT / 2)
                ball.x = previous[0] * 0.7 + center[0] * 0.3
                ball.y = previous[1] * 0.7 + center[1] * 0.3

        cleared = self.cells_touched_by_ball(ball)
        owned_cleared = {cell for cell in cleared if self.cell_owner(cell)}
        if owned_cleared:
            self.clear_cells(owned_cleared)
            if self.match_time - self.last_erase_sound > 0.18:
                self.sounds.play(self.sounds.erase)
                self.last_erase_sound = self.match_time
            if random.random() < 0.45:
                self.emit_eraser_particles(random.choice(list(owned_cleared)))

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
            if cell in self.footprint_for(snake):
                return snake
        return None

    def neutral_cells(self) -> Set[Cell]:
        owned = self.all_territory()
        return {cell for cell in ALL_CELLS if cell not in owned}

    def bonus_spawn_cells(self) -> List[Cell]:
        cells = []
        occupied_heads = set()
        for snake in self.snakes:
            if snake.alive:
                occupied_heads.update(self.footprint_for(snake))

        for cell in self.neutral_cells():
            footprint = {(cell[0] + dx, cell[1] + dy) for dx in range(2) for dy in range(2)}
            if any(part not in PLAYABLE_CELLS for part in footprint):
                continue
            if any(self.cell_owner(part) is not None for part in footprint):
                continue
            if footprint & occupied_heads:
                continue
            cells.append(cell)
        return cells

    def spawn_bonus(self) -> None:
        cells = self.bonus_spawn_cells()
        if not cells:
            self.bonus_timer = random.uniform(*BONUS_RESPAWN_SECONDS)
            return
        big_snakes = [snake for snake in self.snakes if snake.alive and snake.head_size > 1]
        far_cells = [
            cell
            for cell in cells
            if all(manhattan(cell, big.head) >= BONUS_BIG_SNAKE_MIN_DISTANCE for big in big_snakes)
        ]
        if far_cells:
            cells = far_cells
        random.shuffle(cells)
        reachable_cells = [
            cell
            for cell in cells[:BONUS_REACHABILITY_CHECK_LIMIT]
            if any(snake.alive and snake.head_size == 1 and self.path_to_cell(snake, cell) for snake in self.snakes)
        ]
        if not reachable_cells:
            reachable_cells = cells[:BONUS_REACHABILITY_CHECK_LIMIT]
        self.bonus = Bonus(random.choice(reachable_cells))
        self.bonus_timer = random.uniform(*BONUS_RESPAWN_SECONDS)

    def spawn_initial_bonus(self) -> None:
        cells = self.bonus_spawn_cells()
        if not cells:
            self.spawn_bonus()
            return
        center = (BOARD_LEFT + BOARD_WIDTH / 2, BOARD_TOP + BOARD_HEIGHT / 2)
        self.bonus = Bonus(min(cells, key=lambda cell: math.dist(cell_center(cell), center)))
        self.initial_bonus_race = True

    def update_bonus(self, dt: float) -> None:
        if self.bonus:
            if self.bonus.cell not in self.neutral_cells():
                self.bonus = None
                self.initial_bonus_race = False
            return
        self.initial_bonus_race = False
        self.bonus_timer -= dt
        if self.bonus_timer <= 0:
            self.spawn_bonus()

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
            if not self.can_occupy(snake, nxt):
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
        seen = {snake.head}
        queue: List[Tuple[Cell, Vec]] = []
        nearest_target = min(targets, key=lambda cell: manhattan(snake.head, cell))

        first_steps = self.move_options(snake)
        first_steps.sort(key=lambda d: manhattan(add_vec(snake.head, d), nearest_target))
        for direction in first_steps:
            nxt = add_vec(snake.head, direction)
            if nxt in blocked or nxt in seen or not self.can_occupy(snake, nxt):
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
                if nxt in seen or nxt in blocked or not self.can_occupy(snake, nxt):
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
            if nxt not in snake.territory:
                value -= 1.5
            return value

        return min(options, key=score)

    def choose_direction(self, snake: LightSnake) -> Vec:
        if self.initial_bonus_race:
            bonus_step = self.bonus_direction(snake)
            if bonus_step:
                return bonus_step

        if snake.opening_steps:
            direction = snake.opening_steps.pop(0)
            nxt = add_vec(snake.head, direction)
            if self.can_occupy(snake, nxt):
                return direction

        bonus_step = self.bonus_direction(snake)
        if bonus_step:
            return bonus_step

        forced_exit = self.force_exit_direction(snake)
        if forced_exit:
            return forced_exit

        pattern_step = self.pattern_direction(snake)
        if pattern_step:
            return pattern_step

        fresh_step = self.fresh_cell_direction(snake)
        if fresh_step:
            return fresh_step
        return self.inside_direction(snake)

    def nearest_playable_cell(self, target: Tuple[float, float]) -> Cell:
        return min(ALL_CELLS, key=lambda cell: math.dist(cell, target))

    def pattern_direction(self, snake: LightSnake) -> Optional[Vec]:
        options = self.move_options(snake)
        if not options:
            return None

        center = ((GRID_COLS - 1) / 2, (GRID_ROWS - 1) / 2)

        def base_score(direction: Vec) -> float:
            nxt = add_vec(snake.head, direction)
            score = -self.head_pressure_at(snake, nxt) * 2.0
            if self.cell_owner(nxt) is None:
                score += 5.0
            if direction == snake.direction:
                score += 0.7
            if self.trail_owner_at(nxt, exclude=snake):
                score += 7.0
            return score

        def toward(target: Cell, direction: Vec) -> float:
            return base_score(direction) - manhattan(add_vec(snake.head, direction), target) * 1.5

        if snake.strategy == StrategyKind.BUILDER:
            radius = 9.5

            def circle_score(direction: Vec) -> float:
                nxt = add_vec(snake.head, direction)
                dx, dy = nxt[0] - center[0], nxt[1] - center[1]
                distance = max(0.1, math.hypot(dx, dy))
                tangent = (-dy / distance, dx / distance)
                flow = direction[0] * tangent[0] + direction[1] * tangent[1]
                return base_score(direction) + flow * 5.0 - abs(distance - radius) * 1.4

            return max(options, key=circle_score)

        if snake.strategy == StrategyKind.GUARDIAN:
            nearby_rows = {snake.head[1] - 1, snake.head[1], snake.head[1] + 1}
            left_edge = min((cell for cell in ALL_CELLS if cell[1] in nearby_rows), key=lambda cell: cell[0])
            if snake.head[0] > left_edge[0] + 1:
                return max(options, key=lambda direction: toward(left_edge, direction))
            vertical = -1 if (snake.pattern_step // 13) % 2 == 0 else 1
            return max(
                options,
                key=lambda direction: base_score(direction)
                - add_vec(snake.head, direction)[0] * 2.4
                + direction[1] * vertical * 4.0,
            )

        if snake.strategy == StrategyKind.RAIDER:
            triangle = [
                self.nearest_playable_cell((GRID_COLS / 2, 3)),
                self.nearest_playable_cell((5, GRID_ROWS - 5)),
                self.nearest_playable_cell((GRID_COLS - 6, GRID_ROWS - 5)),
            ]
            target = triangle[snake.pattern_index % len(triangle)]
            if manhattan(snake.head, target) <= 2:
                snake.pattern_index = (snake.pattern_index + 1) % len(triangle)
                target = triangle[snake.pattern_index]
            return max(options, key=lambda direction: toward(target, direction))

        if snake.strategy == StrategyKind.SPRINTER:
            zigzag = [
                self.nearest_playable_cell((4, 5)),
                self.nearest_playable_cell((GRID_COLS - 5, 9)),
                self.nearest_playable_cell((4, 14)),
                self.nearest_playable_cell((GRID_COLS - 5, 19)),
                self.nearest_playable_cell((4, GRID_ROWS - 5)),
            ]
            target = zigzag[snake.pattern_index % len(zigzag)]
            if manhattan(snake.head, target) <= 2:
                snake.pattern_index = (snake.pattern_index + 1) % len(zigzag)
                target = zigzag[snake.pattern_index]
            return max(options, key=lambda direction: toward(target, direction) + (2.0 if direction == snake.direction else 0.0))

        if snake.strategy == StrategyKind.THIEF:
            cycle = snake.pattern_step % 72
            radius = 11.5 - cycle * 0.12
            angle = snake.pattern_step * 0.34
            target = self.nearest_playable_cell(
                (center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius)
            )
            return max(options, key=lambda direction: toward(target, direction))

        if snake.strategy == StrategyKind.SCOUT:
            fresh = self.neutral_cells()
            if fresh:
                owned_cells = snake.territory or {snake.head}
                target = max(
                    fresh,
                    key=lambda cell: min(manhattan(cell, owned) for owned in owned_cells)
                    - self.head_pressure_at(snake, cell) * 3,
                )
                return max(options, key=lambda direction: toward(target, direction))

        return None

    def bonus_direction(self, snake: LightSnake) -> Optional[Vec]:
        if not self.bonus or snake.head_size > 1:
            return None
        if manhattan(snake.head, self.bonus.cell) > BONUS_DETECTION_DISTANCE:
            return None
        step = self.path_to_cell(snake, self.bonus.cell)
        if step:
            return step
        options = self.move_options(snake)
        if options:
            return min(options, key=lambda direction: manhattan(add_vec(snake.head, direction), self.bonus.cell))
        return None

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
            return 0
        if snake.strategy == StrategyKind.GUARDIAN:
            return SAFE_HOME_MOVE_LIMIT + 1
        return SAFE_HOME_MOVE_LIMIT

    def fresh_cell_direction(self, snake: LightSnake) -> Optional[Vec]:
        fresh_cells = self.neutral_cells()
        if not fresh_cells:
            return None

        adjacent_fresh = [
            direction
            for direction in self.move_options(snake)
            if add_vec(snake.head, direction) in fresh_cells
        ]
        if adjacent_fresh:
            return min(adjacent_fresh, key=lambda direction: self.head_pressure_at(snake, add_vec(snake.head, direction)))

        step = self.path_to_cells(snake, fresh_cells)
        if step:
            return step
        return None

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
            enemy_edges = self.neutral_cells_near_enemy(snake)
            if enemy_edges:
                target = min(enemy_edges, key=lambda cell: manhattan(snake.head, cell))
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.9, 5.0)

        if snake.strategy == StrategyKind.THIEF:
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
                if cell not in snake.territory and not self.is_enemy_territory(snake, cell)
            }
        if not candidates:
            return snake.head
        return min(candidates, key=lambda cell: manhattan(snake.head, cell) + self.head_pressure_at(snake, cell) * 2 + random.random() * 3)

    def choose_far_open_cell(self, snake: LightSnake) -> Cell:
        candidates = {
            cell
            for cell in ALL_CELLS
            if cell not in snake.territory and not self.is_enemy_territory(snake, cell)
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
        self.update_bonus(dt)

        if self.game_over:
            self.end_timer += dt
            self.window_recorder.stop_after_game_over(self.end_timer)
            return

        self.match_time += dt
        remaining = max(0, math.ceil(self.max_match_seconds - self.match_time))
        if 0 < remaining <= 15 and remaining != self.last_countdown_second:
            self.sounds.play_countdown(final=remaining <= 3)
            self.last_countdown_second = remaining
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
        self.update_eraser_ball(dt)
        self.check_game_over()

    def resolve_moves(self, movers: List[LightSnake]) -> None:
        proposals: Dict[LightSnake, Cell] = {}
        proposed_directions: Dict[LightSnake, Vec] = {}
        proposed_sizes: Dict[LightSnake, int] = {}
        stalled: Set[LightSnake] = set()

        for snake in movers:
            direction = self.choose_direction(snake)
            nxt = add_vec(snake.head, direction)
            proposed_directions[snake] = direction
            proposals[snake] = nxt
            proposed_sizes[snake] = snake.head_size
            if not self.can_occupy(snake, nxt):
                stalled.add(snake)
                continue
            if (
                self.bonus
                and snake.head_size == 1
                and self.bonus.cell in self.footprint_for(snake, nxt)
                and self.can_occupy(snake, nxt, size=2)
            ):
                proposed_sizes[snake] = 2

        proposed_footprints: Dict[LightSnake, Set[Cell]] = {}
        for snake, nxt in proposals.items():
            if snake in stalled:
                continue
            proposed_footprints[snake] = self.footprint_for(snake, nxt, size=proposed_sizes[snake])

        snakes = list(proposed_footprints.keys())
        for index, snake in enumerate(snakes):
            for other in snakes[index + 1:]:
                if proposed_footprints[snake] & proposed_footprints[other]:
                    stalled.add(snake)
                    stalled.add(other)

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
            snake.pattern_step += 1
            collected_bonus = self.bonus is not None and proposed_sizes[snake] > snake.head_size
            if collected_bonus:
                snake.head_size = 2
                self.bonus = None
                self.sounds.play(self.sounds.bonus)
                if self.initial_bonus_race:
                    self.initial_bonus_race = False
                    for racer in self.snakes:
                        racer.opening_steps = []

            footprint = self.footprint_for(snake)
            new_cells = {cell for cell in footprint if self.cell_owner(cell) is not snake}
            if not new_cells:
                snake.safe_moves += 1
            else:
                self.claim_cells(snake, new_cells)
                snake.captures += len(new_cells)
                snake.last_gain = len(new_cells)
                snake.best_capture = max(snake.best_capture, len(new_cells))
                self.emit_capture_particles(new_cells, snake.color if not collected_bonus else BONUS_COLOR)
                if not collected_bonus and self.match_time - self.last_capture_sound > 0.09:
                    if self.sounds.capture:
                        sound = self.sounds.capture[snake.captures % len(self.sounds.capture)]
                        self.sounds.play(sound)
                    self.last_capture_sound = self.match_time
                snake.safe_moves = 0
            snake.trail = []
        self.fill_surrounded_neutral_regions()

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
            self.sounds.play(self.sounds.big_capture)
        snake.trail = []
        snake.safe_moves = 0

    def claim_cells(self, snake: LightSnake, cells: Set[Cell]) -> None:
        for other in self.snakes:
            if other is snake:
                continue
            other.territory.difference_update(cells)
        snake.territory.update(cells)

    def fill_surrounded_neutral_regions(self) -> None:
        neutral = self.neutral_cells()
        seen: Set[Cell] = set()

        for start in list(neutral):
            if start in seen:
                continue
            region: Set[Cell] = set()
            border_owners: Set[LightSnake] = set()
            touches_wall = False
            queue = [start]
            seen.add(start)

            index = 0
            while index < len(queue):
                cell = queue[index]
                index += 1
                region.add(cell)

                for direction in DIRS:
                    nxt = add_vec(cell, direction)
                    if nxt not in PLAYABLE_CELLS:
                        touches_wall = True
                        continue
                    owner = self.cell_owner(nxt)
                    if owner:
                        border_owners.add(owner)
                        continue
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)

            if touches_wall or len(border_owners) != 1:
                continue
            owner = next(iter(border_owners))
            self.claim_cells(owner, region)
            owner.captures += len(region)
            owner.last_gain = len(region)
            owner.best_capture = max(owner.best_capture, len(region))
            self.emit_capture_particles(region, owner.color)

    def kill_snake(self, snake: LightSnake, reason: str) -> None:
        if not snake.alive:
            return
        snake.alive = False
        snake.final_cells = max(snake.final_cells, len(snake.territory))
        snake.death_reason = reason
        snake.death_flash = 1.0
        self.sounds.play(self.sounds.death)
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

    def emit_eraser_particles(self, cell: Cell) -> None:
        x, y = cell_center(cell)
        for _ in range(3):
            angle = random.random() * math.tau
            speed = random.uniform(12, 42)
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    ERASER_COLOR,
                    0.42,
                    0.42,
                    2,
                )
            )

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
        return

    def finish_match_by_time_limit(self) -> None:
        if self.game_over:
            return
        self.winner = max(self.snakes, key=lambda snake: (snake.owned_cells, snake.captures))
        self.finish_reason = "TIME LIMIT"
        self.game_over = True
        self.end_timer = 0.0
        self.sounds.play(self.sounds.finish)

    def draw(self) -> None:
        self.screen.fill(BG)
        self.draw_header()
        self.draw_board()
        self.draw_trails()
        if self.eraser_ball:
            self.eraser_ball.draw(self.screen)
        if self.bonus:
            self.bonus.draw(self.screen, pygame.time.get_ticks() / 1000.0)
        for snake in self.snakes:
            snake.draw_head(self.screen, self.font_small)
        for particle in self.particles:
            particle.draw(self.screen)
        self.draw_scoreboard()
        self.draw_countdown()
        if self.match_time < 1.5 and not self.game_over:
            self.draw_hook()
        if self.game_over and self.winner:
            self.draw_winner_screen()
        if self.paused:
            self.draw_pause()
        pygame.display.flip()
        self.window_recorder.start_if_pending()
        if self.window_recorder.needs_video_frame():
            self.window_recorder.write_video_frame(pygame.image.tostring(self.screen, "RGB"))

    def draw_hook(self) -> None:
        panel = pygame.Surface((300, 78), pygame.SRCALPHA)
        pygame.draw.rect(panel, (8, 10, 18, 225), panel.get_rect(), border_radius=12)
        pygame.draw.rect(panel, (*ERASER_COLOR, 210), panel.get_rect(), 2, border_radius=12)
        self.screen.blit(panel, (30, 246))
        hook = self.font_title.render("WHO CONTROLS THE BOARD?", True, WHITE)
        threat = self.font_subtitle.render("DODGE THE ERASER", True, DANGER)
        self.screen.blit(hook, hook.get_rect(center=(WIDTH // 2, 270)))
        self.screen.blit(threat, threat.get_rect(center=(WIDTH // 2, 300)))

    def draw_header(self) -> None:
        title = self.font_title.render("PICK YOUR SNAKE", True, WHITE)
        subtitle = self.font_subtitle.render("WHITE BALL ERASES TERRITORY", True, MUTED)
        remaining = max(0, math.ceil(self.max_match_seconds - self.match_time))
        timer = self.font_small.render(f"{remaining // 60:02d}:{remaining % 60:02d}", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 24)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 50)))
        self.screen.blit(timer, timer.get_rect(center=(WIDTH // 2, 66)))

    def draw_countdown(self) -> None:
        remaining = max(0, math.ceil(self.max_match_seconds - self.match_time))
        if 0 < remaining <= 15:
            pulse = 1.0 + 0.18 * (0.5 + 0.5 * math.sin(self.match_time * math.tau * 2.0))
            countdown = self.font_winner.render(str(remaining), True, DANGER if remaining <= 5 else WHITE)
            countdown = pygame.transform.smoothscale(
                countdown,
                (int(countdown.get_width() * pulse), int(countdown.get_height() * pulse)),
            )
            glow = pygame.Surface((110, 75), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (*DANGER, 42 if remaining <= 5 else 24), glow.get_rect())
            self.screen.blit(glow, glow.get_rect(center=(WIDTH // 2, 103)))
            self.screen.blit(countdown, countdown.get_rect(center=(WIDTH // 2, 103)))

    def draw_board(self) -> None:
        outline = board_outline_points()
        pygame.draw.polygon(self.screen, PANEL, outline)

        for cell in ALL_CELLS:
            owner = self.cell_owner(cell)
            x, y = cell_center(cell)
            rect = pygame.Rect(x - CELL_SIZE // 2 + 1, y - CELL_SIZE // 2 + 1, CELL_SIZE - 2, CELL_SIZE - 2)
            if not owner:
                pygame.draw.rect(self.screen, NEUTRAL_CELL, rect, border_radius=3)
                pygame.draw.rect(self.screen, GRID, rect, 1, border_radius=3)
                continue
            amount = 0.68 if owner.alive else 0.28
            fill = mix(NEUTRAL_CELL, owner.color, amount)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            pygame.draw.rect(self.screen, GRID, rect, 1, border_radius=3)
            if owner.alive:
                shine = mix(fill, (255, 255, 255), 0.55)
                pygame.draw.circle(self.screen, shine, (x - 3, y - 3), 2)

        pygame.draw.polygon(self.screen, (86, 101, 142), outline, 2)

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
        headers = ["SNAKE / STRATEGY", "CELLS", "PAINT", "STATUS"]
        xs = [22, 198, 240, 282]
        for header, x in zip(headers, xs):
            self.screen.blit(self.font_small.render(header, True, MUTED), (x, SCORE_TOP + 8))
        for index, snake in enumerate(self.snakes):
            y = SCORE_TOP + 22 + index * 30
            pygame.draw.circle(self.screen, snake.color, (24, y + 5), 4)
            status = snake.status()
            status_color = snake.color
            texts = [
                (snake.name, 33, snake.color),
                (str(snake.owned_cells), 205, WHITE),
                (str(snake.captures), 246, WHITE),
                (status, 282, status_color),
            ]
            for text, x, color in texts:
                self.screen.blit(self.font_ui.render(text, True, color), (x, y))
            self.screen.blit(self.font_ui.render(snake.strategy.value, True, WHITE), (33, y + 13))

    def draw_winner_screen(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((3, 5, 13, 220))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(35, 205, WIDTH - 70, 210)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=4)
        for width, alpha in ((14, 35), (7, 70), (2, 255)):
            glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*self.winner.color, alpha), panel.inflate(width, width), width, border_radius=10)
            self.screen.blit(glow, (0, 0))
        winner_text = self.font_winner.render("WINNER", True, self.winner.color)
        name_text = self.font_title.render(self.winner.name, True, WHITE)
        strat_text = self.font_subtitle.render(self.winner.strategy.value, True, MUTED)
        score_text = self.font_subtitle.render(f"Cells {self.winner.owned_cells}  Paint {self.winner.captures}", True, WHITE)
        reason_text = self.font_small.render(self.finish_reason, True, MUTED)
        restart_text = self.font_ui.render("PRESS R TO REPLAY", True, MUTED)
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
    parser.add_argument(
        "--audio-source",
        default="auto",
        help="system-audio loopback device for recording, default auto",
    )
    parser.add_argument(
        "--audio-backend",
        choices=("dshow", "wasapi"),
        default="wasapi",
        help="ffmpeg audio capture backend, default wasapi loopback",
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
        audio_source=args.audio_source,
        audio_backend=args.audio_backend,
    ).run()
