import argparse
from array import array
import ctypes
import json
import math
import os
import random
import sys
import wave
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ai_light_snake_capture.recording import FrameRecorder, RecordingUnavailable

import pygame


# ---------------------------
# Quick tuning constants
# ---------------------------
WIDTH, HEIGHT = 540, 960
WINDOW_TITLE = "AI Light Snake Capture"
FPS = 60
CELL_SIZE = 10
GRID_COLS = 48
GRID_ROWS = 45
BOARD_LEFT = (WIDTH - GRID_COLS * CELL_SIZE) // 2
BOARD_TOP = 112
BOARD_WIDTH = GRID_COLS * CELL_SIZE
BOARD_HEIGHT = GRID_ROWS * CELL_SIZE
TERRITORY_BAR_TOP = BOARD_TOP + BOARD_HEIGHT + 10
SCORE_TOP = BOARD_TOP + BOARD_HEIGHT + 70
MOVE_TICKS_PER_SECOND = 6.215625
MATCH_TIME_LIMIT_SECONDS = 60
WINDOW_RECORD_FPS = FPS
WINDOW_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
RECORDING_END_DELAY_SECONDS = 3.0
SAFE_HOME_MOVE_LIMIT = 1
BONUS_DETECTION_DISTANCE = GRID_COLS + GRID_ROWS
BONUS_BIG_SNAKE_MIN_DISTANCE = 10
BONUS_REACHABILITY_CHECK_LIMIT = 70
BONUS_RESPAWN_SECONDS = (7.0, 13.0)
ERASER_BALL_RADIUS = 11
ERASER_BALL_SPEED = 70.0
ERASER_BOUNCE_SPEED_MULTIPLIER = 1.1
ERASER_WALL_HOLE_RADIUS = ERASER_BALL_RADIUS + 6
ERASER_EVADE_SECONDS = 2.8
ERASER_EVADE_RADIUS = 56.0
BIG_CAPTURE_MESSAGE_COOLDOWN = 3.0

BG = (8, 10, 18)
PANEL = (18, 22, 35)
GRID = (38, 45, 65)
WHITE = (245, 247, 255)
MUTED = (170, 178, 200)
DANGER = (255, 70, 90)
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


def make_cartoon_sound(
    frequency: float,
    duration: float,
    volume: float,
    tone: str,
    time_scale: float = 1.0,
) -> pygame.mixer.Sound:
    sample_rate = 44100
    samples = array("h")
    count = int(sample_rate * duration * time_scale)
    rng = random.Random(int(frequency * 71 + duration * 10000))
    phase = 0.0
    for index in range(count):
        progress = index / max(1, count - 1)
        logical_progress = min(1.0, progress)
        if tone == "boing":
            pitch = frequency * (1.0 + 1.15 * math.exp(-7.0 * logical_progress) * math.sin(math.tau * 4.0 * logical_progress))
            envelope = math.sin(math.pi * logical_progress) ** 0.28 * (1.0 - logical_progress) ** 0.7
            wobble = math.sin(math.tau * 7.0 * logical_progress) * 0.22
            wave = math.sin(phase) + wobble * math.sin(phase * 0.5)
        elif tone == "pop":
            pitch = frequency * (2.2 - 1.35 * logical_progress)
            envelope = math.exp(-9.0 * logical_progress)
            wave = math.sin(phase) + rng.uniform(-0.5, 0.5) * (1.0 - logical_progress)
        elif tone == "sparkle":
            pitch = frequency * (1.0 + logical_progress * 1.8)
            envelope = math.sin(math.pi * logical_progress) ** 0.2 * (1.0 - logical_progress) ** 0.55
            wave = math.sin(phase) + 0.42 * math.sin(phase * 2.01) + 0.2 * math.sin(phase * 4.03)
        elif tone == "splat":
            pitch = frequency * (1.7 - 1.25 * logical_progress)
            envelope = math.exp(-5.0 * logical_progress)
            wave = math.sin(phase) * 0.55 + rng.uniform(-1.0, 1.0) * 0.65
        elif tone == "bonk":
            pitch = frequency * (1.0 - logical_progress * 0.42)
            envelope = math.exp(-6.5 * logical_progress)
            wave = math.sin(phase) + 0.65 * math.sin(phase * 0.51) + 0.25 * math.sin(phase * 2.03)
        else:
            pitch = frequency * (0.75 + logical_progress * 1.5)
            envelope = math.sin(math.pi * logical_progress) ** 0.35 * (1.0 - logical_progress) ** 0.3
            wave = math.sin(phase) + 0.28 * math.sin(phase * 2.0)
        phase += math.tau * pitch / sample_rate
        sample = math.tanh(wave * 1.25) * envelope * volume
        samples.append(int(max(-1.0, min(1.0, sample)) * 32767))
    return pygame.mixer.Sound(buffer=samples.tobytes())


def make_ambient_melody(time_scale: float = 1.0) -> pygame.mixer.Sound:
    sample_rate = 44100
    beat = 0.32 * time_scale
    notes = [392.00, 523.25, 659.25, 523.25, 440.00, 587.33, 698.46, 587.33,
             392.00, 493.88, 659.25, 493.88, 349.23, 440.00, 587.33, 440.00]
    bass = [196.00, 196.00, 220.00, 220.00, 174.61, 174.61, 196.00, 196.00]
    total = int(sample_rate * beat * len(notes))
    samples = array("h")
    for index in range(total):
        time = index / sample_rate
        note_index = min(len(notes) - 1, int(time / beat))
        local = (time % beat) / beat
        note = notes[note_index]
        bass_note = bass[(note_index // 2) % len(bass)]
        pluck = math.exp(-6.0 * local)
        bounce = 1.0 + 0.035 * math.sin(math.tau * 5.0 * local)
        wave = math.sin(math.tau * note * bounce * time) * pluck * 0.095
        wave += math.sin(math.tau * note * 2.002 * time) * pluck * 0.028
        wave += math.sin(math.tau * bass_note * time) * math.exp(-4.0 * local) * 0.038
        samples.append(int(max(-1.0, min(1.0, wave)) * 32767))
    return pygame.mixer.Sound(buffer=samples.tobytes())


class SoundBank:
    def __init__(self, time_scale: float = 1.0) -> None:
        self.enabled = False
        self.recorder: Optional[FrameRecorder] = None
        self.sound_names: Dict[int, str] = {}
        self.raw_sounds: Dict[str, bytes] = {}
        self.music_raw = b""
        self.music_volume = 0.48
        self.music_started_at: Optional[float] = None
        self.countdown_channel: Optional[pygame.mixer.Channel] = None
        self.music_channel: Optional[pygame.mixer.Channel] = None
        self.death_channel: Optional[pygame.mixer.Channel] = None
        self.area_capture_channel: Optional[pygame.mixer.Channel] = None
        self.notification_channel: Optional[pygame.mixer.Channel] = None
        self.music = None
        self.notification = None
        self.start = self.big_capture = self.bonus = self.erase = self.death = self.finish = None
        self.area_capture = None
        self.countdown = self.countdown_final = None
        self.capture: List[pygame.mixer.Sound] = []
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(5)
            self.countdown_channel = pygame.mixer.Channel(0)
            self.music_channel = pygame.mixer.Channel(1)
            self.death_channel = pygame.mixer.Channel(2)
            self.area_capture_channel = pygame.mixer.Channel(3)
            self.notification_channel = pygame.mixer.Channel(4)
            self.start = make_cartoon_sound(330, .48, .34, "whistle", time_scale)
            self.capture = [make_cartoon_sound(pitch, .11, .23, "pop", time_scale) for pitch in (330, 370, 415, 466)]
            self.big_capture = make_cartoon_sound(280, .48, .38, "boing", time_scale)
            self.area_capture = make_cartoon_sound(390, .52, .42, "boing", time_scale)
            self.notification = make_cartoon_sound(620, .25, .38, "sparkle", time_scale)
            self.bonus = make_cartoon_sound(520, .62, .42, "sparkle", time_scale)
            self.erase = make_cartoon_sound(150, .24, .38, "splat", time_scale)
            self.death = make_cartoon_sound(115, .88, .92, "bonk", time_scale)
            self.countdown = make_cartoon_sound(420, .18, .42, "pop", time_scale)
            self.countdown_final = make_cartoon_sound(570, .32, .52, "boing", time_scale)
            self.finish = make_cartoon_sound(350, .95, .44, "whistle", time_scale)
            self.music = make_ambient_melody(time_scale)
            named_sounds = {
                "start": self.start,
                "big_capture": self.big_capture,
                "area_capture": self.area_capture,
                "notification": self.notification,
                "bonus": self.bonus,
                "erase": self.erase,
                "death": self.death,
                "countdown": self.countdown,
                "countdown_final": self.countdown_final,
                "finish": self.finish,
            }
            named_sounds.update({f"capture_{index}": sound for index, sound in enumerate(self.capture)})
            self.sound_names = {id(sound): name for name, sound in named_sounds.items()}
            self.raw_sounds = {name: sound.get_raw() for name, sound in named_sounds.items()}
            self.music_raw = self.music.get_raw()
            self.music_channel.set_volume(self.music_volume)
            self.music_channel.play(self.music, loops=-1)
            self.music_started_at = pygame.time.get_ticks() / 1000.0
            self.enabled = True
        except pygame.error:
            pass

    def attach_recorder(self, recorder: Optional[FrameRecorder]) -> None:
        self.recorder = recorder

    def music_position(self) -> float:
        if self.music_started_at is None:
            return 0.0
        return max(0.0, pygame.time.get_ticks() / 1000.0 - self.music_started_at)

    def record(self, sound: Optional[pygame.mixer.Sound]) -> None:
        if self.recorder and sound:
            name = self.sound_names.get(id(sound))
            if name:
                self.recorder.record_sound(name)

    def play(self, sound: pygame.mixer.Sound) -> None:
        self.record(sound)
        if self.enabled and sound:
            sound.play()

    def play_countdown(self, final: bool = False) -> None:
        sound = self.countdown_final if final else self.countdown
        self.record(sound)
        if self.enabled and sound:
            if self.countdown_channel:
                self.countdown_channel.play(sound)
            else:
                sound.play()

    def play_death(self) -> None:
        self.record(self.death)
        if self.enabled and self.death:
            if self.music_channel:
                self.music_channel.set_volume(0.18)
            if self.death_channel:
                self.death_channel.set_volume(1.0)
                self.death_channel.play(self.death)
            else:
                self.death.play()

    def play_area_capture(self) -> None:
        self.record(self.area_capture)
        if self.enabled and self.area_capture:
            if self.area_capture_channel:
                self.area_capture_channel.play(self.area_capture)
            else:
                self.area_capture.play()

    def play_notification(self) -> None:
        self.record(self.notification)
        if self.enabled and self.notification:
            if self.notification_channel:
                self.notification_channel.set_volume(1.0)
                self.notification_channel.play(self.notification)
            else:
                self.notification.play()

    def update(self) -> None:
        if self.enabled and self.music_channel and self.death_channel and not self.death_channel.get_busy():
            self.music_channel.set_volume(self.music_volume)

    def write_recording_audio(
        self,
        path: str,
        video_frames: int,
        fps: int,
        music_offset: float,
        sound_events: List[Tuple[int, str]],
    ) -> None:
        sample_rate = 44100
        total_samples = round(video_frames * sample_rate / fps)
        music = array("h")
        music.frombytes(self.music_raw)
        music_offset_samples = round(music_offset * sample_rate)
        mixed = array(
            "h",
            (
                int(music[(music_offset_samples + index) % len(music)] * self.music_volume)
                if music else 0
                for index in range(total_samples)
            ),
        )
        decoded_sounds: Dict[str, array] = {}
        for name, raw in self.raw_sounds.items():
            samples = array("h")
            samples.frombytes(raw)
            decoded_sounds[name] = samples
        for video_frame, name in sound_events:
            source = decoded_sounds.get(name)
            if source is None:
                continue
            start = round(video_frame * sample_rate / fps)
            count = min(len(source), total_samples - start)
            for index in range(max(0, count)):
                target = start + index
                mixed[target] = max(-32768, min(32767, mixed[target] + source[index]))
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(mixed.tobytes())


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


BOARD_OUTLINE: List[Tuple[int, int]] = regular_hex_points(pad=1)
ALL_CELLS: List[Cell] = playable_cells()
PLAYABLE_CELLS: Set[Cell] = set(ALL_CELLS)
CELL_CENTERS: Dict[Cell, Tuple[int, int]] = {
    cell: (
        BOARD_LEFT + cell[0] * CELL_SIZE + CELL_SIZE // 2,
        BOARD_TOP + cell[1] * CELL_SIZE + CELL_SIZE // 2,
    )
    for cell in ALL_CELLS
}
CELL_RECTS: Dict[Cell, pygame.Rect] = {
    cell: pygame.Rect(
        center[0] - CELL_SIZE // 2 + 1,
        center[1] - CELL_SIZE // 2 + 1,
        CELL_SIZE - 2,
        CELL_SIZE - 2,
    )
    for cell, center in CELL_CENTERS.items()
}
CELL_FILL_RECTS: Dict[Cell, pygame.Rect] = {cell: rect.inflate(-2, -2) for cell, rect in CELL_RECTS.items()}
NEAR_CELLS_CACHE: Dict[Tuple[Cell, int], Tuple[Cell, ...]] = {}


def cells_near(cell: Cell, radius: int) -> Tuple[Cell, ...]:
    key = (cell, radius)
    cached = NEAR_CELLS_CACHE.get(key)
    if cached is not None:
        return cached
    cx, cy = cell
    result = tuple(
        candidate
        for candidate in ALL_CELLS
        if abs(candidate[0] - cx) + abs(candidate[1] - cy) <= radius
    )
    NEAR_CELLS_CACHE[key] = result
    return result


class StrategyKind(Enum):
    BUILDER = "Runs clean circles"
    RAIDER = "Follows the eraser"
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
        fade = max(0.0, min(1.0, self.life / self.max_life))
        pygame.draw.circle(surface, mix(BG, self.color, fade), (int(self.x), int(self.y)), max(1, int(self.radius)))


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

        rect = pygame.Rect(0, 0, CELL_SIZE + 4, CELL_SIZE + 4)
        rect.center = (x, y)
        pygame.draw.rect(surface, (255, 239, 179), rect, border_radius=4)
        pygame.draw.rect(surface, BONUS_COLOR, rect, 2, border_radius=4)
        pygame.draw.line(surface, BONUS_COLOR, (x - 5, y), (x + 5, y), 3)
        pygame.draw.line(surface, BONUS_COLOR, (x, y - 5), (x, y + 5), 3)


@dataclass
class EraserBall:
    x: float
    y: float
    vx: float
    vy: float
    radius: int = ERASER_BALL_RADIUS
    escaping: bool = False

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surface: pygame.Surface) -> None:
        glow_radius = self.radius + 7
        glow = pygame.Surface((glow_radius * 4, glow_radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*ERASER_COLOR, 34), (glow.get_width() // 2, glow.get_height() // 2), glow_radius * 2)
        surface.blit(glow, (self.x - glow.get_width() / 2, self.y - glow.get_height() / 2))

        pygame.draw.circle(surface, (248, 250, 247), (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, ERASER_COLOR, (int(self.x), int(self.y)), self.radius, 3)
        pygame.draw.circle(surface, (177, 188, 190), (int(self.x - 4), int(self.y - 4)), max(3, self.radius // 3))


@dataclass
class StatusMessage:
    snake_name: str
    text: str
    color: Color
    created_at: float


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
    last_capture_message_at: float = -99.0

    @property
    def protected(self) -> bool:
        return self.alive and self.head in self.territory

    @property
    def owned_cells(self) -> int:
        return len(self.territory) if self.alive else max(self.final_cells, len(self.territory))

    def status(self) -> str:
        if not self.alive:
            return "dead"
        if self.head_size > 1:
            return "big"
        return "small"

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
            fade = max(0.0, min(1.0, life / 0.30))
            pygame.draw.circle(surface, mix(BG, self.color, fade * 0.45), (int(x), int(y)), CELL_SIZE // 2)

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
            surface.blit(label, label.get_rect(center=(x, y - 20)))

        if self.death_flash > 0:
            flash_radius = int(27 * self.death_flash)
            pygame.draw.circle(surface, (*DANGER, 90), (x, y), flash_radius, 2)


def cell_center(cell: Cell) -> Tuple[int, int]:
    return CELL_CENTERS[cell]


def add_vec(a: Cell, b: Vec) -> Cell:
    return a[0] + b[0], a[1] + b[1]


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def opposite(a: Vec, b: Vec) -> bool:
    return a[0] == -b[0] and a[1] == -b[1]


def mix(a: Color, b: Color, amount: float) -> Color:
    return tuple(int(a[i] * (1.0 - amount) + b[i] * amount) for i in range(3))


def board_outline_points() -> List[Tuple[int, int]]:
    return BOARD_OUTLINE


class Game:
    def __init__(
        self,
        record_window: bool = True,
        window_record_fps: int = WINDOW_RECORD_FPS,
        window_record_dir: str = WINDOW_RECORDINGS_DIR,
        time_limit: int = MATCH_TIME_LIMIT_SECONDS,
    ) -> None:
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.screen.fill(BG)
        pygame.display.flip()
        self.clock = pygame.time.Clock()
        self.font_tiny = pygame.font.SysFont("arial", 11, bold=True)
        self.font_small = pygame.font.SysFont("arial", 15, bold=True)
        self.font_ui = pygame.font.SysFont("arial", 19, bold=True)
        self.font_title = pygame.font.SysFont("arial", 40, bold=True)
        self.font_subtitle = pygame.font.SysFont("arial", 22, bold=True)
        self.font_winner = pygame.font.SysFont("arial", 57, bold=True)
        self.sounds = SoundBank()
        self.last_capture_sound = -1.0
        self.last_erase_sound = -1.0
        self.last_countdown_second: Optional[int] = None
        self.gameplay_log_file = None
        self.pending_log_events: List[dict] = []
        self.last_snapshot_second = -1
        self.snakes: List[LightSnake] = []
        self.scoreboard_order: List[LightSnake] = []
        self.last_scoreboard_second = -1
        self.particles: List[Particle] = []
        self.status_messages: List[StatusMessage] = []
        self.bonus: Optional[Bonus] = None
        self.bonus_timer = 0.0
        self.initial_bonus_race = False
        self.eraser_ball: Optional[EraserBall] = None
        self.wall_holes: List[Tuple[float, float]] = []
        self.paused = False
        self.game_over = False
        self.winner: Optional[LightSnake] = None
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.recorder: Optional[FrameRecorder] = None
        self.region_fill_timer = 0.0
        self.max_match_seconds = max(1, time_limit)
        self.owner_by_cell: Dict[Cell, LightSnake] = {}
        self._neutral_cells_cache: Optional[Set[Cell]] = None
        self.board_base = self.build_board_base()
        self.sprinter_waypoints = [
            self.nearest_playable_cell((4, 5)),
            self.nearest_playable_cell((GRID_COLS - 5, 9)),
            self.nearest_playable_cell((4, 14)),
            self.nearest_playable_cell((GRID_COLS - 5, 19)),
            self.nearest_playable_cell((4, GRID_ROWS - 5)),
        ]
        if record_window:
            try:
                self.recorder = FrameRecorder((WIDTH, HEIGHT), window_record_fps, self.sounds, window_record_dir)
                self.sounds.attach_recorder(self.recorder)
                print(f"Recording to {self.recorder.output_path}")
            except RecordingUnavailable as error:
                print(f"Recording disabled: {error}", file=sys.stderr)
        self.restart()

    def restart(self) -> None:
        self.close_gameplay_log()
        self.snakes = []
        self.owner_by_cell = {}
        self._neutral_cells_cache = None
        self.particles = []
        self.status_messages = []
        self.bonus = None
        self.bonus_timer = 5.0
        self.initial_bonus_race = False
        self.eraser_ball = self.create_eraser_ball()
        self.wall_holes = []
        self.paused = False
        self.game_over = False
        self.winner = None
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.region_fill_timer = 0.0
        self.last_countdown_second = None
        self.pending_log_events = []
        self.last_snapshot_second = -1
        self.create_snakes()
        self.rebuild_owner_cache()
        self.scoreboard_order = list(self.snakes)
        self.last_scoreboard_second = -1
        self.log_event("match_start", time_limit=self.max_match_seconds)
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
            ("MAX", YELLOW, StrategyKind.BUILDER, (43, 20), (-1, 0), 1.00, {(43, 20)}, [(-1, 0), (0, 1), (1, 0), (0, -1)]),
            ("LEO", GREEN, StrategyKind.GUARDIAN, (34, 37), (-1, 0), 0.96, {(34, 37)}, [(-1, 0), (0, -1), (1, 0), (0, 1)]),
            ("MIA", CORAL, StrategyKind.RAIDER, (13, 37), (1, 0), 0.98, {(13, 37)}, [(1, 0), (0, -1), (-1, 0), (0, 1)]),
            ("ZOE", BLUE, StrategyKind.SPRINTER, (4, 20), (1, 0), 1.06, {(4, 20)}, [(1, 0), (0, 1), (-1, 0), (0, -1)]),
            ("NOA", PURPLE, StrategyKind.THIEF, (13, 3), (1, 0), 1.07, {(13, 3)}, [(1, 0), (0, 1), (-1, 0), (0, -1)]),
            ("SAM", TEAL, StrategyKind.SCOUT, (34, 3), (-1, 0), 1.12, {(34, 3)}, [(-1, 0), (0, 1), (1, 0), (0, -1)]),
        ]
        for name, color, strategy, start, direction, speed, territory, opening_steps in configs:
            self.snakes.append(
                LightSnake(name, color, strategy, start, direction, speed, set(territory), opening_steps=list(opening_steps))
            )

    def rebuild_owner_cache(self) -> None:
        self.owner_by_cell.clear()
        for snake in self.snakes:
            for cell in snake.territory:
                self.owner_by_cell[cell] = snake
        self._neutral_cells_cache = None

    def invalidate_cell_cache(self) -> None:
        self._neutral_cells_cache = None

    def build_board_base(self) -> pygame.Surface:
        surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.polygon(surface, PANEL, BOARD_OUTLINE)
        for cell in ALL_CELLS:
            rect = CELL_RECTS[cell]
            pygame.draw.rect(surface, NEUTRAL_CELL, rect, border_radius=4)
            pygame.draw.rect(surface, GRID, rect, 1, border_radius=4)
        return surface

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
        head_size = snake.head_size if size is None else size
        hx, hy = head

        for dx in range(head_size):
            for dy in range(head_size):
                cell = (hx + dx, hy + dy)
                if cell not in PLAYABLE_CELLS:
                    return False
                owner = self.owner_by_cell.get(cell)
                if owner is not None and owner is not snake:
                    return False

        for other in self.snakes:
            if other is snake or not other.alive:
                continue
            ox, oy = other.head
            if hx < ox + other.head_size and hx + head_size > ox and hy < oy + other.head_size and hy + head_size > oy:
                return False
        return True

    def cell_owner(self, cell: Cell) -> Optional[LightSnake]:
        return self.owner_by_cell.get(cell)

    def is_enemy_territory(self, snake: LightSnake, cell: Cell) -> bool:
        owner = self.owner_by_cell.get(cell)
        return owner is not None and owner is not snake

    def clear_cells(self, cells: Set[Cell]) -> None:
        if not cells:
            return
        for cell in cells:
            owner = self.owner_by_cell.pop(cell, None)
            if owner is not None:
                owner.territory.discard(cell)
        self.invalidate_cell_cache()

    def cells_touched_by_ball(self, ball: EraserBall) -> Set[Cell]:
        touch_radius = ball.radius + CELL_SIZE * 0.72
        radius_sq = touch_radius * touch_radius
        min_x = max(0, int((ball.x - touch_radius - BOARD_LEFT) // CELL_SIZE) - 1)
        max_x = min(GRID_COLS - 1, int((ball.x + touch_radius - BOARD_LEFT) // CELL_SIZE) + 1)
        min_y = max(0, int((ball.y - touch_radius - BOARD_TOP) // CELL_SIZE) - 1)
        max_y = min(GRID_ROWS - 1, int((ball.y + touch_radius - BOARD_TOP) // CELL_SIZE) + 1)
        touched: Set[Cell] = set()
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                cell = (x, y)
                center = CELL_CENTERS.get(cell)
                if center is None:
                    continue
                dx = center[0] - ball.x
                dy = center[1] - ball.y
                if dx * dx + dy * dy <= radius_sq:
                    touched.add(cell)
        return touched

    def nearest_wall_hit(
        self,
        point: Tuple[float, float],
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        px, py = point
        polygon = board_outline_points()
        best_distance = float("inf")
        best_normal = (1.0, 0.0)
        best_closest = point

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
                best_closest = closest
                if distance > 0:
                    best_normal = (dx / distance, dy / distance)

        return best_normal, best_closest

    def wall_has_hole_at(self, point: Tuple[float, float]) -> bool:
        return any(math.dist(point, hole) <= ERASER_WALL_HOLE_RADIUS for hole in self.wall_holes)

    def add_wall_hole(self, point: Tuple[float, float]) -> None:
        if not self.wall_has_hole_at(point):
            self.wall_holes.append(point)

    def update_eraser_ball(self, dt: float) -> None:
        if not self.eraser_ball:
            return

        ball = self.eraser_ball
        if ball.escaping:
            ball.update(dt)
            margin = ball.radius + ERASER_WALL_HOLE_RADIUS
            if (
                ball.x < -margin
                or ball.x > WIDTH + margin
                or ball.y < -margin
                or ball.y > HEIGHT + margin
            ):
                self.log_event("eraser_ball_escaped")
                self.eraser_ball = None
            return

        previous = (ball.x, ball.y)
        ball.update(dt)
        polygon = board_outline_points()

        if not point_in_polygon((ball.x, ball.y), polygon):
            normal, wall_hit = self.nearest_wall_hit((ball.x, ball.y))
            if self.wall_has_hole_at(wall_hit):
                ball.escaping = True
                self.log_event("eraser_ball_entered_hole", x=round(wall_hit[0], 2), y=round(wall_hit[1], 2))
                return
            self.add_wall_hole(wall_hit)
            self.log_event("wall_hole_created", x=round(wall_hit[0], 2), y=round(wall_hit[1], 2))
            dot = ball.vx * normal[0] + ball.vy * normal[1]
            ball.vx -= 2 * dot * normal[0]
            ball.vy -= 2 * dot * normal[1]
            ball.vx *= ERASER_BOUNCE_SPEED_MULTIPLIER
            ball.vy *= ERASER_BOUNCE_SPEED_MULTIPLIER
            ball.x, ball.y = previous
            ball.update(dt)

            if not point_in_polygon((ball.x, ball.y), polygon):
                center = (BOARD_LEFT + BOARD_WIDTH / 2, BOARD_TOP + BOARD_HEIGHT / 2)
                ball.x = previous[0] * 0.7 + center[0] * 0.3
                ball.y = previous[1] * 0.7 + center[1] * 0.3

        cleared = self.cells_touched_by_ball(ball)
        for snake in self.snakes:
            if not snake.alive:
                continue
            head_x, head_y = snake.head_center()
            head_radius = CELL_SIZE * (0.72 if snake.head_size == 1 else 1.15)
            if math.dist((head_x, head_y), (ball.x, ball.y)) <= ball.radius + head_radius:
                self.kill_snake(snake, "ERASED")

        owned_cleared = cleared.intersection(self.owner_by_cell)
        if owned_cleared:
            self.clear_cells(owned_cleared)
            if self.match_time - self.last_erase_sound > 0.18:
                self.sounds.play(self.sounds.erase)
                self.last_erase_sound = self.match_time
            if random.random() < 0.45:
                self.emit_eraser_particles(random.choice(tuple(owned_cleared)))

    def neutral_cells(self) -> Set[Cell]:
        if self._neutral_cells_cache is None:
            self._neutral_cells_cache = PLAYABLE_CELLS.difference(self.owner_by_cell)
        return self._neutral_cells_cache

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
            if any(part in self.owner_by_cell for part in footprint):
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
        self.log_event("bonus_spawned", cell=self.bonus.cell)

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
        return {cell for cell, owner in self.owner_by_cell.items() if owner is not snake}

    def neutral_cells_near_enemy(self, snake: LightSnake) -> Set[Cell]:
        neutral = self.neutral_cells()
        result: Set[Cell] = set()
        for enemy_cell in self.enemy_territory_cells(snake):
            for direction in DIRS:
                cell = add_vec(enemy_cell, direction)
                if cell in neutral:
                    result.add(cell)
        return result

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
        for other in self.snakes:
            if other is not snake and other.alive:
                blocked.update(self.footprint_for(other))

        if snake.head_size == 1:
            def can_step(cell: Cell) -> bool:
                return cell in PLAYABLE_CELLS and cell not in blocked
        else:
            def can_step(cell: Cell) -> bool:
                return self.can_occupy(snake, cell)

        seen = {snake.head}
        queue: List[Tuple[Cell, Vec]] = []
        nearest_target = min(targets, key=lambda cell: manhattan(snake.head, cell))

        first_steps = self.move_options(snake)
        first_steps.sort(key=lambda d: manhattan(add_vec(snake.head, d), nearest_target))
        for direction in first_steps:
            nxt = add_vec(snake.head, direction)
            if nxt in seen or not can_step(nxt):
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
                if nxt in seen or not can_step(nxt):
                    continue
                seen.add(nxt)
                queue.append((nxt, first_direction))
        return None

    def path_to_cell(self, snake: LightSnake, target: Cell) -> Optional[Vec]:
        return self.path_to_cells(snake, {target})

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
            if nxt not in snake.territory:
                value -= 1.5
            return value

        return min(options, key=score)

    def choose_direction(self, snake: LightSnake) -> Vec:
        evade_step = self.eraser_evade_direction(snake)
        if evade_step:
            return evade_step

        bonus_step = self.bonus_direction(snake)
        if bonus_step:
            return bonus_step

        if snake.strategy == StrategyKind.RAIDER:
            follow_step = self.pattern_direction(snake)
            if follow_step:
                return follow_step

        if snake.opening_steps:
            direction = snake.opening_steps.pop(0)
            nxt = add_vec(snake.head, direction)
            if self.can_occupy(snake, nxt):
                return direction

        expansion_step = self.fresh_cell_direction(snake)
        if expansion_step:
            return expansion_step

        pattern_step = self.pattern_direction(snake)
        if pattern_step:
            return pattern_step

        forced_exit = self.force_exit_direction(snake)
        if forced_exit:
            return forced_exit

        if snake.strategy == StrategyKind.SCOUT:
            fresh_step = self.fresh_cell_direction(snake)
            if fresh_step:
                return fresh_step
        return self.inside_direction(snake)

    def eraser_evade_direction(self, snake: LightSnake) -> Optional[Vec]:
        ball = self.eraser_ball
        if not ball:
            return None

        head_x, head_y = snake.head_center()
        relative_x = head_x - ball.x
        relative_y = head_y - ball.y
        speed_sq = ball.vx * ball.vx + ball.vy * ball.vy
        if speed_sq <= 0:
            return None

        time_to_closest = (relative_x * ball.vx + relative_y * ball.vy) / speed_sq
        if time_to_closest <= 0 or time_to_closest > ERASER_EVADE_SECONDS:
            return None

        closest_x = ball.x + ball.vx * time_to_closest
        closest_y = ball.y + ball.vy * time_to_closest
        if math.dist((head_x, head_y), (closest_x, closest_y)) > ERASER_EVADE_RADIUS:
            return None

        options = self.move_options(snake, allow_reverse=True)
        if not options:
            return None

        look_ahead = min(ERASER_EVADE_SECONDS, time_to_closest + 0.65)
        future_ball = (ball.x + ball.vx * look_ahead, ball.y + ball.vy * look_ahead)

        def safety(direction: Vec) -> float:
            nxt = add_vec(snake.head, direction)
            nxt_x, nxt_y = cell_center(nxt)
            distance_now = math.dist((nxt_x, nxt_y), (ball.x, ball.y))
            distance_future = math.dist((nxt_x, nxt_y), future_ball)
            cross_track = math.dist((nxt_x, nxt_y), (closest_x, closest_y))
            return distance_now + distance_future * 1.6 + cross_track * 2.2 - self.head_pressure_at(snake, nxt) * 4

        return max(options, key=safety)

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
            return score

        def toward(target: Cell, direction: Vec) -> float:
            return base_score(direction) - manhattan(add_vec(snake.head, direction), target) * 1.5

        def follow_waypoints(points: List[Cell], reach: int = 1, momentum: float = 1.0) -> Vec:
            target = points[snake.pattern_index % len(points)]
            radius = reach + 2
            target_region = {cell for cell in cells_near(target, radius) if not self.is_enemy_territory(snake, cell)}
            if snake.head in target_region:
                snake.pattern_index = (snake.pattern_index + 1) % len(points)
                target = points[snake.pattern_index]
                target_region = {cell for cell in cells_near(target, radius) if not self.is_enemy_territory(snake, cell)}
            path_step = self.path_to_cells(snake, target_region)
            if path_step:
                return path_step
            return max(
                options,
                key=lambda direction: toward(target, direction) + (momentum if direction == snake.direction else 0.0),
            )

        if snake.strategy == StrategyKind.BUILDER:
            def circle_score(direction: Vec) -> float:
                nxt = add_vec(snake.head, direction)
                dx, dy = nxt[0] - center[0], nxt[1] - center[1]
                radius = max(0.1, math.hypot(dx, dy))
                tangent = (-dy / radius, dx / radius)
                flow = direction[0] * tangent[0] + direction[1] * tangent[1]
                return base_score(direction) + flow * 7.0 - abs(radius - 11.5) * 1.1

            return max(options, key=circle_score)

        if snake.strategy == StrategyKind.GUARDIAN:
            vertical = -1 if (snake.pattern_step // 16) % 2 == 0 else 1
            return max(
                options,
                key=lambda direction: base_score(direction)
                - add_vec(snake.head, direction)[0] * 5.0
                + direction[1] * vertical * 3.0,
            )

        if snake.strategy == StrategyKind.RAIDER:
            ball = self.eraser_ball
            if not ball:
                return max(options, key=base_score)

            speed = max(0.1, math.hypot(ball.vx, ball.vy))
            unit_x, unit_y = ball.vx / speed, ball.vy / speed
            follow_distance = CELL_SIZE * 4.5
            target_point = (
                ball.x - unit_x * follow_distance,
                ball.y - unit_y * follow_distance,
            )
            target = min(
                (
                    cell for cell in ALL_CELLS
                    if not self.is_enemy_territory(snake, cell)
                ),
                key=lambda cell: math.dist(cell_center(cell), target_point),
            )
            path_step = self.path_to_cell(snake, target)

            def follow_score(direction: Vec) -> float:
                nxt = add_vec(snake.head, direction)
                nxt_center = cell_center(nxt)
                distance_to_ball = math.dist(nxt_center, (ball.x, ball.y))
                distance_to_target = math.dist(nxt_center, target_point)

                relative_x = nxt_center[0] - ball.x
                relative_y = nxt_center[1] - ball.y
                time_to_closest = max(
                    0.0,
                    min(ERASER_EVADE_SECONDS, (relative_x * ball.vx + relative_y * ball.vy) / (speed * speed)),
                )
                closest_ball = (
                    ball.x + ball.vx * time_to_closest,
                    ball.y + ball.vy * time_to_closest,
                )
                flight_path_clearance = math.dist(nxt_center, closest_ball)
                danger_distance = ball.radius + CELL_SIZE * (3.0 if snake.head_size == 1 else 4.0)

                score = base_score(direction) - distance_to_target * 0.13
                score += min(distance_to_ball, CELL_SIZE * 8) * 0.03
                if flight_path_clearance < danger_distance:
                    score -= (danger_distance - flight_path_clearance) * 1.8
                if direction == path_step:
                    score += 4.0
                return score

            return max(options, key=follow_score)

        if snake.strategy == StrategyKind.SPRINTER:
            return follow_waypoints(self.sprinter_waypoints, reach=2, momentum=2.2)

        if snake.strategy == StrategyKind.THIEF:
            target_radius = max(3.0, 13.0 - snake.pattern_step * 0.07)

            def spiral_score(direction: Vec) -> float:
                nxt = add_vec(snake.head, direction)
                dx, dy = nxt[0] - center[0], nxt[1] - center[1]
                radius = max(0.1, math.hypot(dx, dy))
                tangent = (-dy / radius, dx / radius)
                flow = direction[0] * tangent[0] + direction[1] * tangent[1]
                inward = -abs(radius - target_radius)
                return base_score(direction) + flow * 5.0 + inward * 2.0

            return max(options, key=spiral_score)

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
            pattern_step = self.pattern_direction(snake)
            if pattern_step in adjacent_fresh:
                return pattern_step
            return min(
                adjacent_fresh,
                key=lambda direction: (
                    self.head_pressure_at(snake, add_vec(snake.head, direction)),
                    0 if direction == snake.direction else 1,
                ),
            )

        step = self.path_to_cells(snake, fresh_cells)
        if step:
            return step
        return None

    def inside_direction(self, snake: LightSnake) -> Vec:
        if snake.strategy == StrategyKind.BUILDER:
            exits = self.frontier_outside_cells(snake)
            step = self.path_to_cells(snake, exits)
            if step and (snake.head in self.own_border_cells(snake) or random.random() < 0.72):
                return step
            border = self.own_border_cells(snake)
            if border:
                target = min(border, key=lambda cell: manhattan(snake.head, cell) + random.random() * 2)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.8)

        if snake.strategy == StrategyKind.RAIDER:
            enemy_edges = self.neutral_cells_near_enemy(snake)
            if enemy_edges:
                target = min(enemy_edges, key=lambda cell: manhattan(snake.head, cell))
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.9)

        if snake.strategy == StrategyKind.THIEF:
            enemy_edges = self.neutral_cells_near_enemy(snake)
            if enemy_edges:
                target = min(enemy_edges, key=lambda cell: manhattan(snake.head, cell) - self.head_pressure_at(snake, cell))
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.8)

        if snake.strategy == StrategyKind.GUARDIAN:
            if random.random() < 0.34:
                exits = self.frontier_outside_cells(snake)
                target = min(exits, key=lambda cell: manhattan(snake.head, cell)) if exits else None
                if target:
                    return self.path_to_cell(snake, target) or self.best_direction(snake, target, 1.4)
            border = self.own_border_cells(snake)
            if border:
                target = min(border, key=lambda cell: manhattan(snake.head, cell) + random.random() * 4)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 1.7)

        if snake.strategy == StrategyKind.SPRINTER:
            outside = self.neutral_cells()
            if outside:
                target = max(outside, key=lambda cell: manhattan(snake.head, cell) - self.head_pressure_at(snake, cell) * 2)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.7)

        if snake.strategy == StrategyKind.SCOUT:
            exits = self.frontier_outside_cells(snake)
            if exits:
                target = min(exits, key=lambda cell: manhattan(snake.head, cell) + self.head_pressure_at(snake, cell) * 2)
                return self.path_to_cell(snake, target) or self.best_direction(snake, target, 0.9)

        exits = self.frontier_outside_cells(snake)
        target = min(exits, key=lambda cell: manhattan(snake.head, cell)) if exits else None
        return self.best_direction(snake, target, 1.0)

    def update(self, dt: float) -> None:
        self.sounds.update()
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
            return

        self.match_time += dt
        snapshot_second = int(self.match_time)
        if snapshot_second != self.last_snapshot_second:
            self.last_snapshot_second = snapshot_second
            self.log_snapshot()
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
        self.region_fill_timer -= dt
        if self.region_fill_timer <= 0.0:
            self.fill_surrounded_neutral_regions()
            self.region_fill_timer = 0.18

    def resolve_moves(self, movers: List[LightSnake]) -> None:
        proposals: Dict[LightSnake, Cell] = {}
        proposed_directions: Dict[LightSnake, Vec] = {}
        proposed_sizes: Dict[LightSnake, int] = {}
        bonus_attempts: Set[LightSnake] = set()
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
            ):
                bonus_attempts.add(snake)

        bonus_winner: Optional[LightSnake] = None
        if self.bonus and bonus_attempts:
            eligible_attempts = [snake for snake in bonus_attempts if snake not in stalled]
            if eligible_attempts:
                bonus_winner = min(
                    eligible_attempts,
                    key=lambda snake: (
                        0 if self.can_occupy(snake, proposals[snake], size=2) else 1,
                        math.dist(cell_center(proposals[snake]), cell_center(self.bonus.cell)),
                        -snake.speed,
                        snake.name,
                    ),
                )
                proposed_sizes[bonus_winner] = 2
                self.log_event(
                    "bonus_contested",
                    cell=self.bonus.cell,
                    contenders=[snake.name for snake in eligible_attempts],
                    winner=bonus_winner.name,
                )
                for contender in eligible_attempts:
                    if contender is not bonus_winner:
                        stalled.add(contender)

        proposed_footprints: Dict[LightSnake, Set[Cell]] = {}
        for snake, nxt in proposals.items():
            if snake in stalled:
                continue
            proposed_footprints[snake] = self.footprint_for(snake, nxt, size=proposed_sizes[snake])

        snakes = list(proposed_footprints.keys())
        for index, snake in enumerate(snakes):
            for other in snakes[index + 1:]:
                if proposed_footprints[snake] & proposed_footprints[other]:
                    if bonus_winner is snake:
                        stalled.add(other)
                    elif bonus_winner is other:
                        stalled.add(snake)
                    else:
                        stalled.add(snake)
                        stalled.add(other)

        if bonus_winner:
            stalled.discard(bonus_winner)

        for snake in stalled:
            if snake.alive and snake.head in snake.territory:
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
                self.add_status_message(snake, "BECAME BIG")
                self.log_event("bonus_collected", snake=snake.name, cell=snake.head)
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

    def claim_cells(self, snake: LightSnake, cells: Set[Cell]) -> None:
        if not cells:
            return
        for cell in cells:
            previous_owner = self.owner_by_cell.get(cell)
            if previous_owner is snake:
                continue
            if previous_owner is not None:
                previous_owner.territory.discard(cell)
            snake.territory.add(cell)
            self.owner_by_cell[cell] = snake
        self.invalidate_cell_cache()

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
            self.maybe_add_capture_message(owner, len(region))

    def kill_snake(self, snake: LightSnake, reason: str) -> None:
        if not snake.alive:
            return
        snake.alive = False
        snake.final_cells = max(snake.final_cells, len(snake.territory))
        snake.death_reason = reason
        snake.death_flash = 1.0
        self.sounds.play_death()
        self.add_status_message(snake, "WAS ERASED")
        self.log_event("snake_killed", snake=snake.name, reason=reason, cell=snake.head)
        burst_cells = [snake.head]
        for cell in burst_cells:
            self.emit_death_particles(cell, snake.color)

    def emit_capture_particles(self, cells: Set[Cell], color: Color) -> None:
        if not cells:
            return
        for cell in random.sample(tuple(cells), min(28, len(cells))):
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

    def emit_death_particles(self, cell: Cell, color: Color) -> None:
        x, y = cell_center(cell)
        for _ in range(5):
            angle = random.random() * math.tau
            speed = random.uniform(35, 125)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, 0.75, 0.75, 3))

    def add_status_message(self, snake: LightSnake, text: str) -> None:
        self.status_messages.insert(0, StatusMessage(snake.name, text, snake.color, self.match_time))
        self.status_messages = self.status_messages[:4]
        self.sounds.play_notification()
        self.log_event("notification", snake=snake.name, text=text)

    def maybe_add_capture_message(self, snake: LightSnake, cell_count: int) -> None:
        if cell_count <= 0:
            return
        self.log_event("area_closed", snake=snake.name, cells=cell_count)
        if cell_count > 1:
            self.sounds.play_area_capture()
        if self.match_time - snake.last_capture_message_at < BIG_CAPTURE_MESSAGE_COOLDOWN:
            return
        snake.last_capture_message_at = self.match_time
        self.add_status_message(snake, f"CAPTURED {cell_count} CELLS")

    def log_snapshot(self) -> None:
        self.log_event(
            "snapshot",
            bonus=self.bonus.cell if self.bonus else None,
            eraser={
                "x": round(self.eraser_ball.x, 2),
                "y": round(self.eraser_ball.y, 2),
                "vx": round(self.eraser_ball.vx, 2),
                "vy": round(self.eraser_ball.vy, 2),
            } if self.eraser_ball else None,
            snakes=[
                {
                    "name": snake.name,
                    "status": snake.status(),
                    "head": snake.head,
                    "cells": snake.owned_cells,
                }
                for snake in self.snakes
            ],
        )

    def log_event(self, event: str, **details) -> None:
        entry = {"time": round(self.match_time, 3), "event": event, **details}
        if self.gameplay_log_file:
            self.gameplay_log_file.write(json.dumps(entry, ensure_ascii=True) + "\n")
        else:
            self.pending_log_events.append(entry)

    def open_gameplay_log_if_ready(self) -> None:
        if self.gameplay_log_file or not self.recorder:
            return
        path = os.path.join(os.path.dirname(self.recorder.output_path), "gameplay_events.jsonl")
        self.gameplay_log_file = open(path, "w", encoding="utf-8")
        for entry in self.pending_log_events:
            self.gameplay_log_file.write(json.dumps(entry, ensure_ascii=True) + "\n")
        self.gameplay_log_file.flush()
        self.pending_log_events = []
        print(f"Gameplay log: {path}")

    def close_gameplay_log(self) -> None:
        if self.gameplay_log_file:
            self.gameplay_log_file.close()
            self.gameplay_log_file = None

    def finish_match_by_time_limit(self) -> None:
        if self.game_over:
            return
        survivors = [snake for snake in self.snakes if snake.alive]
        candidates = survivors if survivors else self.snakes
        self.winner = max(candidates, key=lambda snake: (snake.owned_cells, snake.captures))
        self.finish_reason = "TIME LIMIT"
        self.game_over = True
        self.end_timer = 0.0
        self.log_event("match_finished", winner=self.winner.name, reason=self.finish_reason)
        self.sounds.play(self.sounds.finish)

    def draw(self) -> None:
        self.screen.fill(BG)
        self.draw_header()
        self.draw_board()
        if self.eraser_ball:
            self.eraser_ball.draw(self.screen)
        if self.bonus:
            self.bonus.draw(self.screen, pygame.time.get_ticks() / 1000.0)
        for snake in self.snakes:
            snake.draw_head(self.screen, self.font_small)
        for particle in self.particles:
            particle.draw(self.screen)
        self.draw_territory_bar()
        self.draw_scoreboard()
        self.draw_countdown()
        self.draw_status_messages()
        if self.match_time < 1.5 and not self.game_over:
            self.draw_hook()
        if self.game_over and self.winner:
            self.draw_winner_screen()
        if self.paused:
            self.draw_pause()
        pygame.display.flip()
        self.open_gameplay_log_if_ready()
        if self.recorder:
            try:
                self.recorder.write_frame(self.screen)
            except RecordingUnavailable as error:
                print(f"Recording stopped: {error}", file=sys.stderr)
                self.sounds.attach_recorder(None)
                self.recorder.abort()
                self.recorder = None

    def draw_hook(self) -> None:
        panel = pygame.Surface((400, 117), pygame.SRCALPHA)
        pygame.draw.rect(panel, (8, 10, 18, 225), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, (*ERASER_COLOR, 210), panel.get_rect(), 3, border_radius=18)
        self.screen.blit(panel, panel.get_rect(center=(WIDTH // 2, 427)))
        hook = self.font_title.render("WHO CONTROLS THE BOARD?", True, WHITE)
        threat = self.font_subtitle.render("DODGE THE ERASER", True, DANGER)
        self.screen.blit(hook, hook.get_rect(center=(WIDTH // 2, 405)))
        self.screen.blit(threat, threat.get_rect(center=(WIDTH // 2, 450)))

    def draw_territory_bar(self) -> None:
        total = sum(snake.owned_cells for snake in self.snakes)
        bar = pygame.Rect(24, TERRITORY_BAR_TOP, WIDTH - 48, 12)
        pygame.draw.rect(self.screen, PANEL, bar, border_radius=6)
        cursor = bar.left
        for index, snake in enumerate(self.snakes):
            if index == len(self.snakes) - 1:
                width = bar.right - cursor
            else:
                width = int(bar.width * snake.owned_cells / max(1, total))
            if width <= 0:
                continue
            color = snake.color if snake.alive else mix(snake.color, PANEL, 0.62)
            pygame.draw.rect(self.screen, color, (cursor, bar.top, width, bar.height), border_radius=5)
            cursor += width
        pygame.draw.rect(self.screen, GRID, bar, 2, border_radius=6)
        label = self.font_small.render("LIVE TERRITORY", True, MUTED)
        self.screen.blit(label, label.get_rect(center=(WIDTH // 2, TERRITORY_BAR_TOP + 24)))

    def draw_status_messages(self) -> None:
        self.status_messages = [
            message for message in self.status_messages
            if self.match_time - message.created_at < 5.0
        ]
        for index, message in enumerate(self.status_messages):
            age = self.match_time - message.created_at
            alpha = 255 if age < 4.3 else int(255 * max(0.0, (5.0 - age) / 0.7))
            width, height = 176, 41
            panel = pygame.Surface((width, height), pygame.SRCALPHA)
            pygame.draw.rect(panel, (13, 17, 29, int(232 * alpha / 255)), panel.get_rect(), border_radius=10)
            pygame.draw.rect(panel, (*message.color, alpha), panel.get_rect(), 2, border_radius=10)
            pygame.draw.circle(panel, (*message.color, alpha), (16, 20), 8)
            initial = self.font_small.render(message.snake_name[0], True, BG)
            initial.set_alpha(alpha)
            panel.blit(initial, initial.get_rect(center=(16, 20)))
            name = self.font_tiny.render(message.snake_name, True, message.color)
            event = self.font_tiny.render(message.text, True, WHITE)
            name.set_alpha(alpha)
            event.set_alpha(alpha)
            panel.blit(name, (29, 5))
            panel.blit(event, (29, 22))
            x = WIDTH - width - 11
            y = 114 + index * (height + 5)
            self.screen.blit(panel, (x, y))

    def draw_header(self) -> None:
        title = self.font_title.render("PICK YOUR SNAKE", True, WHITE)
        subtitle = self.font_subtitle.render("WHITE BALL ERASES TERRITORY", True, MUTED)
        remaining = max(0, math.ceil(self.max_match_seconds - self.match_time))
        timer = self.font_small.render(f"{remaining // 60:02d}:{remaining % 60:02d}", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 36)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 75)))
        self.screen.blit(timer, timer.get_rect(center=(WIDTH // 2, 99)))

    def draw_countdown(self) -> None:
        remaining = max(0, math.ceil(self.max_match_seconds - self.match_time))
        if 0 < remaining <= 15:
            pulse = 1.0 + 0.18 * (0.5 + 0.5 * math.sin(self.match_time * math.tau * 2.0))
            countdown = self.font_winner.render(str(remaining), True, DANGER if remaining <= 5 else WHITE)
            countdown = pygame.transform.smoothscale(
                countdown,
                (int(countdown.get_width() * pulse), int(countdown.get_height() * pulse)),
            )
            glow = pygame.Surface((165, 112), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (*DANGER, 42 if remaining <= 5 else 24), glow.get_rect())
            self.screen.blit(glow, glow.get_rect(center=(WIDTH // 2, 154)))
            self.screen.blit(countdown, countdown.get_rect(center=(WIDTH // 2, 154)))

    def draw_board(self) -> None:
        self.screen.blit(self.board_base, (0, 0))
        for cell, owner in self.owner_by_cell.items():
            amount = 0.68 if owner.alive else 0.28
            pygame.draw.rect(self.screen, mix(NEUTRAL_CELL, owner.color, amount), CELL_FILL_RECTS[cell], border_radius=3)
        wall_color = (86, 101, 142)
        for index, start in enumerate(BOARD_OUTLINE):
            end = BOARD_OUTLINE[(index + 1) % len(BOARD_OUTLINE)]
            edge_x = end[0] - start[0]
            edge_y = end[1] - start[1]
            length = math.hypot(edge_x, edge_y)
            steps = max(1, math.ceil(length / 3))
            previous: Optional[Tuple[int, int]] = None
            for step in range(steps + 1):
                amount = step / steps
                point = (
                    int(round(start[0] + edge_x * amount)),
                    int(round(start[1] + edge_y * amount)),
                )
                if self.wall_has_hole_at(point):
                    previous = None
                    continue
                if previous is not None:
                    pygame.draw.line(self.screen, wall_color, previous, point, 3)
                previous = point

    def draw_scoreboard(self) -> None:
        rect = pygame.Rect(16, SCORE_TOP, WIDTH - 32, HEIGHT - SCORE_TOP - 18)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=7)
        pygame.draw.rect(self.screen, (207, 216, 207), rect, 2, border_radius=7)
        self.screen.blit(self.font_tiny.render("SNAKE / STRATEGY", True, MUTED), (29, SCORE_TOP + 13))
        for header, center_x in (("BLOCKS", 277), ("CONTROL", 350), ("STATUS", 425)):
            image = self.font_tiny.render(header, True, MUTED)
            self.screen.blit(image, image.get_rect(center=(center_x, SCORE_TOP + 21)))
        total_territory = max(1, sum(snake.owned_cells for snake in self.snakes))
        scoreboard_second = int(self.match_time)
        if scoreboard_second != self.last_scoreboard_second:
            self.last_scoreboard_second = scoreboard_second
            self.scoreboard_order = sorted(
                self.snakes,
                key=lambda snake: (-snake.owned_cells, -snake.pattern_step, snake.name),
            )
        for index, snake in enumerate(self.scoreboard_order):
            y = SCORE_TOP + 33 + index * 45
            pygame.draw.circle(self.screen, snake.color, (32, y + 7), 6)
            status = snake.status()
            status_color = MUTED if status == "dead" else snake.color
            control = snake.owned_cells / total_territory * 100
            self.screen.blit(self.font_ui.render(snake.name, True, snake.color), (44, y))
            for value, center_x, color in (
                (str(snake.pattern_step), 277, WHITE),
                (f"{control:.0f}%", 350, snake.color),
                (status, 425, status_color),
            ):
                image = self.font_ui.render(value, True, color)
                self.screen.blit(image, image.get_rect(center=(center_x, y + 10)))
            self.screen.blit(self.font_ui.render(snake.strategy.value, True, WHITE), (44, y + 20))

    def draw_winner_screen(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((3, 5, 13, 220))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(47, 308, WIDTH - 94, 315)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=7)
        for width, alpha in ((21, 35), (11, 70), (3, 255)):
            glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*self.winner.color, alpha), panel.inflate(width, width), width, border_radius=15)
            self.screen.blit(glow, (0, 0))
        winner_text = self.font_winner.render("WINNER", True, self.winner.color)
        name_text = self.font_title.render(self.winner.name, True, WHITE)
        strat_text = self.font_subtitle.render(self.winner.strategy.value, True, MUTED)
        total_territory = max(1, sum(snake.owned_cells for snake in self.snakes))
        control = self.winner.owned_cells / total_territory * 100
        score_text = self.font_subtitle.render(f"Blocks {self.winner.pattern_step}  Control {control:.0f}%", True, WHITE)
        reason_text = self.font_small.render(self.finish_reason, True, MUTED)
        restart_text = self.font_ui.render("PRESS R TO REPLAY", True, MUTED)
        for surf, y in [(winner_text, 363), (name_text, 432), (strat_text, 488), (score_text, 528), (reason_text, 558), (restart_text, 585)]:
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
            if self.game_over and self.end_timer >= RECORDING_END_DELAY_SECONDS:
                running = False
        if self.recorder:
            self.sounds.attach_recorder(None)
            try:
                output_path = self.recorder.close()
                print(f"Recording saved to {output_path}")
            except RecordingUnavailable as error:
                print(f"Could not finish recording: {error}", file=sys.stderr)
        self.close_gameplay_log()
        pygame.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Light Snake Capture pygame simulation")
    parser.add_argument(
        "--no-record",
        action="store_false",
        dest="record_window",
        help="disable automatic frame recording",
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
        time_limit=args.time_limit,
    ).run()
