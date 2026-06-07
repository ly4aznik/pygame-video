import argparse
import math
import os
import random
import sys
from dataclasses import dataclass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from window_recorder import WindowRecorder

import pygame


WIDTH, HEIGHT = 360, 640
FPS = 60
TITLE = "The Gap Is Too Small"
CENTER = pygame.Vector2(WIDTH / 2, 330)
BALL_RADIUS = 9
RING_THICKNESS = 5
RECORDINGS = os.path.join(os.path.dirname(__file__), "window_recordings")

BG = (3, 5, 11)
WHITE = (245, 250, 255)
CYAN = (45, 232, 255)
PINK = (255, 54, 168)
VIOLET = (137, 82, 255)
GOLD = (255, 198, 70)


def clamp(value, low, high):
    return max(low, min(high, value))


def angle_delta(a, b):
    return (a - b + math.pi) % math.tau - math.pi


@dataclass
class Particle:
    pos: pygame.Vector2
    vel: pygame.Vector2
    life: float
    color: tuple
    size: float

    def update(self, dt):
        self.life -= dt
        self.pos += self.vel * dt
        self.vel *= 0.94


@dataclass
class Ring:
    radius: float
    gap_angle: float
    gap_width: float
    speed: float
    color: tuple
    block: bool = False
    broken: bool = False

    def update(self, dt):
        self.gap_angle = (self.gap_angle + self.speed * dt) % math.tau

    def gap_half_angle(self):
        return math.asin(clamp(self.gap_width / (2 * self.radius), 0.02, 0.9))

    def is_in_gap(self, angle, ball_radius=0):
        extra = math.asin(clamp(ball_radius / self.radius, 0, 0.4))
        return abs(angle_delta(angle, self.gap_angle)) < self.gap_half_angle() - extra


class Game:
    def __init__(self, args):
        self.args = args
        self.rng = random.Random(args.seed)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 27, bold=True)
        self.small = pygame.font.SysFont("arial", 12, bold=True)
        self.big = pygame.font.SysFont("arial", 48, bold=True)
        self.recorder = WindowRecorder(
            enabled=args.record,
            window_title=TITLE,
            output_root=RECORDINGS,
            session_prefix="too_small_gap",
            video_filename="too_small_gap.mp4",
            music_filename="too_small_gap_music.mp4",
            fps=30,
            capture_size=(WIDTH, HEIGHT),
            output_size=(1080, 1920),
            end_delay_seconds=0.6,
            pipe_video=True,
        )
        self.reset()

    def reset(self):
        self.elapsed = 0.0
        self.result = ""
        self.result_time = 0.0
        self.near_misses = 0
        self.last_hit = -1.0
        self.final_push = False
        self.trail = []
        self.particles = []
        self.ball = CENTER + pygame.Vector2(*self.args.start)
        self.velocity = pygame.Vector2(self.rng.uniform(75, 115), self.rng.uniform(-20, 20))
        palette = [CYAN, PINK, VIOLET, GOLD]
        self.rings = []
        for i in range(self.args.rings):
            radius = 62 + i * 32
            gap = self.rng.uniform(0, math.tau)
            speed = self.args.rotation * (1 if i % 2 == 0 else -0.78) * (1 + i * 0.08)
            self.rings.append(Ring(radius, gap, self.args.gap, speed, palette[i % len(palette)],
                                   self.args.breakable and i == self.args.rings - 2))
        self.recorder.new_match()

    def sparks(self, point, color, count=9):
        for _ in range(count):
            angle = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(35, 125)
            self.particles.append(Particle(point.copy(), pygame.Vector2(math.cos(angle), math.sin(angle)) * speed,
                                           self.rng.uniform(0.18, 0.42), color, self.rng.uniform(1, 3)))

    def collide_ring(self, ring):
        if ring.broken:
            return
        offset = self.ball - CENTER
        distance = offset.length()
        if distance < 0.001:
            return
        angle = math.atan2(offset.y, offset.x)
        crossed = abs(distance - ring.radius) <= BALL_RADIUS + RING_THICKNESS / 2
        if not crossed:
            return
        if ring.is_in_gap(angle, BALL_RADIUS):
            return
        normal = offset.normalize()
        radial_speed = self.velocity.dot(normal)
        approaching = radial_speed > 0 if distance < ring.radius else radial_speed < 0
        if not approaching:
            return
        if ring.block and self.velocity.length() > 235:
            ring.broken = True
            self.sparks(self.ball, ring.color, 28)
            self.velocity *= 0.78
            return
        tangent = pygame.Vector2(-normal.y, normal.x)
        wall_velocity = tangent * ring.speed * ring.radius
        relative = self.velocity - wall_velocity
        self.velocity = relative - (1 + self.args.bounce) * relative.dot(normal) * normal + wall_velocity
        self.velocity *= 0.992
        self.ball += normal * (-2 if distance < ring.radius else 2)
        self.sparks(self.ball, ring.color)
        if self.elapsed - self.last_hit > 0.18 and abs(angle_delta(angle, ring.gap_angle)) < ring.gap_half_angle() * 1.8:
            self.near_misses += 1
        self.last_hit = self.elapsed

    def update(self, dt):
        if self.result:
            self.result_time += dt
            for particle in self.particles:
                particle.update(dt)
            return
        self.elapsed += dt
        slow = 0.28 if self.args.slowmo and 7.2 < self.elapsed < 7.7 else 1.0
        dt *= slow
        for ring in self.rings:
            ring.update(dt)
        self.velocity.y += self.args.gravity * dt
        self.velocity *= 1 - 0.018 * dt
        # Some seeds create one brief, satisfying alignment near the finale.
        if self.args.seed % 4 == 0 and 7.45 < self.elapsed < 8.05:
            outward = (self.ball - CENTER).normalize()
            escape_angle = math.atan2(outward.y, outward.x)
            for ring in self.rings:
                ring.gap_angle = escape_angle
            if self.elapsed > 7.68:
                self.velocity = outward * 390
                self.final_push = True
        self.ball += self.velocity * dt
        for ring in self.rings:
            self.collide_ring(ring)
        self.trail.append(self.ball.copy())
        self.trail = self.trail[-18:]
        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        outer = self.rings[-1].radius
        if (self.ball - CENTER).length() > outer + 35:
            self.result = "ESCAPED"
            self.result_time = 0
            self.sparks(self.ball, WHITE, 45)
        elif self.elapsed >= self.args.duration:
            self.result = "TRAPPED"
            self.result_time = 0
        if self.result and self.result_time == 0:
            print(f"{self.result} at {self.elapsed:.2f}s (seed={self.args.seed}, near_misses={self.near_misses})")

    def draw_arc(self, ring, glow=False):
        if ring.broken:
            return
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        rect = pygame.Rect(CENTER.x - ring.radius, CENTER.y - ring.radius, ring.radius * 2, ring.radius * 2)
        half = ring.gap_half_angle()
        color = (*ring.color, 35 if glow else 245)
        width = 13 if glow else RING_THICKNESS
        pygame.draw.arc(layer, color, rect, ring.gap_angle + half, ring.gap_angle + math.tau - half, width)
        for sign in (-1, 1):
            a = ring.gap_angle + sign * half
            p = CENTER + pygame.Vector2(math.cos(a), math.sin(a)) * ring.radius
            pygame.draw.circle(layer, color, p, width // 2)
        self.screen.blit(layer, (0, 0))

    def draw(self):
        self.screen.fill(BG)
        for y in range(0, HEIGHT, 32):
            pygame.draw.line(self.screen, (7, 12, 22), (0, y), (WIDTH, y), 1)
        for ring in self.rings:
            self.draw_arc(ring, True)
            self.draw_arc(ring)
            if ring.block and not ring.broken:
                a = ring.gap_angle + ring.gap_half_angle() * 1.45
                p = CENTER + pygame.Vector2(math.cos(a), math.sin(a)) * ring.radius
                pygame.draw.rect(self.screen, ring.color, (p.x - 7, p.y - 7, 14, 14), border_radius=3)
        for i, point in enumerate(self.trail):
            radius = max(1, int(BALL_RADIUS * (i + 1) / len(self.trail) * 0.75))
            pygame.draw.circle(self.screen, (18, 82 + i * 5, 110 + i * 7), point, radius)
        for particle in self.particles:
            alpha = int(255 * clamp(particle.life / 0.4, 0, 1))
            layer = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*particle.color, alpha), (5, 5), max(1, int(particle.size)))
            self.screen.blit(layer, particle.pos - pygame.Vector2(5, 5))
        pygame.draw.circle(self.screen, (55, 220, 255), self.ball, BALL_RADIUS + 8)
        pygame.draw.circle(self.screen, WHITE, self.ball, BALL_RADIUS)
        pygame.draw.circle(self.screen, (255, 255, 255), self.ball - pygame.Vector2(3, 3), 3)
        hook_alpha = clamp(1 - self.elapsed / 2.2, 0, 1)
        if hook_alpha:
            text = self.font.render("The gap is too small", True, WHITE)
            self.screen.blit(text, text.get_rect(center=(WIDTH / 2, 40)))
        label = self.small.render(f"SEED {self.args.seed}   NEAR MISSES {self.near_misses}", True, (100, 130, 155))
        self.screen.blit(label, label.get_rect(center=(WIDTH / 2, HEIGHT - 20)))
        if self.result:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, min(150, int(self.result_time * 300))))
            self.screen.blit(overlay, (0, 0))
            color = CYAN if self.result == "ESCAPED" else PINK
            result = self.big.render(self.result, True, color)
            self.screen.blit(result, result.get_rect(center=(WIDTH / 2, HEIGHT / 2)))

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    self.reset()
            dt = min(self.clock.tick(FPS) / 1000, 1 / 30)
            self.update(dt)
            self.draw()
            pygame.display.flip()
            self.recorder.start_if_pending()
            if self.recorder.needs_video_frame():
                self.recorder.write_video_frame(pygame.image.tostring(self.screen, "RGB"))
            self.recorder.monitor()
            if self.result:
                self.recorder.stop_after_game_over(self.result_time)
                if self.result_time > 1.15:
                    running = False
        self.recorder.stop()
        pygame.quit()


def parse_args():
    parser = argparse.ArgumentParser(description="Viral rotating-ring physics simulation")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--gap", type=float, default=23, help="Gap width in pixels")
    parser.add_argument("--rotation", type=float, default=0.72, help="Base ring rotation speed")
    parser.add_argument("--rings", type=int, default=5)
    parser.add_argument("--gravity", type=float, default=125)
    parser.add_argument("--bounce", type=float, default=0.91)
    parser.add_argument("--start", type=float, nargs=2, default=(-16, -12), metavar=("X", "Y"))
    parser.add_argument("--duration", type=float, default=9.4)
    parser.add_argument("--breakable", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--slowmo", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--record", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    pygame.init()
    Game(parse_args()).run()
