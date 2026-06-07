import argparse
import math
import os
import random
import struct
import sys
from dataclasses import dataclass
from typing import List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from window_recorder import WindowRecorder

import pygame


WIDTH, HEIGHT = 360, 640
EXPORT_SIZE = (1080, 1920)
FPS = 30
GAME_SECONDS = 29.5
FREEZE_SECONDS = 0.5
TOTAL_SECONDS = GAME_SECONDS + FREEZE_SECONDS
TITLE = "Boss Bouncing Ball Arena"
RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_recordings")

BG = (4, 6, 17)
GRID = (19, 25, 47)
WHITE = (242, 248, 255)
MUTED = (132, 147, 177)
BOSS = (255, 38, 103)
BOSS_CORE = (255, 176, 207)
MINION_COLORS = ((32, 224, 255), (255, 210, 46), (139, 82, 255))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Ball:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    color: Tuple[int, int, int]
    boss: bool = False
    alive: bool = True
    hp: float = 1.0


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Tuple[int, int, int]
    life: float
    size: float


@dataclass
class Ring:
    x: float
    y: float
    radius: float
    speed: float
    color: Tuple[int, int, int]
    life: float


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    color: Tuple[int, int, int]
    life: float = 1.8


def make_sound(frequency: float, duration: float, volume: float, slide: float = 0.0) -> pygame.mixer.Sound:
    sample_rate = 44100
    frames = bytearray()
    count = int(sample_rate * duration)
    for index in range(count):
        progress = index / count
        pitch = frequency * (1.0 + slide * progress)
        envelope = math.sin(math.pi * progress) ** 0.45 * (1.0 - progress) ** 0.25
        wave = math.sin(math.tau * pitch * index / sample_rate)
        wave += 0.28 * math.sin(math.tau * pitch * 2.03 * index / sample_rate)
        sample = int(clamp(wave * envelope * volume, -1.0, 1.0) * 32767)
        frames.extend(struct.pack("<h", sample))
    return pygame.mixer.Sound(buffer=bytes(frames))


class SoundBank:
    def __init__(self) -> None:
        self.enabled = False
        self.shots: List[pygame.mixer.Sound] = []
        self.hit = None
        self.pop = None
        self.dash = None
        self.shockwave = None
        self.spawn = None
        self.finish = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            pygame.mixer.set_num_channels(24)
            self.shots = [make_sound(pitch, 0.07, 0.13, 0.5) for pitch in (690, 820, 970)]
            self.hit = make_sound(155, 0.12, 0.23, -0.45)
            self.pop = make_sound(420, 0.16, 0.24, 0.9)
            self.dash = make_sound(240, 0.24, 0.28, 1.4)
            self.shockwave = make_sound(105, 0.48, 0.34, -0.35)
            self.spawn = make_sound(390, 0.35, 0.25, 1.1)
            self.finish = make_sound(180, 0.72, 0.38, 1.8)
            self.enabled = True
        except pygame.error:
            pass

    def play(self, sound: pygame.mixer.Sound) -> None:
        if self.enabled and sound:
            sound.play()


class Arena:
    def __init__(self, seed: int, minion_count: int, sounds: SoundBank) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.time = 0.0
        self.ability_text = ""
        self.ability_life = 0.0
        self.next_ability = 3.2
        self.particles: List[Particle] = []
        self.rings: List[Ring] = []
        self.projectiles: List[Projectile] = []
        self.sounds = sounds
        self.next_shot = 0.12
        self.flash = 0.0
        self.shake = 0.0
        self.finished = False
        self.freeze_time = 0.0
        self.winner = ""
        self.initial_count = minion_count
        self.boss = Ball(WIDTH / 2, HEIGHT / 2, 86, -74, 38, BOSS, True, True, 1.0)
        self.minions: List[Ball] = []
        for index in range(minion_count):
            angle = math.tau * index / minion_count + self.rng.uniform(-0.12, 0.12)
            distance = self.rng.uniform(105, 215)
            x = clamp(WIDTH / 2 + math.cos(angle) * distance, 22, WIDTH - 22)
            y = clamp(HEIGHT / 2 + math.sin(angle) * distance, 78, HEIGHT - 36)
            speed = self.rng.uniform(78, 125)
            heading = angle + math.pi + self.rng.uniform(-0.7, 0.7)
            self.minions.append(
                Ball(x, y, math.cos(heading) * speed, math.sin(heading) * speed, 9, MINION_COLORS[index % 3])
            )

    def burst(self, x: float, y: float, color: Tuple[int, int, int], count: int, force: float) -> None:
        for _ in range(count):
            angle = self.rng.random() * math.tau
            speed = self.rng.uniform(force * 0.35, force)
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, color, self.rng.uniform(0.3, 0.75), self.rng.uniform(1.5, 4.0))
            )

    def announce(self, text: str) -> None:
        self.ability_text = text
        self.ability_life = 0.9

    def use_ability(self) -> None:
        alive = [ball for ball in self.minions if ball.alive]
        phase = int(self.time // 4) % 3
        if phase == 0 and alive:
            target = min(alive, key=lambda ball: (ball.x - self.boss.x) ** 2 + (ball.y - self.boss.y) ** 2)
            dx, dy = target.x - self.boss.x, target.y - self.boss.y
            distance = max(1.0, math.hypot(dx, dy))
            self.boss.vx, self.boss.vy = dx / distance * 310, dy / distance * 310
            self.announce("BOSS DASH")
            self.sounds.play(self.sounds.dash)
        elif phase == 1:
            self.rings.append(Ring(self.boss.x, self.boss.y, self.boss.radius, 220, BOSS, 0.75))
            for ball in alive:
                dx, dy = ball.x - self.boss.x, ball.y - self.boss.y
                distance = max(1.0, math.hypot(dx, dy))
                impulse = 245 / max(0.65, distance / 100)
                ball.vx += dx / distance * impulse
                ball.vy += dy / distance * impulse
            self.shake = 0.35
            self.flash = 0.18
            self.announce("SHOCKWAVE")
            self.sounds.play(self.sounds.shockwave)
        else:
            for _ in range(2):
                angle = self.rng.random() * math.tau
                self.minions.append(
                    Ball(
                        self.boss.x + math.cos(angle) * 58,
                        self.boss.y + math.sin(angle) * 58,
                        math.cos(angle) * 155,
                        math.sin(angle) * 155,
                        7,
                        BOSS_CORE,
                    )
                )
            self.burst(self.boss.x, self.boss.y, BOSS_CORE, 18, 145)
            self.announce("SPAWN ORBS")
            self.sounds.play(self.sounds.spawn)
        self.next_ability += self.rng.uniform(3.4, 4.6)

    def shoot(self, shooters: List[Ball]) -> None:
        shooter = self.rng.choice(shooters)
        travel = math.hypot(self.boss.x - shooter.x, self.boss.y - shooter.y) / 330
        target_x = self.boss.x + self.boss.vx * travel * 0.32
        target_y = self.boss.y + self.boss.vy * travel * 0.32
        dx, dy = target_x - shooter.x, target_y - shooter.y
        distance = max(1.0, math.hypot(dx, dy))
        self.projectiles.append(Projectile(shooter.x, shooter.y, dx / distance * 330, dy / distance * 330, shooter.color))
        self.burst(shooter.x, shooter.y, shooter.color, 3, 55)
        if self.sounds.shots:
            self.sounds.play(self.sounds.shots[self.rng.randrange(len(self.sounds.shots))])
        self.next_shot += self.rng.uniform(0.16, 0.27)

    def collide(self, a: Ball, b: Ball) -> None:
        dx, dy = b.x - a.x, b.y - a.y
        distance = math.hypot(dx, dy)
        minimum = a.radius + b.radius
        if distance <= 0 or distance >= minimum:
            return
        nx, ny = dx / distance, dy / distance
        overlap = minimum - distance
        a.x -= nx * overlap * 0.5
        a.y -= ny * overlap * 0.5
        b.x += nx * overlap * 0.5
        b.y += ny * overlap * 0.5
        relative = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
        if relative < 0:
            impulse = -(1.65 * relative) / 2
            a.vx -= impulse * nx
            a.vy -= impulse * ny
            b.vx += impulse * nx
            b.vy += impulse * ny
        if a.boss or b.boss:
            small = b if a.boss else a
            boss = a if a.boss else b
            impact = abs(relative)
            boss.hp = max(0.0, boss.hp - 0.0028)
            if impact > 150 or (self.time > 23 and self.rng.random() < 0.05):
                small.alive = False
                self.burst(small.x, small.y, small.color, 11, 125)
                self.shake = max(self.shake, 0.12)
                self.sounds.play(self.sounds.pop)

    def move_ball(self, ball: Ball, dt: float) -> None:
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt
        speed = math.hypot(ball.vx, ball.vy)
        max_speed = 340 if ball.boss else 230
        if speed > max_speed:
            ball.vx *= max_speed / speed
            ball.vy *= max_speed / speed
        left, right = 13 + ball.radius, WIDTH - 13 - ball.radius
        top, bottom = 69 + ball.radius, HEIGHT - 22 - ball.radius
        if ball.x < left or ball.x > right:
            ball.x = clamp(ball.x, left, right)
            ball.vx *= -0.96
        if ball.y < top or ball.y > bottom:
            ball.y = clamp(ball.y, top, bottom)
            ball.vy *= -0.96

    def update(self, dt: float) -> None:
        if self.finished:
            self.freeze_time += dt
            return
        self.time += dt
        self.ability_life = max(0.0, self.ability_life - dt)
        self.flash = max(0.0, self.flash - dt)
        self.shake = max(0.0, self.shake - dt)
        if self.time >= self.next_ability and self.time < 27.0:
            self.use_ability()

        alive = [ball for ball in self.minions if ball.alive]
        shooters = [ball for ball in alive if ball.color != BOSS_CORE]
        if self.time >= self.next_shot and shooters:
            self.shoot(shooters)
        if self.time > 25.0:
            for ball in alive:
                dx, dy = self.boss.x - ball.x, self.boss.y - ball.y
                distance = max(1.0, math.hypot(dx, dy))
                ball.vx += dx / distance * 35 * dt
                ball.vy += dy / distance * 35 * dt
        for ball in [self.boss] + alive:
            self.move_ball(ball, dt)
        for index, ball in enumerate(alive):
            self.collide(self.boss, ball)
            for other in alive[index + 1 :]:
                self.collide(ball, other)

        for shot in self.projectiles:
            shot.x += shot.vx * dt
            shot.y += shot.vy * dt
            shot.life -= dt
            if math.hypot(shot.x - self.boss.x, shot.y - self.boss.y) <= self.boss.radius + 3:
                shot.life = 0
                self.boss.hp = max(0.0, self.boss.hp - 0.0045)
                self.burst(shot.x, shot.y, shot.color, 5, 85)
                self.flash = max(self.flash, 0.035)
                self.sounds.play(self.sounds.hit)
        self.projectiles = [
            shot for shot in self.projectiles
            if shot.life > 0 and 8 < shot.x < WIDTH - 8 and 64 < shot.y < HEIGHT - 15
        ]

        if self.time >= GAME_SECONDS or self.boss.hp <= 0:
            survivors = sum(ball.alive and ball.color != BOSS_CORE for ball in self.minions)
            self.winner = "MANY SURVIVE" if self.boss.hp <= 0 else ("BOSS WINS" if survivors <= self.initial_count // 2 else "MANY SURVIVE")
            self.finished = True
            self.flash = 0.5
            self.shake = 0.5
            self.burst(self.boss.x, self.boss.y, BOSS if self.winner == "BOSS WINS" else MINION_COLORS[0], 70, 240)
            self.sounds.play(self.sounds.finish)

        for particle in self.particles:
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.vx *= 0.97
            particle.vy *= 0.97
            particle.life -= dt
        self.particles = [particle for particle in self.particles if particle.life > 0]
        for ring in self.rings:
            ring.radius += ring.speed * dt
            ring.life -= dt
        self.rings = [ring for ring in self.rings if ring.life > 0]


def glow_circle(surface: pygame.Surface, position: Tuple[int, int], radius: int, color: Tuple[int, int, int]) -> None:
    for extra, alpha in ((14, 18), (8, 32), (3, 70)):
        pygame.draw.circle(surface, (*color, alpha), position, radius + extra)
    pygame.draw.circle(surface, color, position, radius)


def draw_centered(surface: pygame.Surface, font: pygame.font.Font, text: str, y: int, color=WHITE) -> None:
    rendered = font.render(text, True, color)
    surface.blit(rendered, (WIDTH // 2 - rendered.get_width() // 2, y))


def render(surface: pygame.Surface, arena: Arena, fonts: Tuple[pygame.font.Font, ...]) -> None:
    title_font, big_font, small_font = fonts
    surface.fill(BG)
    for y in range(75, HEIGHT, 35):
        pygame.draw.line(surface, GRID, (12, y), (WIDTH - 12, y), 1)
    for x in range(12, WIDTH, 35):
        pygame.draw.line(surface, GRID, (x, 70), (x, HEIGHT - 20), 1)
    pygame.draw.rect(surface, (42, 52, 82), (11, 67, WIDTH - 22, HEIGHT - 87), 2, border_radius=18)

    ox = int(arena.rng.uniform(-5, 5)) if arena.shake > 0 else 0
    oy = int(arena.rng.uniform(-5, 5)) if arena.shake > 0 else 0
    layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for ring in arena.rings:
        pygame.draw.circle(layer, (*ring.color, int(170 * ring.life)), (int(ring.x), int(ring.y)), int(ring.radius), 3)
    for particle in arena.particles:
        pygame.draw.circle(layer, (*particle.color, int(255 * clamp(particle.life * 2, 0, 1))), (int(particle.x), int(particle.y)), int(particle.size))
    for shot in arena.projectiles:
        start = (int(shot.x - shot.vx * 0.035), int(shot.y - shot.vy * 0.035))
        end = (int(shot.x), int(shot.y))
        pygame.draw.line(layer, (*shot.color, 110), start, end, 5)
        pygame.draw.circle(layer, WHITE, end, 2)
    for ball in arena.minions:
        if ball.alive:
            glow_circle(layer, (int(ball.x), int(ball.y)), int(ball.radius), ball.color)
            pygame.draw.circle(layer, WHITE, (int(ball.x - 2), int(ball.y - 2)), max(1, int(ball.radius / 4)))
    glow_circle(layer, (int(arena.boss.x), int(arena.boss.y)), int(arena.boss.radius), BOSS)
    pygame.draw.circle(layer, BOSS_CORE, (int(arena.boss.x - 10), int(arena.boss.y - 12)), 11)
    surface.blit(layer, (ox, oy))

    alive = sum(ball.alive and ball.color != BOSS_CORE for ball in arena.minions)
    draw_centered(surface, title_font, "BOSS BOUNCING BALL ARENA", 13)
    pygame.draw.rect(surface, (28, 35, 61), (18, 47, 324, 8), border_radius=4)
    pygame.draw.rect(surface, BOSS, (18, 47, int(324 * arena.boss.hp), 8), border_radius=4)
    surface.blit(small_font.render(f"BOSS  {int(arena.boss.hp * 100):02d}%", True, BOSS_CORE), (18, 57))
    count_text = small_font.render(f"MANY  {alive:02d}", True, MINION_COLORS[0])
    surface.blit(count_text, (WIDTH - 18 - count_text.get_width(), 57))
    time_text = small_font.render(f"{max(0, math.ceil(GAME_SECONDS - arena.time)):02d}s", True, MUTED)
    surface.blit(time_text, (WIDTH // 2 - time_text.get_width() // 2, 57))

    if arena.time <= 1.2:
        panel = pygame.Surface((300, 74), pygame.SRCALPHA)
        pygame.draw.rect(panel, (5, 8, 21, 220), panel.get_rect(), border_radius=15)
        pygame.draw.rect(panel, (*BOSS, 220), panel.get_rect(), 2, border_radius=15)
        surface.blit(panel, (30, 276))
        draw_centered(surface, big_font, "1 VS MANY", 288)
        draw_centered(surface, small_font, "WHO SURVIVES?", 327, MUTED)
    elif arena.ability_life > 0:
        draw_centered(surface, title_font, arena.ability_text, 105, BOSS_CORE)

    if arena.finished:
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((3, 4, 12, 135))
        surface.blit(veil, (0, 0))
        draw_centered(surface, big_font, arena.winner, 282, WHITE)
        draw_centered(surface, small_font, f"SEED {arena.seed}", 326, MUTED)
    if arena.flash > 0:
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 255, 255, int(110 * clamp(arena.flash * 3, 0, 1))))
        surface.blit(flash, (0, 0))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic vertical Boss Bouncing Ball Arena.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--minions", type=int, default=16, choices=range(12, 21))
    parser.add_argument("--record", action="store_true", help="Record a 1080x1920 MP4 through window_recorder.py.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    fonts = (
        pygame.font.SysFont("arialblack", 17),
        pygame.font.SysFont("arialblack", 31),
        pygame.font.SysFont("consolas", 13, bold=True),
    )
    sounds = SoundBank()
    recorder = WindowRecorder(
        enabled=args.record,
        window_title=TITLE,
        output_root=RECORDINGS_DIR,
        session_prefix="boss_arena",
        video_filename="boss_bouncing_ball_arena.mp4",
        music_filename="boss_bouncing_ball_arena_with_music.mp4",
        fps=FPS,
        capture_size=(WIDTH, HEIGHT),
        output_size=EXPORT_SIZE,
        end_delay_seconds=0.0,
        capture_audio=True,
        pipe_video=True,
    )
    arena = Arena(args.seed, args.minions, sounds)
    recorder.new_match()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                arena = Arena(args.seed, args.minions, sounds)
                recorder.new_match()
        arena.update(1.0 / FPS)
        render(screen, arena, fonts)
        pygame.display.flip()
        recorder.start_if_pending()
        if args.record:
            recorder.write_video_frame(pygame.image.tostring(screen, "RGB"))
        recorder.monitor()
        if arena.finished and arena.freeze_time >= FREEZE_SECONDS:
            recorder.stop()
            running = False
        clock.tick(FPS)
    recorder.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
