import argparse
import math
import os
import random
import struct
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from window_recorder import WindowRecorder

import pygame


# ---------------------------
# Quick tuning constants
# ---------------------------
WIDTH, HEIGHT = 360, 640
WINDOW_TITLE = "Ring Pop Ball"
FPS = 60
BOARD_SIZE = 340
BOARD_LEFT = (WIDTH - BOARD_SIZE) // 2
BOARD_TOP = 82
BOARD_WIDTH = BOARD_SIZE
BOARD_HEIGHT = BOARD_SIZE
BOARD_CENTER = (WIDTH // 2, BOARD_TOP + BOARD_HEIGHT // 2)
SCORE_TOP = BOARD_TOP + BOARD_HEIGHT + 11
MATCH_TIME_LIMIT_SECONDS = 120
WINDOW_RECORD_FPS = 15
WINDOW_RECORD_CAPTURE_SIZE = (270, 480)
WINDOW_RECORD_OUTPUT_SIZE = (1080, 1920)
WINDOW_RECORD_END_DELAY_SECONDS = 1.0
WINDOW_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_recordings")
DEFAULT_RECORD_AUDIO_SOURCE = "CABLE Output (VB-Audio Virtual Cable)"

RING_COUNT = 33
RING_THICKNESS = 4
RING_RADIUS_START = 52
RING_RADIUS_STEP = 3.35
RING_SHRINK_SPEED = 1.95
RING_GAP_RADIANS = math.radians(38)
RING_MIN_RADIUS = 18

BALL_RADIUS = 7
BALL_GRAVITY = 170.0
BALL_INITIAL_SPEED = 126.0
BALL_MIN_SPEED = 112.0
BALL_MAX_SPEED = 7_000.0
BOUNCE_DAMPING = 0.988
HIT_SPEED_MULTIPLIER = 1.05
LEVEL_PRELOAD_SECONDS = 0.75

POP_SFX_VOLUME = 0.42
BG_MUSIC_VOLUME = 0.18

BG = (246, 248, 242)
PANEL = (255, 255, 250)
GRID = (222, 228, 218)
WHITE = (42, 50, 62)
MUTED = (126, 137, 139)
DANGER = (210, 93, 96)
SAFE = (80, 145, 103)
RED_BALL = (198, 104, 101)
BLUE_BALL = (92, 139, 184)
BALL_LIGHT = (235, 240, 235)

YELLOW = (221, 177, 76)
GREEN = (104, 166, 129)
CORAL = (198, 104, 101)
BLUE = (92, 139, 184)
PURPLE = (150, 124, 180)
TEAL = (86, 159, 164)

RING_COLORS = [BLUE, GREEN, YELLOW, CORAL, PURPLE, TEAL]

Vec2 = Tuple[float, float]
Color = Tuple[int, int, int]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mix(a: Color, b: Color, amount: float) -> Color:
    return tuple(int(a[index] + (b[index] - a[index]) * amount) for index in range(3))


def length(x: float, y: float) -> float:
    return math.hypot(x, y)


def format_speed(speed: float) -> str:
    if speed >= BALL_MAX_SPEED * 0.995:
        return "∞"
    if speed < 1000:
        return str(int(speed))
    units = [("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)]
    for suffix, scale in units:
        if speed >= scale and speed < scale * 1000:
            return f"{speed / scale:.1f}{suffix}".replace(".0", "")
    return f"{speed:.1e}"


def normalize_angle(angle: float) -> float:
    return angle % math.tau


def signed_angle_delta(a: float, b: float) -> float:
    return (a - b + math.pi) % math.tau - math.pi


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
        self.vx *= 0.965
        self.vy *= 0.965

    def draw(self, surface: pygame.Surface) -> None:
        if self.life <= 0:
            return
        alpha = max(0, min(255, int(255 * self.life / self.max_life)))
        layer_size = max(4, int(self.radius * 4))
        layer = pygame.Surface((layer_size, layer_size), pygame.SRCALPHA)
        center = layer_size // 2
        pygame.draw.circle(layer, (*self.color, alpha), (center, center), max(1, int(self.radius)))
        surface.blit(layer, (self.x - center, self.y - center))


@dataclass
class Ring:
    radius: float
    base_radius: float
    color: Color
    angle: float
    angular_speed: float
    gap_width: float
    popped: bool = False
    pop_flash: float = 0.0

    @property
    def direction_label(self) -> str:
        return "CW" if self.angular_speed > 0 else "CCW"

    def update(self, dt: float) -> None:
        if self.popped:
            self.pop_flash = max(0.0, self.pop_flash - dt)
            return
        self.angle = normalize_angle(self.angle + self.angular_speed * dt)
        self.radius = max(RING_MIN_RADIUS, self.radius - RING_SHRINK_SPEED * dt)

    def angle_in_gap(self, angle: float, ball_radius: float = 0.0) -> bool:
        margin = 0.0
        if self.radius > 1.0 and ball_radius:
            margin = math.asin(clamp(ball_radius / self.radius, 0.0, 0.85))
        return abs(signed_angle_delta(angle, self.angle)) <= self.gap_width / 2 + margin

    def draw(self, surface: pygame.Surface, center: Vec2) -> None:
        if self.popped:
            return
        draw_ring_arc(surface, center, self.radius + 1.0, self.angle, self.gap_width, (205, 214, 204), RING_THICKNESS)
        draw_ring_arc(surface, center, self.radius, self.angle, self.gap_width, self.color, RING_THICKNESS)
        draw_ring_arc(surface, center, self.radius - 2.0, self.angle, self.gap_width, mix(self.color, PANEL, 0.55), 1)
        draw_gap_caps(surface, center, self.radius, self.angle, self.gap_width, self.color)


@dataclass
class Ball:
    name: str
    color: Color
    x: float
    y: float
    vx: float
    vy: float
    score: int = 0
    radius: int = BALL_RADIUS

    def update(self, dt: float) -> None:
        self.vy += BALL_GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.999
        self.vy *= 0.999
        self.limit_speed()

    def limit_speed(self) -> None:
        speed = length(self.vx, self.vy)
        if speed <= 0.01:
            self.vx = BALL_MIN_SPEED
            self.vy = -BALL_MIN_SPEED * 0.35
            return
        if speed < BALL_MIN_SPEED:
            scale = BALL_MIN_SPEED / speed
            self.vx *= scale
            self.vy *= scale
        elif speed > BALL_MAX_SPEED:
            scale = BALL_MAX_SPEED / speed
            self.vx *= scale
            self.vy *= scale

    def speed_up_after_hit(self) -> None:
        self.vx *= HIT_SPEED_MULTIPLIER
        self.vy *= HIT_SPEED_MULTIPLIER
        self.limit_speed()

    def draw(self, surface: pygame.Surface) -> None:
        glow_size = self.radius * 7
        glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*self.color, 34), (glow_size // 2, glow_size // 2), glow_size // 3)
        surface.blit(glow, (self.x - glow_size / 2, self.y - glow_size / 2))

        center = (int(self.x), int(self.y))
        pygame.draw.circle(surface, self.color, center, self.radius)
        pygame.draw.circle(surface, mix(self.color, PANEL, 0.28), center, self.radius, 1)
        pygame.draw.circle(surface, BALL_LIGHT, (int(self.x - 3), int(self.y - 4)), max(2, self.radius // 3))


class PopSound:
    def __init__(self, volume: float = POP_SFX_VOLUME) -> None:
        self.sounds: List[pygame.mixer.Sound] = []
        self.enabled = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            for pitch in (0.86, 0.95, 1.05, 1.18):
                sound = self.create_sound(pitch)
                sound.set_volume(clamp(volume, 0.0, 1.0))
                self.sounds.append(sound)
            self.enabled = True
        except pygame.error:
            self.sounds = []
            self.enabled = False

    @classmethod
    def create_sound_frames(cls, pitch_scale: float) -> bytes:
        sample_rate = 44100
        duration = 0.13
        total = int(sample_rate * duration)
        frames = bytearray()
        for index in range(total):
            t = index / sample_rate
            progress = t / duration
            envelope = (1.0 - progress) ** 2.35
            pitch = (620.0 - progress * 310.0) * pitch_scale
            tone = math.sin(math.tau * pitch * t)
            overtone = 0.42 * math.sin(math.tau * pitch * 1.72 * t)
            snap = 0.22 * math.sin(math.tau * 1840.0 * t) * max(0.0, 1.0 - progress * 8.0)
            value = int(15500 * envelope * (tone + overtone + snap))
            frames.extend(struct.pack("<h", max(-32767, min(32767, value))))
        return bytes(frames)

    def create_sound(self, pitch_scale: float) -> pygame.mixer.Sound:
        return pygame.mixer.Sound(buffer=self.create_sound_frames(pitch_scale))

    def play(self) -> Optional[int]:
        if self.enabled and self.sounds:
            index = random.randrange(len(self.sounds))
            self.sounds[index].play()
            return index
        return None


class BackgroundMusic:
    SAMPLE_RATE = 44100
    DURATION_SECONDS = 8.0

    def __init__(self, volume: float = BG_MUSIC_VOLUME) -> None:
        self.sound: Optional[pygame.mixer.Sound] = None
        self.channel: Optional[pygame.mixer.Channel] = None
        self.enabled = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self.sound = self.create_loop()
            self.sound.set_volume(clamp(volume, 0.0, 1.0))
            self.enabled = True
        except pygame.error:
            self.sound = None
            self.enabled = False

    def create_loop(self) -> pygame.mixer.Sound:
        return pygame.mixer.Sound(buffer=self.create_loop_frames())

    @classmethod
    def create_loop_frames(cls) -> bytes:
        sample_rate = cls.SAMPLE_RATE
        duration = cls.DURATION_SECONDS
        total = int(sample_rate * duration)
        frames = bytearray()
        bass_notes = [130.81, 146.83, 164.81, 196.00]
        bell_notes = [392.00, 493.88, 440.00, 523.25, 329.63, 440.00, 392.00, 587.33]
        for index in range(total):
            t = index / sample_rate
            beat = int(t * 2.0) % len(bell_notes)
            bass = bass_notes[int(t / 2.0) % len(bass_notes)]
            bell = bell_notes[beat]
            beat_pos = (t * 2.0) % 1.0
            bell_env = math.exp(-beat_pos * 5.4)
            bass_wave = math.sin(math.tau * bass * t) * 0.34
            bell_wave = math.sin(math.tau * bell * t) * bell_env * 0.24
            bell_wave += math.sin(math.tau * bell * 2.0 * t) * bell_env * 0.08
            pad = math.sin(math.tau * 65.41 * t) * 0.08 + math.sin(math.tau * 98.00 * t) * 0.06
            fade = min(1.0, index / 3200, (total - index) / 3200)
            value = int(9500 * fade * (bass_wave + bell_wave + pad))
            frames.extend(struct.pack("<h", max(-32767, min(32767, value))))
        return bytes(frames)

    def play(self) -> None:
        if self.enabled and self.sound and self.channel is None:
            self.channel = self.sound.play(loops=-1)

    def stop(self) -> None:
        if self.channel:
            self.channel.stop()
            self.channel = None


def draw_ring_arc(
    surface: pygame.Surface,
    center: Vec2,
    radius: float,
    gap_angle: float,
    gap_width: float,
    color: Color,
    width: int,
) -> None:
    start = gap_angle + gap_width / 2
    arc_size = math.tau - gap_width
    segments = max(44, int(radius * 0.7))
    points = []
    cx, cy = center
    for index in range(segments + 1):
        angle = start + arc_size * index / segments
        points.append((int(round(cx + math.cos(angle) * radius)), int(round(cy + math.sin(angle) * radius))))
    if len(points) > 1:
        pygame.draw.lines(surface, color, False, points, width)


def draw_gap_caps(surface: pygame.Surface, center: Vec2, radius: float, gap_angle: float, gap_width: float, color: Color) -> None:
    cx, cy = center
    cap_radius = max(2, RING_THICKNESS // 2)
    for angle in (gap_angle - gap_width / 2, gap_angle + gap_width / 2):
        point = (int(round(cx + math.cos(angle) * radius)), int(round(cy + math.sin(angle) * radius)))
        pygame.draw.circle(surface, color, point, cap_radius)
        pygame.draw.circle(surface, mix(color, PANEL, 0.5), point, max(1, cap_radius - 2))


class Game:
    def __init__(
        self,
        record_window: bool = False,
        window_record_fps: int = WINDOW_RECORD_FPS,
        window_record_dir: str = WINDOW_RECORDINGS_DIR,
        music_path: str = "",
        music_volume: float = 0.25,
        time_limit: int = MATCH_TIME_LIMIT_SECONDS,
        sfx_volume: float = POP_SFX_VOLUME,
        bg_music_volume: float = BG_MUSIC_VOLUME,
        record_audio_source: str = DEFAULT_RECORD_AUDIO_SOURCE,
    ) -> None:
        pygame.mixer.pre_init(44100, -16, 1, 512)
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
        self.rings: List[Ring] = []
        self.particles: List[Particle] = []
        self.balls = self.create_balls()
        self.paused = False
        self.game_over = False
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.max_match_seconds = max(1, time_limit)
        self.preload_timer = LEVEL_PRELOAD_SECONDS
        self.popped_count = 0
        self.last_pop_time = 0.0
        self.pop_sound = PopSound(sfx_volume)
        self.background_music = BackgroundMusic(bg_music_volume)
        self.background_music.play()
        self.window_recorder = WindowRecorder(
            enabled=record_window,
            window_title=WINDOW_TITLE,
            output_root=window_record_dir,
            session_prefix="ring_pop_ball",
            video_filename="ring_pop_ball_window.mp4",
            music_filename="ring_pop_ball_window_music.mp4",
            fps=window_record_fps,
            capture_size=WINDOW_RECORD_CAPTURE_SIZE,
            output_size=WINDOW_RECORD_OUTPUT_SIZE,
            end_delay_seconds=WINDOW_RECORD_END_DELAY_SECONDS,
            music_path="",
            music_volume=music_volume,
            capture_audio=record_window,
            audio_source=record_audio_source,
            audio_backend="dshow",
            pipe_video=True,
        )
        self.restart()

    def create_balls(self) -> List[Ball]:
        configs = [
            ("RED", RED_BALL, -8.0, 0.0, math.radians(-34), BALL_INITIAL_SPEED * 1.02),
            ("BLUE", BLUE_BALL, 8.0, 0.0, math.radians(-146), BALL_INITIAL_SPEED * 0.98),
        ]
        balls = []
        for name, color, ox, oy, angle, speed in configs:
            balls.append(
                Ball(
                    name,
                    color,
                    BOARD_CENTER[0] + ox,
                    BOARD_CENTER[1] + oy,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                )
            )
        return balls

    def restart(self) -> None:
        self.window_recorder.new_match()
        self.rings = []
        self.particles = []
        self.balls = self.create_balls()
        self.paused = False
        self.game_over = False
        self.finish_reason = ""
        self.end_timer = 0.0
        self.match_time = 0.0
        self.preload_timer = LEVEL_PRELOAD_SECONDS
        self.popped_count = 0
        self.last_pop_time = 0.0
        self.create_rings()

    def create_rings(self) -> None:
        base_angle = random.uniform(-0.45, 0.45)
        start_radius = max(RING_RADIUS_START, self.required_start_ring_radius())
        for index in range(RING_COUNT):
            radius = start_radius + index * RING_RADIUS_STEP
            direction = 1 if index % 2 == 0 else -1
            speed = direction * (0.42 + index * 0.035)
            color = RING_COLORS[index % len(RING_COLORS)]
            gap_angle = base_angle + index * 0.74 + random.uniform(-0.16, 0.16)
            self.rings.append(
                Ring(
                    radius=radius,
                    base_radius=radius,
                    color=color,
                    angle=normalize_angle(gap_angle),
                    angular_speed=speed,
                    gap_width=RING_GAP_RADIANS,
                )
            )

    def required_start_ring_radius(self) -> float:
        cx, cy = BOARD_CENTER
        farthest_ball = max(length(ball.x - cx, ball.y - cy) + ball.radius for ball in self.balls)
        return farthest_ball + RING_THICKNESS + 7.0

    def active_ring(self) -> Optional[Ring]:
        live = [ring for ring in self.rings if not ring.popped]
        if not live:
            return None
        return min(live, key=lambda ring: ring.radius)

    def update(self, dt: float) -> None:
        self.window_recorder.monitor()
        if self.preload_timer > 0.0:
            self.preload_timer = max(0.0, self.preload_timer - dt)
            return
        if self.paused:
            return
        if self.game_over:
            self.end_timer += dt
            self.window_recorder.stop_after_game_over(self.end_timer)
            for particle in self.particles:
                particle.update(dt)
            self.particles = [particle for particle in self.particles if particle.life > 0]
            return

        self.match_time += dt
        if self.match_time >= self.max_match_seconds:
            self.finish_reason = "TIME LIMIT"
            self.game_over = True
            return

        for ring in self.rings:
            ring.update(dt)
        for ball in self.balls:
            ball.update(dt)
        self.handle_ball_collisions()
        for ball in self.balls:
            self.handle_board_collision(ball)
            self.handle_ring_collisions(ball)

        for particle in self.particles:
            particle.update(dt)
        self.particles = [particle for particle in self.particles if particle.life > 0]

        active = self.active_ring()
        if active and active.radius <= BALL_RADIUS + RING_THICKNESS + 3:
            self.finish_reason = "CRUSHED"
            self.game_over = True

        if not active:
            self.finish_reason = "CLEARED"
            self.game_over = True

    def handle_board_collision(self, ball: Ball) -> None:
        left = BOARD_LEFT + BALL_RADIUS + 3
        right = BOARD_LEFT + BOARD_WIDTH - BALL_RADIUS - 3
        top = BOARD_TOP + BALL_RADIUS + 3
        bottom = BOARD_TOP + BOARD_HEIGHT - BALL_RADIUS - 3
        if ball.x < left:
            ball.x = left
            ball.vx = abs(ball.vx) * BOUNCE_DAMPING
            ball.speed_up_after_hit()
        elif ball.x > right:
            ball.x = right
            ball.vx = -abs(ball.vx) * BOUNCE_DAMPING
            ball.speed_up_after_hit()
        if ball.y < top:
            ball.y = top
            ball.vy = abs(ball.vy) * BOUNCE_DAMPING
            ball.speed_up_after_hit()
        elif ball.y > bottom:
            ball.y = bottom
            ball.vy = -abs(ball.vy) * BOUNCE_DAMPING
            ball.speed_up_after_hit()

    def handle_ball_collisions(self) -> None:
        first, second = self.balls
        dx = second.x - first.x
        dy = second.y - first.y
        distance = length(dx, dy)
        min_distance = first.radius + second.radius
        if distance <= 0.01 or distance >= min_distance:
            return

        nx = dx / distance
        ny = dy / distance
        overlap = min_distance - distance
        first.x -= nx * overlap * 0.5
        first.y -= ny * overlap * 0.5
        second.x += nx * overlap * 0.5
        second.y += ny * overlap * 0.5

        relative_vx = second.vx - first.vx
        relative_vy = second.vy - first.vy
        velocity_along_normal = relative_vx * nx + relative_vy * ny
        if velocity_along_normal > 0:
            return

        impulse = -(1.0 + BOUNCE_DAMPING) * velocity_along_normal / 2.0
        first.vx -= impulse * nx
        first.vy -= impulse * ny
        second.vx += impulse * nx
        second.vy += impulse * ny
        first.speed_up_after_hit()
        second.speed_up_after_hit()

    def handle_ring_collisions(self, ball: Ball) -> None:
        ring = self.active_ring()
        if ring is None:
            return
        cx, cy = BOARD_CENTER
        dx = ball.x - cx
        dy = ball.y - cy
        distance = length(dx, dy)
        if distance <= 0.01:
            return
        ball_angle = math.atan2(dy, dx)
        normal = (dx / distance, dy / distance)
        collision_band = BALL_RADIUS + RING_THICKNESS * 0.5
        if distance < ring.radius - collision_band:
            return

        if ring.angle_in_gap(ball_angle, BALL_RADIUS):
            self.pop_ring(ring, ball)
            self.keep_ball_inside_active_ring(ball)
            return

        radial_velocity = ball.vx * normal[0] + ball.vy * normal[1]
        if radial_velocity < 0.0 and distance < ring.radius:
            radial_velocity = 10.0
        ball.vx = (ball.vx - 2.0 * radial_velocity * normal[0]) * BOUNCE_DAMPING
        ball.vy = (ball.vy - 2.0 * radial_velocity * normal[1]) * BOUNCE_DAMPING
        tangent = (-normal[1], normal[0])
        spin = ring.angular_speed * 6.0
        ball.vx += tangent[0] * spin
        ball.vy += tangent[1] * spin
        target_distance = ring.radius - collision_band - 1.2
        ball.x = cx + normal[0] * target_distance
        ball.y = cy + normal[1] * target_distance
        ball.speed_up_after_hit()

    def keep_ball_inside_active_ring(self, ball: Ball) -> None:
        ring = self.active_ring()
        if ring is None:
            return
        cx, cy = BOARD_CENTER
        dx = ball.x - cx
        dy = ball.y - cy
        distance = length(dx, dy)
        if distance <= 0.01:
            return
        safe_distance = ring.radius - BALL_RADIUS - RING_THICKNESS * 0.5 - 2.0
        if distance <= safe_distance:
            return
        scale = max(0.0, safe_distance) / distance
        ball.x = cx + dx * scale
        ball.y = cy + dy * scale

    def pop_ring(self, ring: Ring, ball: Ball) -> None:
        if ring.popped:
            return
        ring.popped = True
        ring.pop_flash = 0.36
        self.popped_count += 1
        ball.score += 1
        self.last_pop_time = self.match_time
        self.pop_sound.play()
        self.emit_ring_particles(ring)

    def emit_ring_particles(self, ring: Ring) -> None:
        cx, cy = BOARD_CENTER
        count = 28
        for index in range(count):
            angle = index * math.tau / count + random.uniform(-0.025, 0.025)
            x = cx + math.cos(angle) * ring.radius
            y = cy + math.sin(angle) * ring.radius
            speed = random.uniform(34.0, 74.0)
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    ring.color,
                    random.uniform(0.42, 0.72),
                    0.72,
                    random.uniform(1.5, 2.8),
                )
            )

    def draw(self) -> None:
        self.screen.fill(BG)
        self.draw_header()
        self.draw_board()
        for ring in sorted((ring for ring in self.rings if not ring.popped), key=lambda item: item.radius, reverse=True):
            ring.draw(self.screen, BOARD_CENTER)
        for particle in self.particles:
            particle.draw(self.screen)
        for ball in self.balls:
            ball.draw(self.screen)
        self.draw_scoreboard()
        if self.game_over:
            self.draw_end_screen()
        elif self.preload_timer > 0.0:
            self.draw_preload()
        if self.paused:
            self.draw_pause()
        pygame.display.flip()
        if self.preload_timer <= 0.0:
            self.window_recorder.start_if_pending()
            if self.window_recorder.needs_video_frame():
                recording_frame = pygame.transform.scale(self.screen, WINDOW_RECORD_CAPTURE_SIZE)
                self.window_recorder.write_video_frame(pygame.image.tobytes(recording_frame, "RGB"))

    def draw_header(self) -> None:
        title = self.font_title.render("1.05X EVERY HIT", True, WHITE)
        subtitle = self.font_subtitle.render("Red vs Blue", True, (94, 125, 145))
        remaining = max(0, int(self.max_match_seconds - self.match_time))
        live = RING_COUNT - self.popped_count
        timer = self.font_small.render(f"{remaining // 60:02d}:{remaining % 60:02d}   Rings {live}", True, MUTED)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 25)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 52)))
        self.screen.blit(timer, timer.get_rect(center=(WIDTH // 2, 69)))

    def draw_board(self) -> None:
        board_rect = pygame.Rect(BOARD_LEFT - 3, BOARD_TOP - 3, BOARD_WIDTH + 6, BOARD_HEIGHT + 6)
        pygame.draw.rect(self.screen, (253, 254, 249), board_rect, border_radius=6)
        pygame.draw.rect(self.screen, (205, 214, 204), board_rect, 1, border_radius=6)
        for index in range(1, 4):
            x = BOARD_LEFT + index * BOARD_WIDTH // 4
            y = BOARD_TOP + index * BOARD_HEIGHT // 4
            pygame.draw.line(self.screen, GRID, (x, BOARD_TOP), (x, BOARD_TOP + BOARD_HEIGHT), 1)
            pygame.draw.line(self.screen, GRID, (BOARD_LEFT, y), (BOARD_LEFT + BOARD_WIDTH, y), 1)
        pygame.draw.circle(self.screen, (229, 234, 225), BOARD_CENTER, 3)

    def draw_scoreboard(self) -> None:
        rect = pygame.Rect(12, SCORE_TOP, WIDTH - 24, HEIGHT - SCORE_TOP - 12)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=4)
        pygame.draw.rect(self.screen, (207, 216, 207), rect, 1, border_radius=4)
        headers = ["BALL", "POPPED", "SPEED", "STATUS"]
        xs = [22, 122, 198, 267]
        for header, x in zip(headers, xs):
            self.screen.blit(self.font_small.render(header, True, MUTED), (x, SCORE_TOP + 8))
        active = self.active_ring()
        status = self.finish_reason if self.game_over else ("clear" if active is None else active.direction_label)
        status_color = SAFE if status in ("CLEARED", "clear") else (DANGER if status in ("CRUSHED", "TIME LIMIT") else WHITE)
        for index, ball in enumerate(self.balls):
            y = SCORE_TOP + 24 + index * 18
            speed = format_speed(length(ball.vx, ball.vy))
            pygame.draw.circle(self.screen, ball.color, (24, y + 7), 5)
            row = [
                (ball.name, 35, ball.color),
                (f"{ball.score}/{RING_COUNT}", 131, WHITE),
                (speed, 211, WHITE),
                (status if index == 0 else "bounce", 267, status_color if index == 0 else MUTED),
            ]
            for text, x, color in row:
                self.screen.blit(self.font_ui.render(text, True, color), (x, y))

        live = [ring for ring in self.rings if not ring.popped]
        track_y = SCORE_TOP + 70
        pygame.draw.line(self.screen, GRID, (28, track_y), (WIDTH - 28, track_y), 2)
        for index, ring in enumerate(self.rings):
            x = 28 + int((WIDTH - 56) * index / max(1, RING_COUNT - 1))
            color = ring.color if not ring.popped else (207, 216, 207)
            pygame.draw.circle(self.screen, color, (x, track_y), 4)
        if live:
            active = self.active_ring()
            if active:
                active_index = self.rings.index(active)
                x = 28 + int((WIDTH - 56) * active_index / max(1, RING_COUNT - 1))
                pulse = 0.5 + math.sin(pygame.time.get_ticks() / 190.0) * 0.5
                pygame.draw.circle(self.screen, active.color, (x, track_y), 6 + int(pulse * 2), 1)

        hint = self.font_small.render("R restart   SPACE pause   S screenshot", True, MUTED)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT - 19)))

    def duel_winner(self) -> Optional[Ball]:
        red, blue = self.balls
        if red.score == blue.score:
            return None
        return red if red.score > blue.score else blue

    def draw_end_screen(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((246, 248, 242, 205))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Rect(35, 205, WIDTH - 70, 210)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=4)
        winner = self.duel_winner()
        color = winner.color if winner else (SAFE if self.finish_reason == "CLEARED" else DANGER)
        pygame.draw.rect(self.screen, color, panel, 2, border_radius=4)
        title = "DRAW" if self.finish_reason == "CLEARED" and winner is None else (f"{winner.name} WINS" if winner else self.finish_reason)
        title_text = self.font_winner.render(title, True, color)
        red, blue = self.balls
        score_text = self.font_title.render(f"{red.score} - {blue.score}", True, WHITE)
        time_text = self.font_subtitle.render(f"Time {int(self.match_time)}s", True, (94, 125, 145))
        restart_text = self.font_ui.render("Press R for new match", True, MUTED)
        for surf, y in [(title_text, 250), (score_text, 299), (time_text, 336), (restart_text, 382)]:
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))

    def draw_pause(self) -> None:
        label = self.font_title.render("PAUSED", True, WHITE)
        self.screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    def draw_preload(self) -> None:
        label = self.font_ui.render("LOADING LEVEL", True, MUTED)
        self.screen.blit(label, label.get_rect(center=(WIDTH // 2, BOARD_TOP + BOARD_HEIGHT - 18)))

    def save_screenshot(self) -> None:
        pygame.image.save(self.screen, f"ring_pop_ball_screenshot_{pygame.time.get_ticks()}.png")

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
        self.background_music.stop()
        pygame.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ring Pop Ball pygame simulation")
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
        "--record-audio-source",
        default=DEFAULT_RECORD_AUDIO_SOURCE,
        help="DirectShow audio recording device, default records VB-CABLE output",
    )
    parser.add_argument(
        "--music",
        default="",
        help="legacy option, unused for live game-audio window recording",
    )
    parser.add_argument(
        "--music-volume",
        type=float,
        default=0.25,
        help="legacy post-music volume, unused for live game-audio window recording",
    )
    parser.add_argument(
        "--sfx-volume",
        type=float,
        default=POP_SFX_VOLUME,
        help=f"pop sound volume from 0.0 to 1.0, default {POP_SFX_VOLUME}",
    )
    parser.add_argument(
        "--bg-music-volume",
        type=float,
        default=BG_MUSIC_VOLUME,
        help=f"in-game background music volume from 0.0 to 1.0, default {BG_MUSIC_VOLUME}",
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
        sfx_volume=args.sfx_volume,
        bg_music_volume=args.bg_music_volume,
        record_audio_source=args.record_audio_source,
    ).run()
