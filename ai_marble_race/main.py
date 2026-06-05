import argparse
import math
import os
import random
import struct
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from window_recorder import WindowRecorder

import pygame


# ---------------------------
# Quick variation parameters
# ---------------------------
RANDOM_SEED = 24
OBSTACLE_COUNT = 5          # 3-5; controls collision-zone density
NARROW_PASSAGE_WIDTH = 82
START_SPREAD_FORCE = 36.0
FRICTION = 0.992
FINAL_BOOST_LENGTH = 76
BALL_COUNT = 6              # 4, 6, or 8

# Video and simulation
WIDTH, HEIGHT = 360, 640
EXPORT_SIZE = (1080, 1920)
FPS = 60
EXPORT_FPS = 30
RACE_DEADLINE = 20.0
FINAL_REVEAL_AFTER = 19.2
FREEZE_SECONDS = 2.0
WINDOW_TITLE = "Choose Your Color - Marble Race"
WINDOW_RECORD_FPS = 30
WINDOW_RECORD_CAPTURE_SIZE = (WIDTH, HEIGHT)
WINDOW_RECORD_OUTPUT_SIZE = EXPORT_SIZE
WINDOW_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_recordings")
DEFAULT_RECORD_AUDIO_SOURCE = "CABLE Output (VB-Audio Virtual Cable)"

# Track geometry
TRACK_LEFT = 18
TRACK_RIGHT = 342
TRACK_TOP = 82
TRACK_BOTTOM = 520
FINISH_Y = 492
BALL_RADIUS = 8

# Calm Reels design palette from DESIGN_GUIDE.md
BG = (246, 248, 242)
PANEL = (255, 255, 250)
GRID = (222, 228, 218)
TEXT = (42, 50, 62)
MUTED = (126, 137, 139)
DANGER = (210, 93, 96)
SAFE = (80, 145, 103)
CORAL = (198, 104, 101)
BALL_COLORS = [
    (221, 177, 76),
    (104, 166, 129),
    (198, 104, 101),
    (92, 139, 184),
    (150, 124, 180),
    (86, 159, 164),
    (225, 139, 79),
    (110, 154, 202),
]
BALL_NAMES = ["YELLOW", "GREEN", "CORAL", "BLUE", "PURPLE", "TEAL", "ORANGE", "SKY"]

Color = Tuple[int, int, int]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mix(a: Color, b: Color, amount: float) -> Color:
    return tuple(int(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def normalize(x: float, y: float) -> Tuple[float, float]:
    length = math.hypot(x, y)
    if length < 0.0001:
        return 0.0, 1.0
    return x / length, y / length


class SoundBank:
    def __init__(self, volume: float = 0.35) -> None:
        self.enabled = False
        self.hit: List[pygame.mixer.Sound] = []
        self.boost: Optional[pygame.mixer.Sound] = None
        self.win: Optional[pygame.mixer.Sound] = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self.hit = [self.make_tone(pitch, 0.055, volume) for pitch in (420, 510, 620)]
            self.boost = self.make_tone(760, 0.14, volume * 0.8, rise=True)
            self.win = self.make_tone(920, 0.32, volume, rise=True)
            self.enabled = True
        except pygame.error:
            self.enabled = False

    @staticmethod
    def make_tone(pitch: float, duration: float, volume: float, rise: bool = False) -> pygame.mixer.Sound:
        sample_rate = 44100
        frames = bytearray()
        for index in range(int(sample_rate * duration)):
            progress = index / (sample_rate * duration)
            envelope = (1.0 - progress) ** 1.8
            frequency = pitch * (1.0 + progress * 0.65 if rise else 1.0 - progress * 0.18)
            sample = math.sin(math.tau * frequency * index / sample_rate)
            frames.extend(struct.pack("<h", int(sample * envelope * clamp(volume, 0.0, 1.0) * 32767)))
        return pygame.mixer.Sound(buffer=bytes(frames))

    def play_hit(self, variant: int) -> None:
        if self.enabled and self.hit:
            self.hit[variant % len(self.hit)].play()

    def play_boost(self) -> None:
        if self.enabled and self.boost:
            self.boost.play()

    def play_win(self) -> None:
        if self.enabled and self.win:
            self.win.play()


@dataclass
class TrailPoint:
    x: float
    y: float
    life: float = 0.42


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Color
    life: float

    def update(self, dt: float) -> None:
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.96
        self.vy *= 0.96


@dataclass(eq=False)
class Ball:
    name: str
    color: Color
    x: float
    y: float
    vx: float
    vy: float
    lane_bias: float
    radius: int = BALL_RADIUS
    finished: bool = False
    finish_time: Optional[float] = None
    rank: Optional[int] = None
    boost_sound_played: bool = False
    trail: List[TrailPoint] = field(default_factory=list)

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def update_trail(self, dt: float) -> None:
        for point in self.trail:
            point.life -= dt
        self.trail = [point for point in self.trail if point.life > 0]
        if not self.finished or len(self.trail) < 3:
            self.trail.append(TrailPoint(self.x, self.y))


class MarbleRace:
    def __init__(
        self,
        random_seed: int = RANDOM_SEED,
        obstacle_count: int = OBSTACLE_COUNT,
        narrow_passage_width: int = NARROW_PASSAGE_WIDTH,
        start_spread_force: float = START_SPREAD_FORCE,
        friction: float = FRICTION,
        final_boost_length: int = FINAL_BOOST_LENGTH,
        ball_count: int = BALL_COUNT,
        sounds: Optional[SoundBank] = None,
    ) -> None:
        self.random_seed = random_seed
        self.rng = random.Random(random_seed)
        self.obstacle_count = int(clamp(obstacle_count, 3, 5))
        self.narrow_passage_width = int(clamp(narrow_passage_width, 54, 150))
        self.start_spread_force = clamp(start_spread_force, 0.0, 90.0)
        self.friction = clamp(friction, 0.96, 0.9995)
        self.final_boost_length = int(clamp(final_boost_length, 45, 110))
        self.ball_count = ball_count if ball_count in (4, 6, 8) else 6
        self.sounds = sounds

        self.elapsed = 0.0
        self.spinner_angle = 0.0
        self.spinner_speed = 2.5
        self.finished_order: List[Ball] = []
        self.particles: List[Particle] = []
        self.done = False
        self.freeze_elapsed = 0.0
        self.last_hit_sound_at = -1.0
        self.fonts: dict = {}

        self.gate_y = 202
        self.gate_center = WIDTH // 2 + self.rng.randint(-28, 28)
        self.spinner_center = (WIDTH // 2, 275)
        self.spinner_length = 122
        self.bumpers = self.make_bumpers()
        self.boost_top = FINISH_Y - self.final_boost_length
        self.balls = self.make_balls()

    def make_balls(self) -> List[Ball]:
        balls = []
        available = TRACK_RIGHT - TRACK_LEFT - 30
        spacing = available / self.ball_count
        for index in range(self.ball_count):
            x = TRACK_LEFT + 15 + spacing * (index + 0.5)
            x += self.rng.uniform(-spacing * 0.12, spacing * 0.12)
            balls.append(
                Ball(
                    BALL_NAMES[index],
                    BALL_COLORS[index],
                    x,
                    TRACK_TOP + 18 + self.rng.uniform(-2, 2),
                    self.rng.uniform(-self.start_spread_force, self.start_spread_force),
                    self.rng.uniform(19, 28),
                    self.rng.uniform(-18, 18),
                )
            )
        return balls

    def make_bumpers(self) -> List[Tuple[float, float, float]]:
        bumpers = [
            (82, 326, 14),
            (180, 324, 16),
            (278, 326, 14),
            (128, 360, 14),
            (232, 360, 14),
            (78, 397, 12),
            (180, 395, 14),
            (282, 397, 12),
        ]
        if self.obstacle_count == 3:
            return bumpers[:4]
        if self.obstacle_count == 4:
            return bumpers[:6]
        return bumpers

    def burst(self, ball: Ball, count: int = 5) -> None:
        for _ in range(count):
            angle = self.rng.random() * math.tau
            speed = self.rng.uniform(18, 55)
            self.particles.append(
                Particle(ball.x, ball.y, math.cos(angle) * speed, math.sin(angle) * speed, ball.color, 0.35)
            )

    def update(self, dt: float) -> None:
        if self.done:
            self.freeze_elapsed += dt
            return

        self.elapsed += dt
        self.spinner_angle += self.spinner_speed * dt
        for particle in self.particles:
            particle.update(dt)
        self.particles = [particle for particle in self.particles if particle.life > 0]

        for ball in self.balls:
            ball.update_trail(dt)
            if ball.finished:
                continue
            self.update_ball(ball, dt)

        self.resolve_ball_collisions()

        if self.elapsed >= RACE_DEADLINE and not self.finished_order:
            leader = max(self.balls, key=lambda item: item.y)
            leader.y = FINISH_Y + leader.radius + 1
            self.finish_ball(leader)

        if self.finished_order and (
            self.elapsed >= RACE_DEADLINE
            or (self.elapsed >= FINAL_REVEAL_AFTER and len(self.finished_order) == self.ball_count)
        ):
            self.complete_race()

    def update_ball(self, ball: Ball, dt: float) -> None:
        # Constant downhill pull plus a tiny seeded weave keeps the race lively.
        weave = math.sin(self.elapsed * 3.2 + self.balls.index(ball) * 1.71) * 11.0
        center_pull = (WIDTH / 2 + ball.lane_bias - ball.x) * 0.12
        ball.vx += (weave + center_pull) * dt
        ball.vy += 12.75 * dt

        if ball.y >= self.boost_top:
            if not ball.boost_sound_played:
                ball.boost_sound_played = True
                if self.sounds:
                    self.sounds.play_boost()
            ball.vy += 105.0 * dt

        frame_friction = self.friction ** (dt * FPS)
        ball.vx *= frame_friction
        ball.vy *= frame_friction
        speed = ball.speed
        if speed > 78:
            scale = 78 / speed
            ball.vx *= scale
            ball.vy *= scale

        old_x, old_y = ball.x, ball.y
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt
        self.resolve_track_walls(ball)
        self.resolve_gate(ball, old_y)
        self.resolve_spinner(ball)
        self.resolve_bumpers(ball)

        if ball.y >= FINISH_Y + ball.radius:
            self.finish_ball(ball)
        elif ball.y < old_y - 4 or abs(ball.x - old_x) > 8:
            ball.lane_bias += self.rng.uniform(-0.25, 0.25)

    def resolve_track_walls(self, ball: Ball) -> None:
        if ball.x - ball.radius < TRACK_LEFT:
            ball.x = TRACK_LEFT + ball.radius
            ball.vx = abs(ball.vx) * 0.8
        elif ball.x + ball.radius > TRACK_RIGHT:
            ball.x = TRACK_RIGHT - ball.radius
            ball.vx = -abs(ball.vx) * 0.8

    def resolve_gate(self, ball: Ball, old_y: float) -> None:
        half_gap = self.narrow_passage_width / 2
        in_gap = self.gate_center - half_gap + ball.radius < ball.x < self.gate_center + half_gap - ball.radius
        crossed = old_y + ball.radius <= self.gate_y < ball.y + ball.radius
        if crossed and not in_gap:
            ball.y = self.gate_y - ball.radius
            ball.vy = -abs(ball.vy) * 0.48
            direction = 1 if ball.x < self.gate_center else -1
            ball.vx += direction * 42
            self.play_hit_sound(ball)

    def resolve_spinner(self, ball: Ball) -> None:
        cx, cy = self.spinner_center
        dx = math.cos(self.spinner_angle) * self.spinner_length / 2
        dy = math.sin(self.spinner_angle) * self.spinner_length / 2
        ax, ay = cx - dx, cy - dy
        bx, by = cx + dx, cy + dy
        abx, aby = bx - ax, by - ay
        projection = clamp(((ball.x - ax) * abx + (ball.y - ay) * aby) / (abx * abx + aby * aby), 0, 1)
        px, py = ax + abx * projection, ay + aby * projection
        nx, ny = ball.x - px, ball.y - py
        distance = math.hypot(nx, ny)
        min_distance = ball.radius + 4
        if distance < min_distance:
            nx, ny = normalize(nx, ny)
            ball.x = px + nx * min_distance
            ball.y = py + ny * min_distance
            relative = ball.vx * nx + ball.vy * ny
            ball.vx -= 1.75 * relative * nx
            ball.vy -= 1.75 * relative * ny
            tangent_x, tangent_y = -ny, nx
            ball.vx += tangent_x * self.spinner_speed * 10
            ball.vy += tangent_y * self.spinner_speed * 10
            self.play_hit_sound(ball)

    def resolve_bumpers(self, ball: Ball) -> None:
        for bx, by, radius in self.bumpers:
            dx, dy = ball.x - bx, ball.y - by
            distance = math.hypot(dx, dy)
            min_distance = radius + ball.radius
            if distance < min_distance:
                nx, ny = normalize(dx, dy)
                ball.x = bx + nx * min_distance
                ball.y = by + ny * min_distance
                impact = ball.vx * nx + ball.vy * ny
                ball.vx -= 1.8 * impact * nx
                ball.vy -= 1.8 * impact * ny
                self.play_hit_sound(ball)

    def resolve_ball_collisions(self) -> None:
        active = [ball for ball in self.balls if not ball.finished]
        for index, first in enumerate(active):
            for second in active[index + 1 :]:
                dx, dy = second.x - first.x, second.y - first.y
                distance = math.hypot(dx, dy)
                min_distance = first.radius + second.radius
                if distance >= min_distance:
                    continue
                nx, ny = normalize(dx, dy)
                overlap = min_distance - max(distance, 0.01)
                first.x -= nx * overlap / 2
                first.y -= ny * overlap / 2
                second.x += nx * overlap / 2
                second.y += ny * overlap / 2
                relative = (second.vx - first.vx) * nx + (second.vy - first.vy) * ny
                if relative < 0:
                    impulse = -relative * 0.86
                    first.vx -= impulse * nx
                    first.vy -= impulse * ny
                    second.vx += impulse * nx
                    second.vy += impulse * ny
                    self.play_hit_sound(first)

    def play_hit_sound(self, ball: Ball) -> None:
        if self.sounds and self.elapsed - self.last_hit_sound_at >= 0.075:
            self.last_hit_sound_at = self.elapsed
            self.sounds.play_hit(self.balls.index(ball))

    def finish_ball(self, ball: Ball) -> None:
        if ball.finished:
            return
        ball.finished = True
        ball.finish_time = self.elapsed
        ball.rank = len(self.finished_order) + 1
        ball.y = FINISH_Y + 10 + (ball.rank - 1) * 2
        ball.vx = ball.vy = 0
        self.finished_order.append(ball)
        self.burst(ball, 12 if ball.rank == 1 else 5)
        if ball.rank == 1 and self.sounds:
            self.sounds.play_win()

    def complete_race(self) -> None:
        remaining = sorted((ball for ball in self.balls if not ball.finished), key=lambda item: item.y, reverse=True)
        for ball in remaining:
            ball.finished = True
            ball.finish_time = None
            ball.rank = len(self.finished_order) + 1
            self.finished_order.append(ball)
        self.done = True

    def get_font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("arial", size, bold=bold)
        return self.fonts[key]

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(BG)
        self.draw_header(surface)
        self.draw_track(surface)
        self.draw_effects(surface)
        self.draw_balls(surface)
        self.draw_table(surface)
        if self.done:
            self.draw_winner_overlay(surface)

    def draw_header(self, surface: pygame.Surface) -> None:
        title = "CHOOSE YOUR COLOR" if self.elapsed < 1.8 else "MARBLE RACE"
        title_surface = self.get_font(22, True).render(title, True, TEXT)
        surface.blit(title_surface, title_surface.get_rect(center=(WIDTH // 2, 22)))
        subtitle = self.get_font(11).render("Who reaches the boost first?", True, MUTED)
        surface.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 43)))
        timer = self.get_font(13, True).render(f"{min(self.elapsed, RACE_DEADLINE):04.1f}s", True, TEXT)
        surface.blit(timer, timer.get_rect(center=(WIDTH // 2, 62)))

    def draw_track(self, surface: pygame.Surface) -> None:
        track = pygame.Rect(TRACK_LEFT, TRACK_TOP, TRACK_RIGHT - TRACK_LEFT, TRACK_BOTTOM - TRACK_TOP)
        pygame.draw.rect(surface, PANEL, track, border_radius=12)
        for y in range(TRACK_TOP + 18, TRACK_BOTTOM, 24):
            pygame.draw.line(surface, GRID, (TRACK_LEFT + 6, y), (TRACK_RIGHT - 6, y), 1)
        pygame.draw.rect(surface, GRID, track, 2, border_radius=12)

        half_gap = self.narrow_passage_width // 2
        pygame.draw.line(surface, TEXT, (TRACK_LEFT, self.gate_y), (self.gate_center - half_gap, self.gate_y), 5)
        pygame.draw.line(surface, TEXT, (self.gate_center + half_gap, self.gate_y), (TRACK_RIGHT, self.gate_y), 5)
        gate_label = self.get_font(9, True).render("NARROW PASS", True, MUTED)
        surface.blit(gate_label, gate_label.get_rect(center=(WIDTH // 2, self.gate_y - 10)))

        self.draw_spinner(surface)
        for x, y, radius in self.bumpers:
            pygame.draw.circle(surface, mix(TEXT, PANEL, 0.7), (int(x), int(y)), int(radius + 3))
            pygame.draw.circle(surface, TEXT, (int(x), int(y)), int(radius), 2)
            pygame.draw.circle(surface, PANEL, (int(x - radius * 0.3), int(y - radius * 0.3)), 3)

        boost_rect = pygame.Rect(TRACK_LEFT + 2, self.boost_top, TRACK_RIGHT - TRACK_LEFT - 4, FINISH_Y - self.boost_top)
        boost_layer = pygame.Surface(boost_rect.size, pygame.SRCALPHA)
        boost_layer.fill((*SAFE, 24))
        surface.blit(boost_layer, boost_rect)
        for y in range(self.boost_top + 8, FINISH_Y - 4, 16):
            for x in range(TRACK_LEFT + 22, TRACK_RIGHT - 12, 44):
                pygame.draw.polygon(surface, mix(SAFE, PANEL, 0.32), [(x, y + 5), (x + 6, y), (x + 12, y + 5)], 2)
        boost_label = self.get_font(9, True).render("FINAL BOOST", True, SAFE)
        surface.blit(boost_label, boost_label.get_rect(center=(WIDTH // 2, self.boost_top + 9)))
        self.draw_finish_line(surface)

    def draw_spinner(self, surface: pygame.Surface) -> None:
        cx, cy = self.spinner_center
        dx = math.cos(self.spinner_angle) * self.spinner_length / 2
        dy = math.sin(self.spinner_angle) * self.spinner_length / 2
        start, end = (int(cx - dx), int(cy - dy)), (int(cx + dx), int(cy + dy))
        pygame.draw.line(surface, mix(CORAL, PANEL, 0.55), start, end, 10)
        pygame.draw.line(surface, CORAL, start, end, 4)
        pygame.draw.circle(surface, PANEL, (cx, cy), 8)
        pygame.draw.circle(surface, CORAL, (cx, cy), 8, 2)

    def draw_finish_line(self, surface: pygame.Surface) -> None:
        cell = 8
        for index, x in enumerate(range(TRACK_LEFT + 2, TRACK_RIGHT - 2, cell)):
            color = TEXT if index % 2 == 0 else PANEL
            pygame.draw.rect(surface, color, (x, FINISH_Y, cell, 5))
        pygame.draw.line(surface, TEXT, (TRACK_LEFT + 2, FINISH_Y + 5), (TRACK_RIGHT - 2, FINISH_Y + 5), 1)

    def draw_effects(self, surface: pygame.Surface) -> None:
        for particle in self.particles:
            alpha = int(clamp(particle.life / 0.35, 0, 1) * 150)
            layer = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*particle.color, alpha), (4, 4), 3)
            surface.blit(layer, (particle.x - 4, particle.y - 4))

    def draw_balls(self, surface: pygame.Surface) -> None:
        for ball in self.balls:
            for index, point in enumerate(ball.trail):
                alpha = int(65 * clamp(point.life / 0.42, 0, 1))
                radius = max(2, int(ball.radius * (index + 1) / max(1, len(ball.trail)) * 0.75))
                layer = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
                pygame.draw.circle(layer, (*ball.color, alpha), (radius * 2, radius * 2), radius)
                surface.blit(layer, (point.x - radius * 2, point.y - radius * 2))

            glow = pygame.Surface((36, 36), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*ball.color, 35), (18, 18), 16)
            surface.blit(glow, (ball.x - 18, ball.y - 18))
            center = (int(ball.x), int(ball.y))
            pygame.draw.circle(surface, ball.color, center, ball.radius)
            pygame.draw.circle(surface, mix(ball.color, TEXT, 0.22), center, ball.radius, 1)
            pygame.draw.circle(surface, mix(ball.color, PANEL, 0.72), (center[0] - 3, center[1] - 3), 2)

    def draw_table(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(18, 532, 324, 98)
        pygame.draw.rect(surface, PANEL, panel, border_radius=10)
        pygame.draw.rect(surface, GRID, panel, 1, border_radius=10)
        standings = self.finished_order + sorted(
            [ball for ball in self.balls if ball not in self.finished_order],
            key=lambda item: item.y,
            reverse=True,
        )
        column_width = 102
        for index, ball in enumerate(standings[:6]):
            col, row = index % 3, index // 3
            x = panel.left + 9 + col * column_width
            y = panel.top + 13 + row * 38
            pygame.draw.circle(surface, ball.color, (x + 5, y + 6), 5)
            label = f"{index + 1}. {ball.name}"
            surface.blit(self.get_font(9, True).render(label, True, TEXT), (x + 14, y))
            status = f"{ball.finish_time:.2f}s" if ball.finish_time is not None else f"{int(ball.y - TRACK_TOP):03d}m"
            surface.blit(self.get_font(8).render(status, True, MUTED), (x + 14, y + 13))

    def draw_winner_overlay(self, surface: pygame.Surface) -> None:
        if not self.finished_order:
            return
        winner = self.finished_order[0]
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((255, 255, 250, 100))
        surface.blit(overlay, (0, 0))
        card = pygame.Rect(62, 206, 236, 158)
        pygame.draw.rect(surface, PANEL, card, border_radius=18)
        pygame.draw.rect(surface, winner.color, card, 3, border_radius=18)
        heading = self.get_font(14, True).render("WINNER", True, MUTED)
        surface.blit(heading, heading.get_rect(center=(WIDTH // 2, 232)))
        pygame.draw.circle(surface, winner.color, (WIDTH // 2, 270), 20)
        pygame.draw.circle(surface, mix(winner.color, PANEL, 0.7), (WIDTH // 2 - 7, 263), 5)
        name = self.get_font(25, True).render(winner.name, True, TEXT)
        surface.blit(name, name.get_rect(center=(WIDTH // 2, 310)))
        time_text = f"FINISH  {winner.finish_time:.2f}s" if winner.finish_time is not None else "PHOTO FINISH"
        finish = self.get_font(11, True).render(time_text, True, winner.color)
        surface.blit(finish, finish.get_rect(center=(WIDTH // 2, 339)))


def auto_record_frames(
    output_dir: str,
    random_seed: int = RANDOM_SEED,
    fps: int = EXPORT_FPS,
    max_seconds: float = RACE_DEADLINE + FREEZE_SECONDS,
    output_size: Tuple[int, int] = EXPORT_SIZE,
    **race_options: object,
) -> MarbleRace:
    """Render a deterministic PNG sequence ready for ffmpeg or another encoder."""
    os.makedirs(output_dir, exist_ok=True)
    pygame.init()
    pygame.font.init()
    canvas = pygame.Surface((WIDTH, HEIGHT))
    race = MarbleRace(random_seed=random_seed, **race_options)
    total_frames = int(max_seconds * fps)
    simulation_time = 0.0
    for frame_number in range(total_frames):
        target_time = (frame_number + 1) / fps
        while simulation_time + 0.000001 < target_time:
            race.update(1.0 / FPS)
            simulation_time += 1.0 / FPS
        race.draw(canvas)
        frame = pygame.transform.smoothscale(canvas, output_size)
        pygame.image.save(frame, os.path.join(output_dir, f"frame_{frame_number:05d}.png"))
    pygame.quit()
    return race


def run_headless(race: MarbleRace, seconds: float = RACE_DEADLINE + FREEZE_SECONDS) -> None:
    for _ in range(int(seconds * FPS)):
        race.update(1.0 / FPS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vertical marble race Reel simulation")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--obstacles", type=int, default=OBSTACLE_COUNT)
    parser.add_argument("--passage-width", type=int, default=NARROW_PASSAGE_WIDTH)
    parser.add_argument("--start-spread", type=float, default=START_SPREAD_FORCE)
    parser.add_argument("--friction", type=float, default=FRICTION)
    parser.add_argument("--boost-length", type=int, default=FINAL_BOOST_LENGTH)
    parser.add_argument("--balls", type=int, choices=(4, 6, 8), default=BALL_COUNT)
    parser.add_argument("--export-frames", metavar="DIR")
    parser.add_argument("--export-fps", type=int, default=EXPORT_FPS)
    parser.add_argument("--export-seconds", type=float, default=RACE_DEADLINE + FREEZE_SECONDS)
    parser.add_argument("--batch", type=int, default=1, help="Export N sequential seeds")
    parser.add_argument("--headless-test", action="store_true")
    parser.add_argument(
        "--record-window",
        action="store_true",
        help="record MP4 with ffmpeg and live audio from the virtual output",
    )
    parser.add_argument("--record-fps", type=int, default=WINDOW_RECORD_FPS)
    parser.add_argument("--record-dir", default=WINDOW_RECORDINGS_DIR)
    parser.add_argument(
        "--record-audio-source",
        default=DEFAULT_RECORD_AUDIO_SOURCE,
        help="DirectShow audio device, usually VB-CABLE Output",
    )
    parser.add_argument("--record-audio-volume", type=float, default=1.0)
    parser.add_argument("--sfx-volume", type=float, default=0.35)
    return parser.parse_args()


def race_options(args: argparse.Namespace) -> dict:
    return {
        "obstacle_count": args.obstacles,
        "narrow_passage_width": args.passage_width,
        "start_spread_force": args.start_spread,
        "friction": args.friction,
        "final_boost_length": args.boost_length,
        "ball_count": args.balls,
    }


def main() -> None:
    args = parse_args()
    options = race_options(args)
    if args.export_frames:
        for index in range(max(1, args.batch)):
            seed = args.seed + index
            directory = args.export_frames if args.batch == 1 else os.path.join(args.export_frames, f"seed_{seed}")
            race = auto_record_frames(directory, seed, args.export_fps, args.export_seconds, **options)
            winner = race.finished_order[0].name if race.finished_order else "none"
            print(f"seed={seed} winner={winner} frames={int(args.export_seconds * args.export_fps)} dir={directory}")
        return

    pygame.mixer.pre_init(44100, -16, 1, 512)
    pygame.init()
    pygame.font.init()
    if args.headless_test:
        race = MarbleRace(args.seed, **options)
        run_headless(race)
        winner = race.finished_order[0].name if race.finished_order else "none"
        print(f"seed={args.seed} winner={winner} finishers={len(race.finished_order)} done={race.done}")
        pygame.quit()
        return

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()
    sounds = SoundBank(args.sfx_volume)
    race = MarbleRace(args.seed, sounds=sounds, **options)
    recorder = WindowRecorder(
        enabled=args.record_window,
        window_title=WINDOW_TITLE,
        output_root=args.record_dir,
        session_prefix="marble_race",
        video_filename="marble_race.mp4",
        music_filename="marble_race_music.mp4",
        fps=args.record_fps,
        capture_size=WINDOW_RECORD_CAPTURE_SIZE,
        output_size=WINDOW_RECORD_OUTPUT_SIZE,
        end_delay_seconds=FREEZE_SECONDS,
        capture_audio=args.record_window,
        audio_source=args.record_audio_source,
        audio_backend="dshow",
        audio_volume=args.record_audio_volume,
        pipe_video=True,
    )
    recorder.new_match()
    running = True
    paused = False
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)
        recorder.monitor()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_r:
                    args.seed += 1
                    race = MarbleRace(args.seed, sounds=sounds, **options)
                    recorder.new_match()
                elif event.key == pygame.K_s:
                    pygame.image.save(screen, f"marble_race_seed_{args.seed}.png")
        if not paused:
            race.update(dt)
        if race.done:
            recorder.stop_after_game_over(race.freeze_elapsed)
        race.draw(screen)
        pygame.display.flip()
        recorder.start_if_pending()
        if recorder.needs_video_frame():
            recorder.write_video_frame(pygame.image.tobytes(screen, "RGB"))
    recorder.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
