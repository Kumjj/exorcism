from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
import math
import random
from typing import Deque, Iterable, Optional, Sequence, TypeAlias


Pattern = tuple[int, ...]
PatternAttempt: TypeAlias = Pattern | tuple[Pattern, Pattern]
PATTERN_POOL: tuple[Pattern, ...] = (
    (0, 1, 2),
    (0, 3, 6),
    (2, 5, 8),
    (6, 7, 8),
    (0, 4, 8),
    (2, 4, 6),
    (1, 4, 7),
    (3, 4, 5),
    (0, 1, 4, 7),
    (2, 1, 4, 7),
    (0, 3, 4, 5),
    (6, 3, 4, 2),
    (0, 1, 4),
    (2, 1, 4),
    (6, 3, 4),
    (8, 5, 4),
    (0, 4, 5),
    (2, 4, 3),
    (6, 4, 1),
    (8, 4, 7),
    (0, 1, 5),
    (2, 1, 3),
    (6, 7, 5),
    (8, 7, 3),
    (0, 4, 7),
    (2, 4, 7),
    (6, 4, 5),
    (8, 4, 3),
    (0, 3, 4, 1),
    (2, 5, 4, 1),
    (6, 3, 4, 7),
    (8, 5, 4, 7),
)
COMPLEX_PATTERN_POOL: tuple[Pattern, ...] = (
    (0, 1, 2, 5, 4, 3, 6, 7, 8),
    (0, 3, 6, 7, 4, 1, 2, 5, 8),
    (2, 1, 0, 3, 4, 5, 8, 7, 6),
    (6, 3, 0, 1, 4, 7, 8, 5, 2),
    (0, 4, 2, 5, 8, 7, 3),
    (2, 4, 0, 3, 6, 7, 5),
    (6, 4, 8, 5, 2, 1, 3),
    (8, 4, 6, 3, 0, 1, 5),
    (1, 0, 3, 4, 5, 8, 7),
    (3, 0, 1, 4, 7, 8, 5),
    (5, 2, 1, 4, 3, 6, 7),
    (7, 6, 3, 4, 1, 2, 5),
    (0, 4, 1, 2, 5, 8),
    (2, 4, 5, 8, 7, 6),
    (6, 4, 3, 0, 1, 2),
    (8, 4, 7, 6, 3, 0),
)
LAYERED_PATTERN_POOL: tuple[tuple[Pattern, Pattern], ...] = (
    ((0, 1, 2), (6, 7, 8)),
    ((0, 3, 6), (2, 5, 8)),
    ((0, 4, 8), (2, 4, 6)),
    ((1, 4, 7), (3, 4, 5)),
)


class PatternResult(Enum):
    HIT = auto()
    RESONATED = auto()
    MISSED = auto()
    SPELL = auto()
    EMPTY = auto()


class GhostKind(Enum):
    SLOWPOKE = auto()
    START_LOCKED = auto()
    BLINKING = auto()
    WAVY = auto()
    FORBIDDEN = auto()
    PARTIAL = auto()
    CREEP = auto()
    CREASE = auto()
    SNARL = auto()


class SpellType(Enum):
    HEAL = auto()
    REPEL = auto()
    NULLIFY = auto()
    TRUTH = auto()


@dataclass(frozen=True)
class SpellDefinition:
    spell_type: SpellType
    name: str
    pattern: Pattern
    cost: int
    description: str
    cooldown: float


def pattern_edges(pattern: Pattern) -> frozenset[tuple[int, int]]:
    return frozenset(
        tuple(sorted((first, second)))
        for first, second in zip(pattern, pattern[1:])
    )


def layered_pattern_signature(layers: tuple[Pattern, Pattern]) -> tuple[frozenset[int], frozenset[tuple[int, int]]]:
    nodes = frozenset(node for layer in layers for node in layer)
    edges = frozenset(edge for layer in layers for edge in pattern_edges(layer))
    return nodes, edges


def patterns_match(entered: Pattern, expected: Pattern, strict_start: bool = False) -> bool:
    if entered == expected:
        return True
    return not strict_start and entered == tuple(reversed(expected))


def pattern_attempt_matches(
    entered: PatternAttempt,
    expected: PatternAttempt,
    strict_start: bool = False,
) -> bool:
    if isinstance(expected[0], tuple):
        if not isinstance(entered[0], tuple):
            return False
        return layered_pattern_signature(entered) == layered_pattern_signature(expected)
    if isinstance(entered[0], tuple):
        return False
    return patterns_match(entered, expected, strict_start)


def mirrored_pattern(pattern: Pattern, axis: str) -> Pattern:
    def mirror_node(node: int) -> int:
        row, col = divmod(node, 3)
        if axis == "x":
            row = 2 - row
        elif axis == "y":
            col = 2 - col
        elif axis == "origin":
            row = 2 - row
            col = 2 - col
        return row * 3 + col

    return tuple(mirror_node(node) for node in pattern)


@dataclass(frozen=True)
class GhostSpec:
    name: str
    pattern: Pattern
    speed: float
    score: int
    holy_power: int
    color: tuple[int, int, int]


@dataclass
class Ghost:
    RESONANCE_DURATION = 3.0
    RESONANCE_MULTIPLIER = 1.65

    spec: GhostSpec
    x: float
    y: float
    target_x: float = 0.0
    target_y: float = 0.0
    radius: int = 32
    pulse: float = 0.0
    remaining_patterns: list[PatternAttempt] = field(default_factory=list)
    vanishing: bool = False
    fade_remaining: float = 0.0
    fade_duration: float = 0.85
    movement_phase: str = "pause"
    movement_elapsed: float = 0.0
    movement_pause: float = 0.18
    movement_duration: float = 2.25
    step_start_x: float = 0.0
    step_start_y: float = 0.0
    step_end_x: float = 0.0
    step_end_y: float = 0.0
    kind: GhostKind = GhostKind.SLOWPOKE
    forbidden_patterns: list[Pattern] = field(default_factory=list)
    spawn_elapsed: float = 0.0
    spawn_duration: float = 0.7
    spawn_protected: bool = False
    slow_remaining: float = 0.0
    resonance_remaining: float = 0.0
    removed_pattern: Pattern = ()
    removed_forbidden_pattern: Pattern = ()
    pattern_transition_elapsed: float = 0.0
    pattern_transition_duration: float = 0.55
    pattern_transition_from_count: int = 0
    knockback_elapsed: float = 0.0
    knockback_duration: float = 0.42
    knockback_start_x: float = 0.0
    knockback_start_y: float = 0.0
    knockback_end_x: float = 0.0
    knockback_end_y: float = 0.0
    knockback_active: bool = False
    art_variant: int = 1
    hit_reaction_elapsed: float = 0.0
    hit_reaction_duration: float = 0.72
    hit_reaction_distance: float = 22.0
    hidden_remaining: float = 0.0
    hidden_duration: float = 5.5
    hidden_duration_min: float = 5.2
    hidden_duration_max: float = 7.8
    reappear_remaining: float = 0.0
    reappear_duration: float = 0.45
    pending_reappear_x: float = 0.0
    pending_reappear_y: float = 0.0
    crease_axis: str = ""
    crease_source_pattern: Pattern = ()
    crease_target_pattern: Pattern = ()
    crease_axes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.remaining_patterns:
            self.remaining_patterns = [self.spec.pattern]
        self.art_variant = 1 if self.art_variant == 1 else 2
        if not self.removed_pattern:
            self.hit_reaction_elapsed = self.hit_reaction_duration

    @property
    def pattern(self) -> Pattern:
        first = self.remaining_patterns[0] if self.remaining_patterns else ()
        if not first:
            return ()
        return first if isinstance(first[0], int) else first[0]

    @property
    def is_resonant(self) -> bool:
        return self.kind is GhostKind.FORBIDDEN

    @property
    def strict_start(self) -> bool:
        return self.kind is GhostKind.START_LOCKED

    @property
    def is_spawned(self) -> bool:
        return self.spawn_elapsed >= self.spawn_duration

    @property
    def is_interactive(self) -> bool:
        return (
            not self.vanishing
            and self.hidden_remaining <= 0
            and self.reappear_remaining <= 0
            and (not self.spawn_protected or self.is_spawned)
        )

    def matches_required(self, entered: PatternAttempt) -> bool:
        if not self.remaining_patterns:
            return False
        return pattern_attempt_matches(entered, self.remaining_patterns[0], self.strict_start)

    def matches_forbidden(self, entered: Pattern) -> bool:
        if not isinstance(entered[0], int):
            return False
        return any(
            patterns_match(entered, forbidden)
            for forbidden in self.forbidden_patterns
        )

    def update(self, seconds: float) -> None:
        self.spawn_elapsed = min(self.spawn_duration, self.spawn_elapsed + seconds)
        self.hit_reaction_elapsed = min(
            self.hit_reaction_duration,
            self.hit_reaction_elapsed + seconds,
        )
        was_hidden = self.hidden_remaining > 0
        self.hidden_remaining = max(0.0, self.hidden_remaining - seconds)
        started_reappearing = False
        if was_hidden and self.hidden_remaining <= 0:
            self.x = self.pending_reappear_x
            self.y = self.pending_reappear_y
            self.reappear_remaining = self.reappear_duration
            self.resonance_remaining = self.RESONANCE_DURATION
            self.spawn_elapsed = 0.0
            self.start_moving_immediately()
            started_reappearing = True
        if not started_reappearing:
            self.reappear_remaining = max(0.0, self.reappear_remaining - seconds)
        if self.pattern_transition_elapsed < self.pattern_transition_duration:
            self.pattern_transition_elapsed = min(
                self.pattern_transition_duration,
                self.pattern_transition_elapsed + seconds,
            )
            if self.pattern_transition_elapsed >= self.pattern_transition_duration:
                self.removed_pattern = ()
                self.removed_forbidden_pattern = ()
        self.slow_remaining = max(0.0, self.slow_remaining - seconds)
        if not started_reappearing:
            self.resonance_remaining = max(
                0.0, self.resonance_remaining - seconds
            )
        if self.vanishing or self.hidden_remaining > 0:
            self.fade_remaining = max(0.0, self.fade_remaining - seconds)
            self.pulse += seconds
            return

        if self.knockback_active:
            self.knockback_elapsed = min(
                self.knockback_duration,
                self.knockback_elapsed + seconds,
            )
            progress = self.knockback_elapsed / self.knockback_duration
            eased = 1.0 - (1.0 - progress) ** 3
            self.x = self.knockback_start_x + (
                self.knockback_end_x - self.knockback_start_x
            ) * eased
            self.y = self.knockback_start_y + (
                self.knockback_end_y - self.knockback_start_y
            ) * eased
            if self.knockback_elapsed >= self.knockback_duration:
                self.x = self.knockback_end_x
                self.y = self.knockback_end_y
                self.knockback_active = False
                self.movement_phase = "pause"
                self.movement_elapsed = 0.0
            self.pulse += seconds
            return

        remaining = seconds
        while remaining > 0:
            phase_duration = (
                self.movement_pause
                if self.movement_phase == "pause"
                else self.movement_duration
            )
            phase_remaining = phase_duration - self.movement_elapsed
            elapsed = min(remaining, phase_remaining)
            self.movement_elapsed += elapsed
            remaining -= elapsed

            if self.movement_phase == "move":
                progress = min(1.0, self.movement_elapsed / self.movement_duration)
                eased = progress * progress * (3.0 - 2.0 * progress)
                self.x = self.step_start_x + (self.step_end_x - self.step_start_x) * eased
                self.y = self.step_start_y + (self.step_end_y - self.step_start_y) * eased

            if self.movement_elapsed >= phase_duration:
                self.movement_elapsed = 0.0
                if self.movement_phase == "pause":
                    self._begin_movement_step()
                else:
                    self.x = self.step_end_x
                    self.y = self.step_end_y
                    self.movement_phase = "pause"
        self.pulse += seconds

    def _begin_movement_step(self) -> None:
        self.movement_phase = "move"
        self.step_start_x = self.x
        self.step_start_y = self.y
        distance = self.distance_to((self.target_x, self.target_y))
        if distance <= 0:
            self.step_end_x = self.x
            self.step_end_y = self.y
            return
        step_distance = min(
            self.spec.speed
            * (
                self.RESONANCE_MULTIPLIER
                if self.resonance_remaining > 0
                else 1.0
            )
            * (0.42 if self.slow_remaining > 0 else 1.0)
            * (self.movement_pause + self.movement_duration),
            distance,
        )
        self.step_end_x = self.x + (self.target_x - self.x) / distance * step_distance
        self.step_end_y = self.y + (self.target_y - self.y) / distance * step_distance

    def start_moving_immediately(self) -> None:
        self.movement_elapsed = 0.0
        self._begin_movement_step()

    def distance_to(self, position: tuple[float, float]) -> float:
        return math.hypot(self.x - position[0], self.y - position[1])

    def resonate(self) -> None:
        self.resonance_remaining = self.RESONANCE_DURATION

    def trigger_forbidden_pattern(self, entered: Pattern) -> None:
        for index, forbidden in enumerate(self.forbidden_patterns):
            if patterns_match(entered, forbidden):
                self.removed_forbidden_pattern = self.forbidden_patterns.pop(index)
                self.pattern_transition_elapsed = 0.0
                self.pattern_transition_from_count = len(self.remaining_patterns) + 1
                break
        self.resonate()

    def repel(self, distance: float) -> None:
        dx = self.x - self.target_x
        dy = self.y - self.target_y
        length = math.hypot(dx, dy) or 1.0
        self.knockback_start_x = self.x
        self.knockback_start_y = self.y
        self.knockback_end_x = self.x + dx / length * distance
        self.knockback_end_y = self.y + dy / length * distance
        self.knockback_elapsed = 0.0
        self.knockback_active = True

    def nullify_gimmick(self) -> None:
        self.kind = GhostKind.SLOWPOKE
        self.forbidden_patterns.clear()
        self.resonance_remaining = 0.0

    def remove_first_pattern(self) -> bool:
        if self.vanishing or not self.remaining_patterns:
            return False
        self.pattern_transition_from_count = len(self.remaining_patterns)
        self.removed_pattern = self.remaining_patterns.pop(0)
        if self.crease_axes:
            self.crease_axes.pop(0)
        self.pattern_transition_elapsed = 0.0
        self.hit_reaction_elapsed = 0.0
        if not self.remaining_patterns:
            self.vanishing = True
            self.fade_remaining = self.fade_duration
        return True

    def hide_and_reappear_at(self, position: tuple[float, float]) -> None:
        self.pending_reappear_x, self.pending_reappear_y = position
        self.hidden_remaining = self.hidden_duration
        self.reappear_remaining = 0.0
        self.hit_reaction_elapsed = self.hit_reaction_duration
        self.knockback_active = False
        self.movement_phase = "pause"
        self.movement_elapsed = 0.0

    def reveal_now(self, accelerate: bool = False) -> None:
        if self.hidden_remaining > 0:
            self.hidden_remaining = 0.0
            self.x = self.pending_reappear_x
            self.y = self.pending_reappear_y
            self.reappear_remaining = self.reappear_duration
            self.resonance_remaining = (
                self.RESONANCE_DURATION if accelerate else 0.0
            )
            self.spawn_elapsed = 0.0
            self.start_moving_immediately()

    @property
    def alpha(self) -> int:
        if self.hidden_remaining > 0:
            return 0
        reappear_alpha = (
            1.0 - self.reappear_remaining / self.reappear_duration
            if self.reappear_remaining > 0
            else 1.0
        )
        spawn_alpha = min(1.0, self.spawn_elapsed / self.spawn_duration)
        vanish_alpha = (
            self.fade_remaining / self.fade_duration if self.vanishing else 1.0
        )
        return round(255 * spawn_alpha * vanish_alpha * reappear_alpha)

    @property
    def pattern_transition_progress(self) -> float:
        if not self.removed_pattern and not self.removed_forbidden_pattern:
            return 1.0
        return min(
            1.0,
            self.pattern_transition_elapsed / self.pattern_transition_duration,
        )

    @property
    def hit_reaction_progress(self) -> float:
        return min(1.0, self.hit_reaction_elapsed / self.hit_reaction_duration)

    @property
    def is_hit_reacting(self) -> bool:
        return self.hit_reaction_progress < 1.0

    @property
    def facing_right(self) -> bool:
        return self.x <= self.target_x


class PatternInput:
    def __init__(self) -> None:
        self.nodes: list[int] = []
        self.dragging = False

    def begin(self, node: Optional[int]) -> None:
        self.nodes.clear()
        self.dragging = True
        self.add(node)

    def add(self, node: Optional[int]) -> None:
        if not self.dragging or node is None or node in self.nodes:
            return
        self.nodes.append(node)

    def finish(self) -> Pattern:
        pattern = tuple(self.nodes)
        self.clear()
        return pattern

    def clear(self) -> None:
        self.nodes.clear()
        self.dragging = False


class SpellManager:
    MAX_POWER = 150
    HEAL_AMOUNT = 2
    REPEL_DISTANCE = 190.0
    REPEL_RADIUS = 330.0
    NULLIFY_RADIUS = 285.0
    REPEL_SLOW_DURATION = 1.0
    SPELLS = (
        SpellDefinition(
            SpellType.HEAL,
            "HEAL",
            (6, 4, 2, 1, 0, 5, 8),
            40,
            "+2 HP",
            7.0,
        ),
        SpellDefinition(
            SpellType.REPEL,
            "REPEL",
            (0, 4, 8, 5, 2),
            35,
            "Push and slow 1s",
            6.0,
        ),
        SpellDefinition(
            SpellType.NULLIFY,
            "SANCTIFY",
            (0, 1, 4, 7, 8),
            45,
            "Clear all gimmicks",
            10.0,
        ),
        SpellDefinition(
            SpellType.TRUTH,
            "TRUTH",
            (2, 1, 4, 3, 6),
            45,
            "Reveal creeps / clear traps",
            12.0,
        ),
    )
    HEAL_PATTERN = SPELLS[0].pattern
    HEAL_COST = SPELLS[0].cost

    def __init__(self) -> None:
        self.holy_power = 0
        self.cooldowns: dict[SpellType, float] = {
            spell.spell_type: 0.0 for spell in self.SPELLS
        }

    def gain(self, amount: int) -> None:
        self.holy_power = min(self.MAX_POWER, self.holy_power + amount)

    def can_heal(self) -> bool:
        return self.holy_power >= self.HEAL_COST

    def matching_spell(self, pattern: Pattern) -> Optional[SpellDefinition]:
        return next(
            (
                spell
                for spell in self.SPELLS
                if patterns_match(pattern, spell.pattern)
            ),
            None,
        )

    def can_cast(self, spell: SpellDefinition) -> bool:
        return (
            self.holy_power >= spell.cost
            and self.cooldowns.get(spell.spell_type, 0.0) <= 0
        )

    def spend(self, spell: SpellDefinition) -> None:
        self.holy_power -= spell.cost
        self.cooldowns[spell.spell_type] = spell.cooldown

    def update(self, seconds: float) -> None:
        for spell_type, remaining in list(self.cooldowns.items()):
            self.cooldowns[spell_type] = max(0.0, remaining - seconds)

    def cooldown_progress(self, spell: SpellDefinition) -> float:
        remaining = self.cooldowns.get(spell.spell_type, 0.0)
        if spell.cooldown <= 0:
            return 1.0
        return 1.0 - min(1.0, remaining / spell.cooldown)


GHOST_SPECS = (
    GhostSpec("Wisp", PATTERN_POOL[0], 14.0, 100, 10, (205, 218, 232)),
    GhostSpec("Shade", PATTERN_POOL[4], 16.0, 130, 12, (205, 218, 232)),
    GhostSpec("Mourner", PATTERN_POOL[8], 18.0, 160, 14, (205, 218, 232)),
    GhostSpec("Lurker", PATTERN_POOL[5], 15.0, 190, 16, (205, 218, 232)),
)


@dataclass
class GameSession:
    SPAWN_CLEARANCE = 170.0

    rng: random.Random = field(default_factory=random.Random)
    max_health: int = 5
    health: int = 5
    score: int = 0
    wave: int = 1
    spawn_queue: Deque[GhostSpec] = field(default_factory=deque)
    ghosts: list[Ghost] = field(default_factory=list)
    spells: SpellManager = field(default_factory=SpellManager)
    last_message: str = ""
    last_match_count: int = 0
    last_spell_cast: bool = False
    last_spell_type: Optional[SpellType] = None
    defeated_events: list[tuple[float, float, int]] = field(default_factory=list)

    def reset(self) -> None:
        self.health = self.max_health
        self.score = 0
        self.wave = 1
        self.spawn_queue.clear()
        self.ghosts.clear()
        self.spells = SpellManager()
        self.last_message = ""
        self.last_match_count = 0
        self.last_spell_cast = False
        self.last_spell_type = None
        self.defeated_events.clear()
        self.fill_wave()

    def fill_wave(self) -> None:
        count = 4 + self.wave
        specs = [self.rng.choice(GHOST_SPECS) for _ in range(count)]
        self.spawn_queue.extend(specs)

    def spawn_next(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
    ) -> Optional[Ghost]:
        if not self.spawn_queue or not spawn_positions:
            return None
        available_positions = [
            position
            for position in spawn_positions
            if all(
                ghost.vanishing
                or ghost.distance_to(position) >= self.SPAWN_CLEARANCE
                for ghost in self.ghosts
            )
        ]
        if not available_positions:
            for extension in (0.35, 0.7, 1.05, 1.4):
                extended_positions = []
                for position in spawn_positions:
                    dx = position[0] - player_position[0]
                    dy = position[1] - player_position[1]
                    candidate = (
                        player_position[0] + dx * (1.0 + extension),
                        player_position[1] + dy * (1.0 + extension),
                    )
                    if all(
                        ghost.vanishing
                        or ghost.distance_to(candidate) >= self.SPAWN_CLEARANCE
                        for ghost in self.ghosts
                    ):
                        extended_positions.append(candidate)
                if extended_positions:
                    available_positions = extended_positions
                    break
        if not available_positions:
            return None
        spec = self.spawn_queue.popleft()
        x, y = self.rng.choice(available_positions)
        kind_weights = (
            (36, 4, 6, 16, 4, 3, 8, 15, 8)
            if self.wave == 1
            else (23, 6, 8, 16, 8, 5, 11, 16, 7)
        )
        kind = self.rng.choices(tuple(GhostKind), weights=kind_weights, k=1)[0]
        pattern_count = self.rng.choices(
            (1, 2, 3), weights=(65, 30, 5), k=1
        )[0]
        if kind is GhostKind.CREEP:
            pattern_count = max(2, pattern_count)
        remaining_patterns: list[PatternAttempt] = list(
            self.rng.sample(PATTERN_POOL, k=pattern_count)
        )
        crease_axis = ""
        crease_source_pattern: Pattern = ()
        crease_target_pattern: Pattern = ()
        crease_axes: list[str] = []
        if kind is GhostKind.CREASE:
            source_patterns = self.rng.sample(PATTERN_POOL, k=pattern_count)
            crease_axes = [
                self.rng.choices(("x", "y", "origin"), weights=(47, 47, 6), k=1)[0]
                for _ in source_patterns
            ]
            crease_axis = crease_axes[0]
            crease_source_pattern = source_patterns[0]
            remaining_patterns = [
                mirrored_pattern(pattern, axis)
                for pattern, axis in zip(source_patterns, crease_axes)
            ]
            crease_target_pattern = remaining_patterns[0]
        elif kind is GhostKind.SNARL:
            snarl_count = self.rng.choices((1, 2), weights=(70, 30), k=1)[0]
            remaining_patterns = []
            for _ in range(snarl_count):
                if self.rng.random() < 0.42:
                    remaining_patterns.append(self.rng.choice(LAYERED_PATTERN_POOL))
                else:
                    remaining_patterns.append(self.rng.choice(COMPLEX_PATTERN_POOL))
        forbidden_patterns: list[Pattern] = []
        if kind is GhostKind.FORBIDDEN:
            overlapping = [
                ghost.pattern
                for ghost in self.ghosts
                if ghost.is_interactive and ghost.pattern not in remaining_patterns
            ]
            candidates = overlapping or [
                pattern
                for pattern in PATTERN_POOL
                if pattern not in remaining_patterns
            ]
            forbidden_patterns = [self.rng.choice(candidates)]
        ghost = Ghost(
            spec,
            x,
            y,
            player_position[0],
            player_position[1],
            remaining_patterns=remaining_patterns,
            kind=kind,
            forbidden_patterns=forbidden_patterns,
            art_variant=self.rng.choice((1, 2)),
            spawn_protected=True,
            crease_axis=crease_axis,
            crease_source_pattern=crease_source_pattern,
            crease_target_pattern=crease_target_pattern,
            crease_axes=crease_axes,
        )
        ghost.start_moving_immediately()
        self.ghosts.append(ghost)
        return ghost

    def advance_wave_if_clear(self) -> bool:
        if self.spawn_queue or self.ghosts:
            return False
        self.wave += 1
        self.fill_wave()
        self.last_message = f"WAVE {self.wave}"
        return True

    def update_ghosts(
        self,
        seconds: float,
        player_position: tuple[float, float],
        player_radius: float,
    ) -> int:
        self.spells.update(seconds)
        escaped = 0
        for ghost in list(self.ghosts):
            ghost.update(seconds)
            if ghost.vanishing and ghost.fade_remaining <= 0:
                self.ghosts.remove(ghost)
            elif (
                ghost.is_interactive
                and ghost.distance_to(player_position) <= player_radius + ghost.radius
            ):
                self.ghosts.remove(ghost)
                escaped += 1
        if escaped:
            self.damage(escaped)
            self.last_message = "A ghost reached you!"
        return escaped

    def damage(self, amount: int = 1) -> None:
        self.health = max(0, self.health - amount)

    def judge_pattern(self, pattern: Iterable[int] | tuple[Pattern, Pattern]) -> PatternResult:
        raw = tuple(pattern)
        entered: PatternAttempt = raw  # type: ignore[assignment]
        self.last_match_count = 0
        self.last_spell_cast = False
        self.last_spell_type = None
        self.defeated_events.clear()
        if not entered:
            return PatternResult.EMPTY

        spell = None if isinstance(entered[0], tuple) else self.spells.matching_spell(entered)
        if spell is not None:
            if not self.spells.can_cast(spell):
                self.last_message = ""
                return PatternResult.MISSED
            self.last_spell_cast = True
            self.last_spell_type = spell.spell_type
            self._cast_spell(spell)
            self.last_message = ""
            return PatternResult.SPELL

        active_ghosts = [ghost for ghost in self.ghosts if ghost.is_interactive]
        if not active_ghosts:
            self.last_message = ""
            return PatternResult.MISSED

        matched = [ghost for ghost in active_ghosts if ghost.matches_required(entered)]
        self.last_match_count = len(matched)
        defeated = 0
        if matched:
            for ghost in matched:
                ghost.remove_first_pattern()
                if ghost.vanishing:
                    defeated += 1
                    self.score += ghost.spec.score
                    self.spells.gain(ghost.spec.holy_power)
                    self.defeated_events.append(
                        (ghost.x, ghost.y, ghost.spec.holy_power)
                    )
                elif ghost.kind is GhostKind.CREEP:
                    ghost.hidden_duration = self.rng.uniform(
                        ghost.hidden_duration_min,
                        ghost.hidden_duration_max,
                    )
                    ghost.hide_and_reappear_at(self._creep_reappear_position(ghost))
        forbidden_hits = [
            ghost
            for ghost in active_ghosts
            if all(ghost is not matched_ghost for matched_ghost in matched)
            and not isinstance(entered[0], tuple)
            and ghost.matches_forbidden(entered)
        ]
        if forbidden_hits:
            for ghost in forbidden_hits:
                ghost.trigger_forbidden_pattern(entered)
            self.last_message = ""
            return PatternResult.RESONATED

        if matched:
            self.last_message = ""
            return PatternResult.HIT

        self.last_message = ""
        return PatternResult.MISSED

    def _creep_reappear_position(self, ghost: Ghost) -> tuple[float, float]:
        dx = ghost.x - ghost.target_x
        dy = ghost.y - ghost.target_y
        distance = math.hypot(dx, dy) or 1.0
        min_distance = ghost.radius + 185.0
        base_distance = max(min_distance, distance - self.rng.uniform(25.0, 70.0))
        base_angle = math.atan2(dy, dx)
        for _ in range(32):
            angle = base_angle + self.rng.uniform(-1.45, 1.45)
            candidate_distance = max(
                min_distance,
                base_distance + self.rng.uniform(-25.0, 90.0),
            )
            candidate = (
                ghost.target_x + math.cos(angle) * candidate_distance,
                ghost.target_y + math.sin(angle) * candidate_distance,
            )
            if self._position_is_clear_for_creep(ghost, candidate):
                return candidate
        for ring_index in range(40):
            ring = base_distance + ring_index * 55.0
            for step in range(16):
                angle = base_angle + step * math.tau / 16
                candidate = (
                    ghost.target_x + math.cos(angle) * ring,
                    ghost.target_y + math.sin(angle) * ring,
                )
                if self._position_is_clear_for_creep(ghost, candidate):
                    return candidate
        return (
            ghost.target_x + dx / distance * (base_distance + 2600.0),
            ghost.target_y + dy / distance * (base_distance + 2600.0),
        )

    def _position_is_clear_for_creep(
        self, ghost: Ghost, candidate: tuple[float, float]
    ) -> bool:
        return all(
            other is ghost
            or other.vanishing
            or other.hidden_remaining > 0
            or math.hypot(other.x - candidate[0], other.y - candidate[1])
            >= self.SPAWN_CLEARANCE
            for other in self.ghosts
        )

    def _cast_spell(self, spell: SpellDefinition) -> None:
        active_ghosts = [ghost for ghost in self.ghosts if ghost.is_interactive]
        if spell.spell_type is SpellType.HEAL:
            if self.health >= self.max_health:
                return
            self.spells.spend(spell)
            self.health = min(
                self.max_health, self.health + self.spells.HEAL_AMOUNT
            )
        elif spell.spell_type is SpellType.REPEL:
            self.spells.spend(spell)
            for ghost in active_ghosts:
                if ghost.distance_to((ghost.target_x, ghost.target_y)) <= (
                    self.spells.REPEL_RADIUS
                ):
                    ghost.repel(self.spells.REPEL_DISTANCE)
                    ghost.slow_remaining = self.spells.REPEL_SLOW_DURATION
        elif spell.spell_type is SpellType.NULLIFY:
            self.spells.spend(spell)
            for ghost in active_ghosts:
                ghost.nullify_gimmick()
        elif spell.spell_type is SpellType.TRUTH:
            self.spells.spend(spell)
            for ghost in self.ghosts:
                if ghost.kind is GhostKind.CREEP and not ghost.vanishing:
                    ghost.reveal_now()
                if ghost.kind is GhostKind.FORBIDDEN:
                    ghost.kind = GhostKind.SLOWPOKE
                    ghost.forbidden_patterns.clear()
                    ghost.resonance_remaining = 0.0

    def target_ghost(self) -> Optional[Ghost]:
        if not self.ghosts:
            return None
        return min(
            (ghost for ghost in self.ghosts if not ghost.vanishing),
            key=lambda ghost: ghost.distance_to((ghost.target_x, ghost.target_y)),
            default=None,
        )
