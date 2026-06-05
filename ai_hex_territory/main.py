import argparse
import math
import os
import random
import struct
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from window_recorder import WindowRecorder

import pygame


# ---------------------------
# Quick variation parameters
# ---------------------------
RANDOM_SEED = 41
GRID_COLS = 18
GRID_ROWS = 25
FACTION_COUNT = 4
GROWTH_STYLE = "probabilistic"  # flood, directional, probabilistic
CENTER_WEIGHT = 1.7
NEUTRAL_DENSITY = 0.035
FACTION_SPEEDS = (1.10, 0.96, 1.16, 1.03)
START_POSITIONS: Sequence[Tuple[int, int]] = ()

WIDTH, HEIGHT = 360, 640
EXPORT_SIZE = (1080, 1920)
FPS = 60
MATCH_SECONDS = 27.0
FINAL_SECONDS = 3.0
INACTIVITY_FINISH_SECONDS = 1.5
WINDOW_TITLE = "Who Will Claim The Most Cells?"
WINDOW_RECORD_FPS = 30
WINDOW_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_recordings")
DEFAULT_RECORD_AUDIO_SOURCE = "CABLE Output (VB-Audio Virtual Cable)"

# Calm Reels palette from DESIGN_GUIDE.md.
BG = (246, 248, 242)
PANEL = (255, 255, 250)
PANEL_LIGHT = (250, 252, 247)
GRID = (222, 228, 218)
TEXT = (42, 50, 62)
MUTED = (126, 137, 139)
DANGER = (210, 93, 96)
NEUTRAL = (247, 249, 244)
BLOCK = (174, 183, 180)
GOLD = (221, 177, 76)

FACTION_DATA = [
    ("RED", (198, 104, 101), "CENTER RUSH"),
    ("BLUE", (92, 139, 184), "SAFE CLUSTERS"),
    ("GREEN", (104, 166, 129), "EDGE RUNNER"),
    ("YELLOW", (221, 177, 76), "WILD CARD"),
]

Cell = Tuple[int, int]
Color = Tuple[int, int, int]
EVEN_ROW_DIRS: Sequence[Cell] = ((1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1))
ODD_ROW_DIRS: Sequence[Cell] = ((1, 0), (1, -1), (0, -1), (-1, 0), (0, 1), (1, 1))

BOARD_TOP = 108
BOARD_BOTTOM = 575


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mix(a: Color, b: Color, amount: float) -> Color:
    return tuple(int(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def add_cell(a: Cell, b: Cell) -> Cell:
    return a[0] + b[0], a[1] + b[1]


def hex_distance(a: Cell, b: Cell) -> int:
    ax = a[0] - (a[1] - (a[1] & 1)) // 2
    az = a[1]
    ay = -ax - az
    bx = b[0] - (b[1] - (b[1] & 1)) // 2
    bz = b[1]
    by = -bx - bz
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def make_tone(pitch: float, duration: float, volume: float, rise: float = 0.0) -> pygame.mixer.Sound:
    sample_rate = 44100
    frames = bytearray()
    count = int(sample_rate * duration)
    for index in range(count):
        progress = index / count
        envelope = math.sin(math.pi * progress) ** 0.65 * (1.0 - progress) ** 0.55
        frequency = pitch * (1.0 + rise * progress)
        wave = math.sin(math.tau * frequency * index / sample_rate)
        wave += 0.18 * math.sin(math.tau * frequency * 2 * index / sample_rate)
        sample = int(clamp(wave * envelope * volume, -1.0, 1.0) * 32767)
        frames.extend(struct.pack("<h", sample))
    return pygame.mixer.Sound(buffer=bytes(frames))


class SoundBank:
    def __init__(self, volume: float) -> None:
        self.enabled = False
        self.claim: List[pygame.mixer.Sound] = []
        self.center: Optional[pygame.mixer.Sound] = None
        self.clash: Optional[pygame.mixer.Sound] = None
        self.win: Optional[pygame.mixer.Sound] = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self.claim = [make_tone(pitch, 0.045, volume * 0.24, 0.08) for pitch in (330, 390, 460, 540)]
            self.center = make_tone(680, 0.20, volume * 0.6, 0.45)
            self.clash = make_tone(240, 0.09, volume * 0.42, -0.25)
            self.win = make_tone(520, 0.55, volume * 0.7, 0.85)
            self.enabled = True
        except pygame.error:
            pass

    def play_claim(self, faction_id: int) -> None:
        if self.enabled:
            self.claim[faction_id % len(self.claim)].play()

    def play_center(self) -> None:
        if self.enabled and self.center:
            self.center.play()

    def play_clash(self) -> None:
        if self.enabled and self.clash:
            self.clash.play()

    def play_win(self) -> None:
        if self.enabled and self.win:
            self.win.play()


@dataclass
class Pulse:
    cell: Cell
    color: Color
    life: float = 0.52
    max_life: float = 0.52


@dataclass
class Trail:
    start: Cell
    end: Cell
    color: Color
    life: float = 0.34
    max_life: float = 0.34


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: Color
    life: float
    max_life: float


@dataclass
class Faction:
    faction_id: int
    name: str
    color: Color
    behavior: str
    speed: float
    home: Cell
    territory: Set[Cell] = field(default_factory=set)
    frontier: Set[Cell] = field(default_factory=set)
    energy: float = 0.0
    center_cells: int = 0
    last_source: Optional[Cell] = None


class HexTerritory:
    def __init__(
        self,
        seed: int = RANDOM_SEED,
        cols: int = GRID_COLS,
        rows: int = GRID_ROWS,
        faction_count: int = FACTION_COUNT,
        growth_style: str = GROWTH_STYLE,
        center_weight: float = CENTER_WEIGHT,
        neutral_density: float = NEUTRAL_DENSITY,
        faction_speeds: Sequence[float] = FACTION_SPEEDS,
        start_positions: Sequence[Cell] = START_POSITIONS,
        sounds: Optional[SoundBank] = None,
    ) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.cols = int(clamp(cols, 12, 24))
        self.rows = int(clamp(rows, 16, 32))
        self.faction_count = int(clamp(faction_count, 3, 4))
        self.growth_style = growth_style if growth_style in ("flood", "directional", "probabilistic") else GROWTH_STYLE
        self.center_weight = clamp(center_weight, 0.0, 3.0)
        self.neutral_density = clamp(neutral_density, 0.0, 0.16)
        self.sounds = sounds

        self.radius = min(9.2, 330 / (math.sqrt(3) * (self.cols + 0.5)), 445 / (1.5 * self.rows + 0.5))
        self.board_width = math.sqrt(3) * self.radius * (self.cols + 0.5)
        self.board_height = self.radius * (1.5 * self.rows + 0.5)
        self.board_left = (WIDTH - self.board_width) / 2
        self.board_top = BOARD_TOP + (BOARD_BOTTOM - BOARD_TOP - self.board_height) / 2

        self.cells: Set[Cell] = {(q, r) for q in range(self.cols) for r in range(self.rows)}
        self.center = (self.cols // 2, self.rows // 2)
        self.center_region = {cell for cell in self.cells if hex_distance(cell, self.center) <= 2}
        self.owner: Dict[Cell, int] = {}
        self.blocked = self.make_blocks()
        supplied_starts = [cell for cell in start_positions if cell in self.cells]
        starts = supplied_starts if len(supplied_starts) >= self.faction_count else self.default_starts()
        speeds = list(faction_speeds) + list(FACTION_SPEEDS)
        self.factions = [
            Faction(index, *FACTION_DATA[index], speed=clamp(speeds[index], 0.35, 2.2), home=starts[index])
            for index in range(self.faction_count)
        ]

        self.elapsed = 0.0
        self.final_elapsed = 0.0
        self.last_action_at = 0.8
        self.done = False
        self.winner: Optional[Faction] = None
        self.pulses: List[Pulse] = []
        self.trails: List[Trail] = []
        self.particles: List[Particle] = []
        self.center_owner: Optional[int] = None
        self.center_sound_owner: Optional[int] = None
        self.last_claim_sound = -1.0
        self.last_clash_sound = -1.0
        self.fonts: Dict[Tuple[int, bool], pygame.font.Font] = {}

        for faction in self.factions:
            self.seed_base(faction)

    def default_starts(self) -> List[Cell]:
        corners = [(1, 1), (self.cols - 2, self.rows - 2), (1, self.rows - 2), (self.cols - 2, 1)]
        if self.faction_count == 3:
            return [corners[0], corners[1], corners[2]]
        return corners

    def make_blocks(self) -> Set[Cell]:
        candidates = [cell for cell in self.cells if hex_distance(cell, self.center) > 3]
        self.rng.shuffle(candidates)
        return set(candidates[: int(len(self.cells) * self.neutral_density)])

    def seed_base(self, faction: Faction) -> None:
        base = {faction.home}
        base.update(cell for cell in self.neighbors(faction.home) if cell not in self.blocked)
        self.blocked.difference_update(base)
        for cell in base:
            self.owner[cell] = faction.faction_id
        faction.territory = base
        faction.frontier = set(base)

    def neighbors(self, cell: Cell) -> List[Cell]:
        directions = ODD_ROW_DIRS if cell[1] & 1 else EVEN_ROW_DIRS
        return [other for direction in directions if (other := add_cell(cell, direction)) in self.cells]

    def cell_center(self, cell: Cell) -> Tuple[float, float]:
        q, r = cell
        x = self.board_left + self.radius * math.sqrt(3) * (q + 0.5 * (r & 1) + 0.5)
        y = self.board_top + self.radius * (1.5 * r + 1.0)
        return x, y

    def score_candidate(self, faction: Faction, source: Cell, target: Cell, attack: bool) -> float:
        neutral_neighbors = sum(1 for cell in self.neighbors(target) if cell not in self.owner and cell not in self.blocked)
        friendly_neighbors = sum(1 for cell in self.neighbors(target) if self.owner.get(cell) == faction.faction_id)
        edge_distance = min(target[0], target[1], self.cols - 1 - target[0], self.rows - 1 - target[1])
        center_distance = hex_distance(target, self.center)
        score = self.rng.random() * 2.4

        if faction.faction_id == 0:  # red: aggressive center rush
            score += (self.cols + self.rows - center_distance) * 0.18 + (3.4 if attack else 0.0)
        elif faction.faction_id == 1:  # blue: prefers stable clusters
            score += friendly_neighbors * 1.55 + neutral_neighbors * 0.35 - (2.0 if attack else 0.0)
        elif faction.faction_id == 2:  # green: runs around the rim
            score += max(0, 7 - edge_distance) * 1.15 + neutral_neighbors * 0.42
        else:  # yellow: intentionally volatile
            score += self.rng.uniform(-4.5, 6.0) + (3.2 if attack and self.rng.random() < 0.55 else 0.0)

        if self.growth_style == "flood":
            score += friendly_neighbors * 0.75 + neutral_neighbors * 0.45
        elif self.growth_style == "directional":
            home_to_target = hex_distance(faction.home, target)
            home_to_source = hex_distance(faction.home, source)
            score += (home_to_target - home_to_source) * 2.1
        return score

    def pick_move(self, faction: Faction) -> Optional[Tuple[Cell, Cell, bool]]:
        candidates: List[Tuple[float, Cell, Cell, bool]] = []
        sources = list(faction.frontier)
        self.rng.shuffle(sources)
        for source in sources[: max(20, len(sources))]:
            for target in self.neighbors(source):
                if target in self.blocked or self.owner.get(target) == faction.faction_id:
                    continue
                attack = target in self.owner
                if attack:
                    enemy = self.factions[self.owner[target]]
                    friendly = sum(1 for cell in self.neighbors(target) if self.owner.get(cell) == faction.faction_id)
                    hostile = sum(1 for cell in self.neighbors(target) if self.owner.get(cell) == enemy.faction_id)
                    chance = 0.12 + friendly * 0.09 - hostile * 0.045
                    if faction.faction_id in (0, 3):
                        chance += 0.12
                    if self.elapsed < 9.5:
                        chance *= 0.25
                    if self.rng.random() > chance:
                        continue
                candidates.append((self.score_candidate(faction, source, target, attack), source, target, attack))
        if not candidates:
            return None
        candidates.sort(reverse=True, key=lambda item: item[0])
        pool = candidates[: min(8, len(candidates))]
        weights = [max(0.1, item[0] - pool[-1][0] + 0.6) for item in pool]
        _, source, target, attack = self.rng.choices(pool, weights=weights, k=1)[0]
        return source, target, attack

    def claim(self, faction: Faction, source: Cell, target: Cell, attack: bool) -> None:
        self.last_action_at = self.elapsed
        previous_owner = self.owner.get(target)
        if previous_owner is not None:
            enemy = self.factions[previous_owner]
            enemy.territory.discard(target)
            enemy.frontier.discard(target)
        self.owner[target] = faction.faction_id
        faction.territory.add(target)
        faction.frontier.add(target)
        faction.last_source = source
        for cell in self.neighbors(target):
            if self.owner.get(cell) == faction.faction_id:
                if all(neighbor in self.owner for neighbor in self.neighbors(cell)):
                    faction.frontier.discard(cell)

        self.pulses.append(Pulse(target, faction.color))
        self.trails.append(Trail(source, target, faction.color))
        x, y = self.cell_center(target)
        for _ in range(3 if attack else 1):
            angle = self.rng.random() * math.tau
            speed = self.rng.uniform(8, 22)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, faction.color, 0.42, 0.42))
        if self.sounds and self.elapsed - self.last_claim_sound > 0.07:
            self.sounds.play_claim(faction.faction_id)
            self.last_claim_sound = self.elapsed
        if attack and self.sounds and self.elapsed - self.last_clash_sound > 0.45:
            self.sounds.play_clash()
            self.last_clash_sound = self.elapsed

    def update_center_control(self) -> None:
        counts = [sum(1 for cell in self.center_region if self.owner.get(cell) == f.faction_id) for f in self.factions]
        for faction, count in zip(self.factions, counts):
            faction.center_cells = count
        leader = max(range(len(counts)), key=counts.__getitem__)
        required = max(3, len(self.center_region) // 3)
        self.center_owner = leader if counts[leader] >= required and counts.count(counts[leader]) == 1 else None
        if self.center_owner is not None and self.center_owner != self.center_sound_owner:
            if self.sounds:
                self.sounds.play_center()
            self.center_sound_owner = self.center_owner

    def update(self, dt: float) -> None:
        if self.done:
            self.final_elapsed += dt
            return
        self.elapsed += dt
        if self.elapsed < 0.8:
            self.update_effects(dt)
            return
        aggression_ramp = 0.86 + min(1.25, self.elapsed / 11.0)
        fill_ramp = 1.0 + max(0.0, self.elapsed - 19.0) * 0.12
        for faction in self.factions:
            boost = 1.0 + faction.center_cells * 0.025 * self.center_weight
            faction.energy += dt * 12.0 * faction.speed * aggression_ramp * fill_ramp * boost
            while faction.energy >= 1.0:
                faction.energy -= 1.0
                move = self.pick_move(faction)
                if move:
                    self.claim(faction, *move)

        self.update_center_control()
        self.update_effects(dt)
        no_actions = self.elapsed - self.last_action_at >= INACTIVITY_FINISH_SECONDS
        if self.elapsed >= MATCH_SECONDS or no_actions:
            self.finish_match()

    def finish_match(self) -> None:
        if self.done:
            return
        self.done = True
        self.winner = max(self.factions, key=lambda faction: len(faction.territory))
        if self.sounds:
            self.sounds.play_win()

    def update_effects(self, dt: float) -> None:
        for pulse in self.pulses:
            pulse.life -= dt
        self.pulses = [pulse for pulse in self.pulses if pulse.life > 0]
        for trail in self.trails:
            trail.life -= dt
        self.trails = [trail for trail in self.trails if trail.life > 0]
        for particle in self.particles:
            particle.life -= dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.vx *= 0.95
            particle.vy *= 0.95
        self.particles = [particle for particle in self.particles if particle.life > 0]

    def get_font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = size, bold
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("arial", size, bold=bold)
        return self.fonts[key]

    def hex_points(self, cell: Cell, scale: float = 1.0) -> List[Tuple[int, int]]:
        cx, cy = self.cell_center(cell)
        radius = self.radius * scale
        return [
            (int(cx + math.cos(math.radians(60 * index - 30)) * radius), int(cy + math.sin(math.radians(60 * index - 30)) * radius))
            for index in range(6)
        ]

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(BG)
        self.draw_header(surface)
        self.draw_board(surface)
        self.draw_effects(surface)
        self.draw_hud(surface)
        self.draw_score_table(surface)
        if self.done:
            self.draw_final(surface)

    def draw_header(self, surface: pygame.Surface) -> None:
        title = self.get_font(19, True).render("HEX TERRITORY", True, TEXT)
        surface.blit(title, (16, 11))
        hook = self.get_font(9, True).render("Who will claim the most cells?", True, MUTED)
        surface.blit(hook, (17, 35))
        phase = "FINAL RESULT" if self.done else ("BATTLE FOR THE CORE" if self.elapsed >= 10 else "TERRITORY RUSH")
        phase_color = GOLD if self.elapsed >= 10 else MUTED
        surface.blit(self.get_font(7, True).render(phase, True, phase_color), (17, 51))
        timer_label = "DONE" if self.done else f"{max(0, math.ceil(MATCH_SECONDS - self.elapsed)):02d}s"
        timer = self.get_font(12, True).render(timer_label, True, TEXT)
        surface.blit(timer, timer.get_rect(topright=(344, 14)))

    def draw_board(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(8, int(self.board_top - 10), 344, int(self.board_height + 20))
        pygame.draw.rect(surface, PANEL, panel, border_radius=14)
        pygame.draw.rect(surface, GRID, panel, 1, border_radius=14)

        for cell in self.cells:
            owner = self.owner.get(cell)
            if cell in self.blocked:
                fill = BLOCK
            elif owner is None:
                fill = NEUTRAL
            else:
                fill = mix(self.factions[owner].color, PANEL, 0.08)
            border = mix(fill, TEXT, 0.08) if owner is not None else GRID
            pygame.draw.polygon(surface, fill, self.hex_points(cell, 0.91))
            pygame.draw.polygon(surface, border, self.hex_points(cell, 0.91), 1)

        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 3.5)
        core_color = self.factions[self.center_owner].color if self.center_owner is not None else GOLD
        for cell in self.center_region:
            layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.polygon(layer, (*core_color, int(28 + pulse * 24)), self.hex_points(cell, 1.08), 2)
            surface.blit(layer, (0, 0))
        cx, cy = self.cell_center(self.center)
        label = self.get_font(7, True).render("CORE xBOOST", True, mix(core_color, TEXT, 0.15))
        surface.blit(label, label.get_rect(center=(cx, cy - self.radius * 3.1)))

    def draw_effects(self, surface: pygame.Surface) -> None:
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for trail in self.trails:
            alpha = int(62 * trail.life / trail.max_life)
            pygame.draw.line(layer, (*trail.color, alpha), self.cell_center(trail.start), self.cell_center(trail.end), 2)
        for pulse in self.pulses:
            progress = 1.0 - pulse.life / pulse.max_life
            alpha = int(100 * (1.0 - progress))
            pygame.draw.polygon(layer, (*pulse.color, alpha), self.hex_points(pulse.cell, 0.95 + progress * 0.40), 2)
        for particle in self.particles:
            alpha = int(125 * particle.life / particle.max_life)
            pygame.draw.circle(layer, (*particle.color, alpha), (int(particle.x), int(particle.y)), 2)
        surface.blit(layer, (0, 0))

    def draw_hud(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(190, 53, 154, 50)
        pygame.draw.rect(surface, PANEL_LIGHT, panel, border_radius=9)
        pygame.draw.rect(surface, GRID, panel, 1, border_radius=9)
        available = max(1, len(self.cells - self.blocked))
        for index, faction in enumerate(self.factions):
            col, row = index % 2, index // 2
            x = panel.left + 7 + col * 73
            y = panel.top + 7 + row * 20
            pygame.draw.circle(surface, faction.color, (x + 4, y + 5), 4)
            percent = len(faction.territory) / available * 100
            surface.blit(self.get_font(8, True).render(f"{faction.name} {percent:4.1f}%", True, TEXT), (x + 11, y))

        total = sum(len(faction.territory) for faction in self.factions)
        bar = pygame.Rect(16, 78, 158, 8)
        pygame.draw.rect(surface, PANEL_LIGHT, bar, border_radius=4)
        cursor = bar.left
        for faction in self.factions:
            width = int(bar.width * len(faction.territory) / max(1, total))
            pygame.draw.rect(surface, faction.color, (cursor, bar.top, width, bar.height), border_radius=3)
            cursor += width
        surface.blit(self.get_font(7, True).render("LIVE TERRITORY", True, MUTED), (16, 91))

    def draw_score_table(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(16, 540, 328, 84)
        pygame.draw.rect(surface, PANEL, panel, border_radius=11)
        pygame.draw.rect(surface, GRID, panel, 1, border_radius=11)
        available = max(1, len(self.cells - self.blocked))
        for index, faction in enumerate(self.factions):
            col, row = index % 2, index // 2
            x = panel.left + 10 + col * 158
            y = panel.top + 10 + row * 34
            pygame.draw.circle(surface, faction.color, (x + 5, y + 6), 5)
            surface.blit(self.get_font(9, True).render(faction.name, True, TEXT), (x + 15, y))
            percent = len(faction.territory) / available * 100
            value = self.get_font(9, True).render(f"{percent:.1f}%", True, faction.color)
            surface.blit(value, value.get_rect(topright=(x + 145, y)))
            surface.blit(self.get_font(7).render(faction.behavior, True, MUTED), (x + 15, y + 14))

    def draw_final(self, surface: pygame.Surface) -> None:
        if not self.winner:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((255, 255, 250, 174))
        surface.blit(overlay, (0, 0))
        card = pygame.Rect(38, 202, 284, 240)
        pygame.draw.rect(surface, PANEL, card, border_radius=20)
        pygame.draw.rect(surface, GRID, card, 1, border_radius=20)
        pygame.draw.rect(surface, self.winner.color, (card.left, card.top, 5, card.height), border_radius=3)
        surface.blit(self.get_font(10, True).render("WINNER", True, MUTED), (card.left + 18, card.top + 17))
        winner_text = self.get_font(29, True).render(self.winner.name, True, self.winner.color)
        surface.blit(winner_text, (card.left + 17, card.top + 35))
        surface.blit(self.get_font(9, True).render(self.winner.behavior, True, TEXT), (card.left + 19, card.top + 69))

        available = max(1, len(self.cells - self.blocked))
        standings = sorted(self.factions, key=lambda faction: len(faction.territory), reverse=True)
        for index, faction in enumerate(standings):
            y = card.top + 104 + index * 28
            pygame.draw.circle(surface, faction.color, (card.left + 22, y + 6), 5)
            surface.blit(self.get_font(10, True).render(f"{index + 1}. {faction.name}", True, TEXT), (card.left + 34, y))
            percent = len(faction.territory) / available * 100
            value = self.get_font(11, True).render(f"{percent:.1f}%", True, faction.color)
            surface.blit(value, value.get_rect(topright=(card.right - 18, y - 1)))
        footer = self.get_font(8, True).render("PRESS R FOR A NEW BATTLE", True, MUTED)
        surface.blit(footer, footer.get_rect(center=(WIDTH // 2, card.bottom - 17)))


def parse_speed_list(value: str) -> Tuple[float, ...]:
    try:
        return tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("speeds must be comma-separated numbers") from exc


def parse_start_list(value: str) -> Tuple[Cell, ...]:
    try:
        starts: List[Cell] = []
        for item in value.split(","):
            axes = tuple(int(axis.strip()) for axis in item.split(":"))
            if len(axes) != 2:
                raise ValueError
            starts.append((axes[0], axes[1]))
        return tuple(starts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("starts must look like 1:1,16:23,1:23,16:1") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vertical hex territory battle for Reels")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--cols", type=int, default=GRID_COLS)
    parser.add_argument("--rows", type=int, default=GRID_ROWS)
    parser.add_argument("--factions", type=int, choices=(3, 4), default=FACTION_COUNT)
    parser.add_argument("--style", choices=("flood", "directional", "probabilistic"), default=GROWTH_STYLE)
    parser.add_argument("--center-weight", type=float, default=CENTER_WEIGHT)
    parser.add_argument("--neutral-density", type=float, default=NEUTRAL_DENSITY)
    parser.add_argument("--speeds", type=parse_speed_list, default=FACTION_SPEEDS, help="comma-separated faction speeds")
    parser.add_argument("--starts", type=parse_start_list, default=START_POSITIONS, help="q:r pairs separated by commas")
    parser.add_argument("--headless-test", action="store_true")
    parser.add_argument("--record-window", action="store_true", help="record 1080x1920 MP4 with ffmpeg")
    parser.add_argument("--record-fps", type=int, default=WINDOW_RECORD_FPS)
    parser.add_argument("--record-dir", default=WINDOW_RECORDINGS_DIR)
    parser.add_argument("--record-audio-source", default=DEFAULT_RECORD_AUDIO_SOURCE)
    parser.add_argument("--record-audio-volume", type=float, default=1.0)
    parser.add_argument("--sfx-volume", type=float, default=0.42)
    return parser.parse_args()


def game_options(args: argparse.Namespace) -> dict:
    return {
        "cols": args.cols,
        "rows": args.rows,
        "faction_count": args.factions,
        "growth_style": args.style,
        "center_weight": args.center_weight,
        "neutral_density": args.neutral_density,
        "faction_speeds": args.speeds,
        "start_positions": args.starts,
    }


def run_headless(game: HexTerritory) -> None:
    while not game.done:
        game.update(1 / FPS)
    available = max(1, len(game.cells - game.blocked))
    standings = sorted(game.factions, key=lambda faction: len(faction.territory), reverse=True)
    result = ", ".join(f"{faction.name}={len(faction.territory) / available * 100:.1f}%" for faction in standings)
    print(f"seed={game.seed} winner={game.winner.name if game.winner else 'none'} filled={len(game.owner) / available * 100:.1f}% {result}")


def main() -> None:
    args = parse_args()
    pygame.mixer.pre_init(44100, -16, 1, 512)
    pygame.init()
    pygame.font.init()
    options = game_options(args)
    if args.headless_test:
        run_headless(HexTerritory(args.seed, **options))
        pygame.quit()
        return

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()
    sounds = SoundBank(args.sfx_volume)
    game = HexTerritory(args.seed, sounds=sounds, **options)
    recorder = WindowRecorder(
        enabled=args.record_window,
        window_title=WINDOW_TITLE,
        output_root=args.record_dir,
        session_prefix="hex_territory",
        video_filename="hex_territory.mp4",
        music_filename="hex_territory_music.mp4",
        fps=args.record_fps,
        capture_size=(WIDTH, HEIGHT),
        output_size=EXPORT_SIZE,
        end_delay_seconds=FINAL_SECONDS,
        capture_audio=args.record_window,
        audio_source=args.record_audio_source,
        audio_backend="dshow",
        audio_volume=args.record_audio_volume,
        pipe_video=True,
    )
    recorder.new_match()
    paused = False
    running = True
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
                    game = HexTerritory(args.seed, sounds=sounds, **options)
                    recorder.new_match()
                elif event.key == pygame.K_s:
                    pygame.image.save(screen, f"hex_territory_seed_{args.seed}.png")
        if not paused:
            game.update(dt)
        if game.done:
            recorder.stop_after_game_over(game.final_elapsed)
        game.draw(screen)
        pygame.display.flip()
        recorder.start_if_pending()
        if recorder.needs_video_frame():
            recorder.write_video_frame(pygame.image.tobytes(screen, "RGB"))
    recorder.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
