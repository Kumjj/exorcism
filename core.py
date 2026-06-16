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
STAGE_TWO_PATTERN_POOL: tuple[Pattern, ...] = (
    (0, 4, 1, 2),
    (2, 4, 1, 0),
    (0, 4, 3, 6),
    (2, 4, 5, 8),
    (6, 4, 3, 0),
    (8, 4, 5, 2),
    (0, 4, 5, 8),
    (2, 4, 3, 6),
    (6, 4, 1, 2),
    (8, 4, 7, 6),
    (0, 4, 2, 5, 8),
    (2, 4, 0, 3, 6),
    (6, 4, 8, 5, 2),
    (8, 4, 6, 3, 0),
    (0, 4, 1, 2, 5),
    (2, 4, 5, 8, 7),
)
WEAVER_PATTERN_POOL: tuple[Pattern, ...] = (
    (0, 4, 8, 5, 2),
    (2, 4, 6, 3, 0),
    (6, 4, 2, 1, 0),
    (8, 4, 0, 3, 6),
    (0, 4, 2, 5, 8),
    (2, 4, 0, 3, 6),
    (6, 4, 8, 5, 2),
    (8, 4, 6, 3, 0),
    (1, 4, 7, 3, 0),
    (7, 4, 1, 5, 8),
    (0, 4, 7, 5, 2, 1),
    (2, 4, 3, 7, 6, 5),
)
WEAVER_ORIGIN_PATTERN_POOL: tuple[Pattern, ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
)
WEAVER_LAYERED_PATTERN_POOL: tuple[tuple[Pattern, Pattern], ...] = (
    ((0, 1, 4, 7), (2, 5, 8)),
    ((0, 3, 4, 5), (2, 1, 4, 7)),
    ((6, 3, 4, 1, 2), (8, 5, 4, 7)),
    ((0, 4, 8), (2, 1, 4, 3, 6)),
    ((6, 7, 4, 1), (0, 3, 4, 5, 8)),
    ((2, 5, 4, 7, 6), (0, 1, 4, 3)),
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
    start_locked_slots: list[bool] = field(default_factory=list)
    partial_slots: list[bool] = field(default_factory=list)
    removed_start_locked: bool = False
    removed_partial: bool = False
    sealed_slots: set[int] = field(default_factory=set)
    max_sealed_slots: int = 1

    def __post_init__(self) -> None:
        if not self.remaining_patterns:
            self.remaining_patterns = [self.spec.pattern]
        pattern_count = len(self.remaining_patterns)
        if not self.start_locked_slots:
            self.start_locked_slots = [
                self.kind is GhostKind.START_LOCKED
            ] + [False] * (pattern_count - 1)
        else:
            self.start_locked_slots = (
                self.start_locked_slots[:pattern_count]
                + [False] * max(0, pattern_count - len(self.start_locked_slots))
            )
        if not self.partial_slots:
            self.partial_slots = [
                self.kind is GhostKind.PARTIAL
            ] + [False] * (pattern_count - 1)
        else:
            self.partial_slots = (
                self.partial_slots[:pattern_count]
                + [False] * max(0, pattern_count - len(self.partial_slots))
            )
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
        return bool(self.start_locked_slots and self.start_locked_slots[0])

    @property
    def partial_pattern(self) -> bool:
        return bool(self.partial_slots and self.partial_slots[0])

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
        if not self.remaining_patterns or 0 in self.sealed_slots:
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
                self.removed_start_locked = False
                self.removed_partial = False
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
        self.start_locked_slots = [False] * len(self.remaining_patterns)
        self.partial_slots = [False] * len(self.remaining_patterns)
        self.purify_one()

    def apply_random_seal(self, rng: random.Random) -> bool:
        if (
            len(self.sealed_slots) >= self.max_sealed_slots
            or not self.remaining_patterns
        ):
            return False
        available = [
            index
            for index in range(len(self.remaining_patterns))
            if index not in self.sealed_slots
        ]
        if not available:
            return False
        self.sealed_slots.add(rng.choice(available))
        return True

    def purify_one(self) -> bool:
        if not self.sealed_slots:
            return False
        self.sealed_slots.remove(min(self.sealed_slots))
        return True

    def remove_first_pattern(self) -> bool:
        if self.vanishing or not self.remaining_patterns:
            return False
        self.pattern_transition_from_count = len(self.remaining_patterns)
        self.removed_pattern = self.remaining_patterns.pop(0)
        self.removed_start_locked = (
            self.start_locked_slots.pop(0)
            if self.start_locked_slots
            else False
        )
        self.removed_partial = (
            self.partial_slots.pop(0)
            if self.partial_slots
            else False
        )
        self.sealed_slots = {
            index - 1
            for index in self.sealed_slots
            if index > 0
        }
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


@dataclass
class PitonBoss:
    spec: GhostSpec
    x: float
    y: float
    target_x: float
    target_y: float
    rows: list[list[PatternAttempt]]
    radius: int = 58
    row_index: int = 0
    patterns: list[PatternAttempt] = field(default_factory=list)
    pattern_axis_rows: list[list[str]] = field(default_factory=list)
    pattern_axes: list[str] = field(default_factory=list)
    sealed_slots: set[int] = field(default_factory=set)
    seal_timer: float = 12.0
    seal_interval: float = 12.0
    seal_refill_delay: float = 8.0
    max_sealed_slots: int = 4
    spell_seal_timer: float = 20.0
    spell_seal_interval: float = 20.0
    spell_seal_duration: float = 5.0
    max_sealed_spells: int = 2
    sealed_spells: dict[SpellType, float] = field(default_factory=dict)
    spawn_elapsed: float = 0.0
    spawn_duration: float = 1.0
    hidden_remaining: float = 0.0
    hidden_duration: float = 1.2
    pending_x: float = 0.0
    pending_y: float = 0.0
    retreat_repositioned: bool = False
    defeated: bool = False
    fade_remaining: float = 0.0
    fade_duration: float = 1.1
    pulse: float = 0.0
    movement_phase: str = "move"
    movement_elapsed: float = 0.0
    movement_duration: float = 3.2
    movement_pause: float = 0.35
    step_start_x: float = 0.0
    step_start_y: float = 0.0
    step_end_x: float = 0.0
    step_end_y: float = 0.0
    knockback_active: bool = False
    knockback_elapsed: float = 0.0
    knockback_duration: float = 0.52
    knockback_start_x: float = 0.0
    knockback_start_y: float = 0.0
    knockback_end_x: float = 0.0
    knockback_end_y: float = 0.0
    hit_reaction_elapsed: float = 0.0
    hit_reaction_duration: float = 0.7
    seal_waiting_for_purify: bool = False
    recently_purified_slots: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.patterns = list(self.rows[0])
        if not self.pattern_axis_rows:
            self.pattern_axis_rows = [[""] * len(row) for row in self.rows]
        self.pattern_axes = list(self.pattern_axis_rows[0])
        self.hit_reaction_elapsed = self.hit_reaction_duration
        self.start_moving_immediately()

    @property
    def row_number(self) -> int:
        return self.row_index + 1

    @property
    def is_interactive(self) -> bool:
        return (
            not self.defeated
            and self.hidden_remaining <= 0
            and self.spawn_elapsed >= self.spawn_duration
        )

    @property
    def alpha(self) -> int:
        if self.hidden_remaining > 0:
            progress = 1.0 - self.hidden_remaining / self.hidden_duration
            visibility = (
                1.0 - progress * 2.0
                if progress < 0.5
                else (progress - 0.5) * 2.0
            )
            return round(255 * max(0.0, min(1.0, visibility)))
        spawn = min(1.0, self.spawn_elapsed / self.spawn_duration)
        vanish = (
            self.fade_remaining / self.fade_duration
            if self.defeated
            else 1.0
        )
        return round(255 * spawn * vanish)

    def distance_to(self, position: tuple[float, float]) -> float:
        return math.hypot(self.x - position[0], self.y - position[1])

    @property
    def hit_reaction_progress(self) -> float:
        return min(1.0, self.hit_reaction_elapsed / self.hit_reaction_duration)

    @property
    def is_hit_reacting(self) -> bool:
        return self.hit_reaction_progress < 1.0

    def update(self, seconds: float, rng: random.Random) -> None:
        self.pulse += seconds
        self.hit_reaction_elapsed = min(
            self.hit_reaction_duration,
            self.hit_reaction_elapsed + seconds,
        )
        for spell_type, remaining in list(self.sealed_spells.items()):
            remaining = max(0.0, remaining - seconds)
            if remaining <= 0:
                self.sealed_spells.pop(spell_type, None)
            else:
                self.sealed_spells[spell_type] = remaining
        if self.defeated:
            self.fade_remaining = max(0.0, self.fade_remaining - seconds)
            return
        if self.hidden_remaining > 0:
            before = self.hidden_remaining
            self.hidden_remaining = max(0.0, self.hidden_remaining - seconds)
            midpoint = self.hidden_duration / 2.0
            if (
                not self.retreat_repositioned
                and before > midpoint
                and self.hidden_remaining <= midpoint
            ):
                self.x = self.pending_x
                self.y = self.pending_y
                self.retreat_repositioned = True
                self.start_moving_immediately()
            if self.hidden_remaining <= 0:
                self.retreat_repositioned = False
                self.start_moving_immediately()
            return
        self.spawn_elapsed = min(self.spawn_duration, self.spawn_elapsed + seconds)
        self.spell_seal_timer -= seconds
        if self.spell_seal_timer <= 0:
            self.apply_random_spell_seal(rng)
            self.spell_seal_timer += self.spell_seal_interval
        if self.seal_waiting_for_purify:
            self.seal_timer = self.seal_refill_delay
        elif len(self.sealed_slots) < self.max_sealed_slots:
            self.seal_timer -= seconds
            if self.seal_timer <= 0:
                self.apply_random_seal(rng)
                self.seal_timer += self.seal_interval
        else:
            self.seal_timer = self.seal_interval
        if self.knockback_active:
            self._update_knockback(seconds)
            return
        self._update_movement(seconds)

    def _update_knockback(self, seconds: float) -> None:
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
        if progress >= 1.0:
            self.knockback_active = False
            self.start_moving_immediately()

    def repel(self, distance: float) -> None:
        dx = self.x - self.target_x
        dy = self.y - self.target_y
        current_distance = math.hypot(dx, dy)
        if current_distance <= 0:
            dx, dy = 0.0, -1.0
            current_distance = 1.0
        self.knockback_start_x = self.x
        self.knockback_start_y = self.y
        self.knockback_end_x = self.x + dx / current_distance * distance
        self.knockback_end_y = self.y + dy / current_distance * distance
        self.knockback_elapsed = 0.0
        self.knockback_active = True
        self.hit_reaction_elapsed = 0.0

    def _update_movement(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0:
            duration = (
                self.movement_pause
                if self.movement_phase == "pause"
                else self.movement_duration
            )
            step = min(remaining, duration - self.movement_elapsed)
            self.movement_elapsed += step
            remaining -= step
            if self.movement_phase == "move":
                progress = min(1.0, self.movement_elapsed / self.movement_duration)
                eased = progress * progress * (3.0 - 2.0 * progress)
                self.x = self.step_start_x + (
                    self.step_end_x - self.step_start_x
                ) * eased
                self.y = self.step_start_y + (
                    self.step_end_y - self.step_start_y
                ) * eased
            if self.movement_elapsed >= duration:
                self.movement_elapsed = 0.0
                if self.movement_phase == "pause":
                    self._begin_movement_step()
                else:
                    self.x = self.step_end_x
                    self.y = self.step_end_y
                    self.movement_phase = "pause"

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
            self.spec.speed * (self.movement_pause + self.movement_duration),
            distance,
        )
        self.step_end_x = self.x + (
            self.target_x - self.x
        ) / distance * step_distance
        self.step_end_y = self.y + (
            self.target_y - self.y
        ) / distance * step_distance

    def start_moving_immediately(self) -> None:
        self.movement_elapsed = 0.0
        self._begin_movement_step()

    def apply_random_seal(self, rng: random.Random) -> bool:
        if len(self.sealed_slots) >= self.max_sealed_slots:
            return False
        available = [
            index
            for index in range(len(self.patterns))
            if index not in self.sealed_slots
            and index not in self.recently_purified_slots
        ]
        if not available:
            return False
        self.sealed_slots.add(rng.choice(available))
        if len(self.sealed_slots) >= self.max_sealed_slots:
            self.seal_waiting_for_purify = True
        return True

    def apply_random_spell_seal(self, rng: random.Random) -> bool:
        if len(self.sealed_spells) >= self.max_sealed_spells:
            return False
        available = [
            spell.spell_type
            for spell in SpellManager.SPELLS
            if spell.spell_type not in self.sealed_spells
        ]
        if not available:
            return False
        spell_type = rng.choice(available)
        self.sealed_spells[spell_type] = self.spell_seal_duration
        return True

    def spell_seal_remaining(self, spell_type: SpellType) -> float:
        return self.sealed_spells.get(spell_type, 0.0)

    def is_spell_sealed(self, spell_type: SpellType) -> bool:
        return self.spell_seal_remaining(spell_type) > 0

    def add_row_transition_seal(self, rng: random.Random) -> None:
        if len(self.sealed_slots) >= self.max_sealed_slots:
            return
        available = [
            index
            for index in range(len(self.patterns))
            if index not in self.sealed_slots
            and index not in self.recently_purified_slots
        ]
        if available:
            self.sealed_slots.add(rng.choice(available))
            self.seal_waiting_for_purify = (
                len(self.sealed_slots) >= self.max_sealed_slots
            )

    def purify_one(self) -> bool:
        if not self.sealed_slots:
            return False
        slot = min(self.sealed_slots)
        self.sealed_slots.remove(slot)
        self.recently_purified_slots.add(slot)
        self.seal_waiting_for_purify = False
        self.seal_timer = self.seal_refill_delay
        return True

    def hit_pattern(self, entered: PatternAttempt, rng: random.Random) -> str:
        if not self.is_interactive:
            return ""
        matching = [
            index
            for index, pattern in enumerate(self.patterns)
            if index not in self.sealed_slots
            and self._matches_pattern_slot(entered, pattern, index)
        ]
        if not matching:
            return ""
        self.hit_reaction_elapsed = 0.0
        removed_index = matching[0]
        self.patterns.pop(removed_index)
        if removed_index < len(self.pattern_axes):
            self.pattern_axes.pop(removed_index)
        self.sealed_slots = {
            index - 1 if index > removed_index else index
            for index in self.sealed_slots
            if index != removed_index
        }
        if self.patterns:
            return "hit"
        if self.row_index + 1 >= len(self.rows):
            self.defeated = True
            self.fade_remaining = self.fade_duration
            return "defeated"
        self.row_index += 1
        self.patterns = list(self.rows[self.row_index])
        self.pattern_axes = list(self.pattern_axis_rows[self.row_index])
        self.sealed_slots.clear()
        self.recently_purified_slots.clear()
        self.seal_waiting_for_purify = False
        self.seal_timer = self.seal_interval
        self.add_row_transition_seal(rng)
        self.apply_random_spell_seal(rng)
        return "row"

    def _matches_pattern_slot(
        self,
        entered: PatternAttempt,
        pattern: PatternAttempt,
        index: int,
    ) -> bool:
        axis = self.pattern_axes[index] if index < len(self.pattern_axes) else ""
        if (
            axis
            and pattern
            and not isinstance(pattern[0], tuple)
            and entered
            and not isinstance(entered[0], tuple)
        ):
            return pattern_attempt_matches(entered, pattern)
        return pattern_attempt_matches(entered, pattern)

    def retreat_and_reposition(self, position: tuple[float, float]) -> None:
        self.pending_x, self.pending_y = position
        self.hidden_remaining = self.hidden_duration
        self.retreat_repositioned = False
        self.knockback_active = False
        self.movement_phase = "pause"
        self.movement_elapsed = 0.0


@dataclass
class WeaverBoss(PitonBoss):
    seal_timer: float = 20.0
    seal_interval: float = 20.0
    snarl_timer: float = 40.0
    snarl_interval: float = 40.0
    pending_snarl_bursts: int = 0
    pending_snarl_singles: int = 0
    web_lane_timer: float = 7.0
    web_lane_interval: float = 8.5
    web_lane_duration: float = 6.0
    active_web_lanes: dict[int, float] = field(default_factory=dict)
    web_spell_timer: float = 13.0
    web_spell_interval: float = 14.0
    web_spell_duration: float = 9.0
    pending_web_spell: Optional[SpellType] = None

    def update(self, seconds: float, rng: random.Random) -> None:
        super().update(seconds, rng)
        if self.defeated or self.hidden_remaining > 0:
            return
        for lane, remaining in list(self.active_web_lanes.items()):
            remaining = max(0.0, remaining - seconds)
            if remaining <= 0:
                self.active_web_lanes.pop(lane, None)
            else:
                self.active_web_lanes[lane] = remaining
        self.snarl_timer -= seconds
        if self.snarl_timer <= 0:
            self.pending_snarl_bursts += 1
            self.snarl_timer += self.snarl_interval
        self.web_lane_timer -= seconds
        if self.web_lane_timer <= 0:
            for lane in rng.sample(range(8), k=2):
                self.active_web_lanes[lane] = self.web_lane_duration
            self.web_lane_timer += self.web_lane_interval
        self.web_spell_timer -= seconds
        if self.web_spell_timer <= 0:
            self.pending_web_spell = rng.choice(
                [spell.spell_type for spell in SpellManager.SPELLS]
            )
            self.web_spell_timer += self.web_spell_interval

    def hit_pattern(self, entered: PatternAttempt, rng: random.Random) -> str:
        result = super().hit_pattern(entered, rng)
        if result == "row":
            self.pending_snarl_singles += 1
        return result

    def web_affects_position(self, position: tuple[float, float]) -> bool:
        if not self.active_web_lanes:
            return False
        dx = position[0] - self.target_x
        dy = position[1] - self.target_y
        if dx == 0 and dy == 0:
            return False
        angle = (math.atan2(dy, dx) + math.tau) % math.tau
        lane = round(angle / (math.tau / 8.0)) % 8
        return lane in self.active_web_lanes

    def consume_web_spell(self) -> Optional[SpellType]:
        spell_type = self.pending_web_spell
        self.pending_web_spell = None
        return spell_type

    def clear_web_effects(self) -> None:
        self.active_web_lanes.clear()
        self.pending_web_spell = None

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
            1.0,
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
        self.cooldown_drags: dict[SpellType, float] = {}

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
            drag_remaining = self.cooldown_drags.get(spell_type, 0.0)
            rate = 0.5 if drag_remaining > 0 else 1.0
            self.cooldowns[spell_type] = max(0.0, remaining - seconds * rate)
            if drag_remaining > 0:
                drag_remaining = max(0.0, drag_remaining - seconds)
                if drag_remaining <= 0:
                    self.cooldown_drags.pop(spell_type, None)
                else:
                    self.cooldown_drags[spell_type] = drag_remaining

    def slow_cooldown(self, spell_type: SpellType, duration: float) -> None:
        self.cooldown_drags[spell_type] = max(
            self.cooldown_drags.get(spell_type, 0.0),
            duration,
        )

    def clear_cooldown_drags(self) -> None:
        self.cooldown_drags.clear()

    def cooldown_progress(self, spell: SpellDefinition) -> float:
        remaining = self.cooldowns.get(spell.spell_type, 0.0)
        if spell.cooldown <= 0:
            return 1.0
        return 1.0 - min(1.0, remaining / spell.cooldown)


def pattern_conflicts_spell(pattern: Pattern) -> bool:
    return any(patterns_match(pattern, spell.pattern) for spell in SpellManager.SPELLS)


def non_spell_patterns(patterns: Sequence[Pattern]) -> tuple[Pattern, ...]:
    return tuple(pattern for pattern in patterns if not pattern_conflicts_spell(pattern))


def non_spell_layered_patterns(
    patterns: Sequence[tuple[Pattern, Pattern]],
) -> tuple[tuple[Pattern, Pattern], ...]:
    return tuple(
        layered
        for layered in patterns
        if not any(pattern_conflicts_spell(layer) for layer in layered)
    )


GHOST_SPECS = (
    GhostSpec("Wisp", PATTERN_POOL[0], 14.0, 100, 10, (205, 218, 232)),
    GhostSpec("Shade", PATTERN_POOL[4], 16.0, 130, 12, (205, 218, 232)),
    GhostSpec("Mourner", PATTERN_POOL[8], 18.0, 160, 14, (205, 218, 232)),
    GhostSpec("Lurker", PATTERN_POOL[5], 15.0, 190, 16, (205, 218, 232)),
)


@dataclass
class GameSession:
    SPAWN_CLEARANCE = 170.0
    MAX_WAVES = 3
    STAGE_ONE_SEAL_LIMITS = {1: 0, 2: 0, 3: 1}
    STAGE_TWO_SEAL_LIMITS = {1: 0, 2: 1, 3: 1}
    STAGE_ONE_WAVES = {
        1: (
            GhostKind.START_LOCKED,
            GhostKind.SLOWPOKE,
            GhostKind.START_LOCKED,
            GhostKind.SLOWPOKE,
            GhostKind.FORBIDDEN,
        ),
        2: (
            GhostKind.SLOWPOKE,
            GhostKind.START_LOCKED,
            GhostKind.FORBIDDEN,
            GhostKind.START_LOCKED,
            GhostKind.SLOWPOKE,
            GhostKind.FORBIDDEN,
        ),
        3: (
            GhostKind.START_LOCKED,
            GhostKind.FORBIDDEN,
            GhostKind.SLOWPOKE,
            GhostKind.START_LOCKED,
            GhostKind.FORBIDDEN,
            GhostKind.SLOWPOKE,
            GhostKind.START_LOCKED,
            GhostKind.FORBIDDEN,
        ),
    }
    STAGE_TWO_WAVES = {
        1: (
            GhostKind.BLINKING,
            GhostKind.WAVY,
            GhostKind.SLOWPOKE,
            GhostKind.PARTIAL,
            GhostKind.CREASE,
            GhostKind.START_LOCKED,
            GhostKind.PARTIAL,
        ),
        2: (
            GhostKind.CREASE,
            GhostKind.SLOWPOKE,
            GhostKind.CREEP,
            GhostKind.PARTIAL,
            GhostKind.CREASE,
            GhostKind.SNARL,
            GhostKind.BLINKING,
            GhostKind.WAVY,
        ),
        3: (
            GhostKind.CREASE,
            GhostKind.SNARL,
            GhostKind.CREASE,
            GhostKind.SLOWPOKE,
            GhostKind.PARTIAL,
            GhostKind.CREASE,
            GhostKind.START_LOCKED,
            GhostKind.FORBIDDEN,
            GhostKind.CREEP,
            GhostKind.SNARL,
        ),
    }

    rng: random.Random = field(default_factory=random.Random)
    max_health: int = 5
    health: int = 5
    score: int = 0
    stage: int = 1
    wave: int = 1
    spawn_queue: Deque[GhostSpec] = field(default_factory=deque)
    kind_queue: Deque[GhostKind] = field(default_factory=deque)
    ghosts: list[Ghost] = field(default_factory=list)
    spells: SpellManager = field(default_factory=SpellManager)
    last_message: str = ""
    last_match_count: int = 0
    last_spell_cast: bool = False
    last_spell_type: Optional[SpellType] = None
    defeated_events: list[tuple[float, float, int]] = field(default_factory=list)
    wave_required_patterns: list[Pattern] = field(default_factory=list)
    stage_cleared: bool = False
    boss: Optional[PitonBoss | WeaverBoss] = None
    boss_battle: bool = False
    boss_last_event: str = ""
    wave_seals_assigned: int = 0

    def reset(self) -> None:
        self.health = self.max_health
        self.score = 0
        self.stage = 1
        self.wave = 1
        self.spawn_queue.clear()
        self.kind_queue.clear()
        self.ghosts.clear()
        self.spells = SpellManager()
        self.last_message = ""
        self.last_match_count = 0
        self.last_spell_cast = False
        self.last_spell_type = None
        self.defeated_events.clear()
        self.boss_last_event = ""
        self.wave_required_patterns.clear()
        self.stage_cleared = False
        self.boss = None
        self.boss_battle = False
        self.boss_last_event = ""
        self.wave_seals_assigned = 0
        self.fill_wave()

    def start_stage(self, stage: int) -> None:
        if stage not in (1, 2):
            raise ValueError(f"Unsupported stage: {stage}")
        self.stage = stage
        self.wave = 1
        self.spells = SpellManager()
        self.spawn_queue.clear()
        self.kind_queue.clear()
        self.ghosts.clear()
        self.wave_required_patterns.clear()
        self.stage_cleared = False
        self.boss = None
        self.boss_battle = False
        self.boss_last_event = ""
        self.wave_seals_assigned = 0
        self.fill_wave()

    def fill_wave(self) -> None:
        waves = (
            self.STAGE_ONE_WAVES
            if self.stage == 1
            else self.STAGE_TWO_WAVES
        )
        kinds = waves.get(self.wave, ())
        specs = [self.rng.choice(GHOST_SPECS) for _ in kinds]
        self.spawn_queue.extend(specs)
        self.kind_queue.extend(kinds)
        self.wave_required_patterns.clear()
        self.wave_seals_assigned = 0

    def spawn_next(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
        allow_seal: bool = True,
    ) -> Optional[Ghost]:
        if not self.spawn_queue or not spawn_positions:
            return None
        available_positions = [
            position
            for position in spawn_positions
            if self._spawn_position_is_clear(position)
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
                    if self._spawn_position_is_clear(candidate):
                        extended_positions.append(candidate)
                if extended_positions:
                    available_positions = extended_positions
                    break
        if not available_positions:
            return None
        spec = self.spawn_queue.popleft()
        x, y = self.rng.choice(available_positions)
        planned_spawn = bool(self.kind_queue)
        kind = (
            self.kind_queue.popleft()
            if planned_spawn
            else self.rng.choices(
                tuple(GhostKind),
                weights=(
                    (36, 4, 6, 16, 4, 3, 0, 15, 8)
                    if self.stage == 1 and self.wave == 1
                    else (23, 6, 8, 16, 8, 5, 0, 16, 7)
                    if self.stage == 1
                    else (18, 7, 10, 14, 8, 9, 12, 14, 8)
                ),
                k=1,
            )[0]
        )
        if planned_spawn:
            pattern_count = self._planned_pattern_count(kind)
            pattern_pool = self._planned_pattern_pool(kind)
        else:
            pattern_count = self.rng.choices(
                (1, 2, 3), weights=(65, 30, 5), k=1
            )[0]
            if kind is GhostKind.CREEP:
                pattern_count = max(2, pattern_count)
            pattern_pool = PATTERN_POOL
        remaining_patterns: list[PatternAttempt] = list(
            self.rng.sample(pattern_pool, k=pattern_count)
        )
        crease_axis = ""
        crease_source_pattern: Pattern = ()
        crease_target_pattern: Pattern = ()
        crease_axes: list[str] = []
        if kind is GhostKind.CREASE:
            source_patterns = self.rng.sample(pattern_pool, k=pattern_count)
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
            snarl_count = (
                max(2, pattern_count)
                if planned_spawn and self.stage == 2
                else self.rng.choices((1, 2), weights=(70, 30), k=1)[0]
            )
            remaining_patterns = []
            complex_patterns = non_spell_patterns(COMPLEX_PATTERN_POOL)
            for _ in range(snarl_count):
                if self.rng.random() < 0.42:
                    remaining_patterns.append(
                        self.rng.choice(non_spell_layered_patterns(LAYERED_PATTERN_POOL))
                    )
                else:
                    remaining_patterns.append(self.rng.choice(complex_patterns))
        forbidden_patterns: list[Pattern] = []
        if kind is GhostKind.FORBIDDEN:
            overlapping = [
                ghost.pattern
                for ghost in self.ghosts
                if ghost.is_interactive and ghost.pattern not in remaining_patterns
            ]
            previous_wave_patterns = [
                pattern
                for pattern in self.wave_required_patterns
                if pattern not in remaining_patterns
            ]
            candidates = overlapping or previous_wave_patterns or [
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
        seal_limit = (
            self.STAGE_TWO_SEAL_LIMITS.get(self.wave, 1)
            if self.stage >= 2
            else self.STAGE_ONE_SEAL_LIMITS.get(self.wave, 0)
        )
        seal_eligible = self.stage >= 2 or (
            self.stage == 1 and kind is GhostKind.SLOWPOKE
        )
        if (
            allow_seal
            and seal_eligible
            and self.wave_seals_assigned < seal_limit
            and ghost.apply_random_seal(self.rng)
        ):
            self.wave_seals_assigned += 1
        ghost.start_moving_immediately()
        self.ghosts.append(ghost)
        self.wave_required_patterns.extend(
            pattern
            for pattern in remaining_patterns
            if isinstance(pattern[0], int)
        )
        return ghost

    def needs_seal_support(self) -> bool:
        sanctify = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        living = [
            ghost
            for ghost in self.ghosts
            if not ghost.vanishing and ghost.remaining_patterns
        ]
        return (
            not self.spawn_queue
            and bool(living)
            and self.spells.holy_power < sanctify.cost
            and all(0 in ghost.sealed_slots for ghost in living)
        )

    def spawn_seal_support(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
    ) -> Optional[Ghost]:
        if not self.needs_seal_support():
            return None
        self.spawn_queue.append(self.rng.choice(GHOST_SPECS[:2]))
        self.kind_queue.append(GhostKind.SLOWPOKE)
        ghost = self.spawn_next(
            spawn_positions,
            player_position,
            allow_seal=False,
        )
        if ghost is None:
            self.spawn_queue.pop()
            self.kind_queue.pop()
            return None
        short_patterns = tuple(
            pattern for pattern in PATTERN_POOL if len(pattern) == 3
        )
        ghost.remaining_patterns = [self.rng.choice(short_patterns)]
        ghost.start_locked_slots = [False]
        ghost.partial_slots = [False]
        ghost.sealed_slots.clear()
        ghost.forbidden_patterns.clear()
        return ghost

    def _spawn_position_is_clear(
        self,
        position: tuple[float, float],
    ) -> bool:
        if not all(
            ghost.vanishing
            or ghost.distance_to(position) >= self.SPAWN_CLEARANCE
            for ghost in self.ghosts
        ):
            return False
        if self.boss is None or self.boss.defeated:
            return True
        boss_positions = [(self.boss.x, self.boss.y)]
        if self.boss.hidden_remaining > 0:
            boss_positions.append((self.boss.pending_x, self.boss.pending_y))
        return all(
            math.dist(position, boss_position) >= self.SPAWN_CLEARANCE
            for boss_position in boss_positions
        )

    def _planned_pattern_count(self, kind: GhostKind) -> int:
        if self.stage == 2:
            if self.wave == 1:
                return 2
            if self.wave == 2:
                return 3 if kind is GhostKind.CREEP else 2
            if kind in (GhostKind.CREEP, GhostKind.START_LOCKED):
                return 3
            return self.rng.choice((2, 3))
        if self.wave == 1:
            return 1
        if self.wave == 2:
            return (
                self.rng.choice((2, 3))
                if kind is GhostKind.CREEP
                else self.rng.choice((1, 2))
            )
        if self.wave == 3:
            if kind is GhostKind.CREEP:
                return 3
            return 2
        if kind is GhostKind.CREEP:
            return self.rng.choice((3, 4))
        if kind is GhostKind.START_LOCKED:
            return self.rng.choice((2, 3))
        return 2

    def _planned_pattern_pool(self, kind: GhostKind) -> tuple[Pattern, ...]:
        short_patterns = tuple(
            pattern for pattern in PATTERN_POOL if len(pattern) == 3
        )
        medium_patterns = tuple(
            pattern for pattern in PATTERN_POOL if len(pattern) >= 4
        )
        if self.stage == 2:
            if self.wave == 1:
                return non_spell_patterns(STAGE_TWO_PATTERN_POOL)
            if self.wave == 2:
                return non_spell_patterns(
                    STAGE_TWO_PATTERN_POOL + COMPLEX_PATTERN_POOL[-4:]
                )
            return non_spell_patterns(STAGE_TWO_PATTERN_POOL + COMPLEX_PATTERN_POOL)
        if self.wave == 1:
            return short_patterns
        if self.wave == 2:
            return PATTERN_POOL
        if self.wave == 3:
            return medium_patterns
        if kind in (GhostKind.CREEP, GhostKind.START_LOCKED):
            return COMPLEX_PATTERN_POOL
        return medium_patterns

    def advance_wave_if_clear(self) -> bool:
        if self.boss_battle:
            return False
        if self.spawn_queue or self.ghosts:
            return False
        if self.wave >= self.MAX_WAVES:
            self.stage_cleared = True
            self.last_message = "STAGE CLEAR"
            return False
        self.wave += 1
        self.fill_wave()
        self.last_message = f"WAVE {self.wave}"
        return True

    def start_boss_battle(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
    ) -> PitonBoss:
        self.spawn_queue.clear()
        self.kind_queue.clear()
        self.ghosts.clear()
        boss_spec = GhostSpec(
            "Piton",
            COMPLEX_PATTERN_POOL[0],
            min(spec.speed for spec in GHOST_SPECS) / 1.7,
            4000,
            50,
            (180, 145, 220),
        )
        boss_patterns = non_spell_patterns(COMPLEX_PATTERN_POOL)
        rows = [self.rng.sample(boss_patterns, k=5) for _ in range(3)]
        position = self.rng.choice(tuple(spawn_positions))
        self.boss = PitonBoss(
            boss_spec,
            position[0],
            position[1],
            player_position[0],
            player_position[1],
            rows,
        )
        self.boss_battle = True
        self.stage_cleared = False
        self.boss_last_event = ""
        return self.boss

    def start_weaver_battle(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
    ) -> WeaverBoss:
        self.spawn_queue.clear()
        self.kind_queue.clear()
        self.ghosts.clear()
        boss_spec = GhostSpec(
            "Weaver",
            WEAVER_PATTERN_POOL[-1],
            min(spec.speed for spec in GHOST_SPECS) / 1.95,
            6500,
            70,
            (185, 170, 235),
        )
        rows: list[list[PatternAttempt]] = []
        axes = ("x", "y", "origin")
        weaver_patterns = non_spell_patterns(WEAVER_PATTERN_POOL)
        weaver_origin_patterns = non_spell_patterns(WEAVER_ORIGIN_PATTERN_POOL)
        weaver_layered_patterns = non_spell_layered_patterns(
            WEAVER_LAYERED_PATTERN_POOL
        )
        pattern_axis_rows: list[list[str]] = []
        for _ in range(4):
            row_entries: list[tuple[PatternAttempt, str]] = []
            for axis in axes:
                source_pool = (
                    weaver_origin_patterns
                    if axis == "origin"
                    else weaver_patterns
                )
                axis_patterns = tuple(
                    pattern
                    for pattern in source_pool
                    if not pattern_conflicts_spell(pattern)
                    and not pattern_conflicts_spell(mirrored_pattern(pattern, axis))
                )
                row_entries.append(
                    (self.rng.choice(axis_patterns), axis)
                )
            row_entries.extend(
                (pattern, "") for pattern in self.rng.sample(weaver_patterns, k=1)
            )
            row_entries.extend(
                (pattern, "")
                for pattern in self.rng.sample(weaver_layered_patterns, k=2)
            )
            self.rng.shuffle(row_entries)
            row = [pattern for pattern, _ in row_entries]
            row_axes = [axis for _, axis in row_entries]
            rows.append(row)
            pattern_axis_rows.append(row_axes)
        position = self.rng.choice(tuple(spawn_positions))
        self.boss = WeaverBoss(
            boss_spec,
            position[0],
            position[1],
            player_position[0],
            player_position[1],
            rows,
            radius=64,
            movement_duration=3.55,
            pattern_axis_rows=pattern_axis_rows,
        )
        self.boss_battle = True
        self.stage_cleared = False
        self.boss_last_event = ""
        return self.boss

    def spawn_boss_support(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
    ) -> Optional[Ghost]:
        if not self.boss_battle or self.boss is None or self.boss.defeated:
            return None
        if not self.spawn_queue:
            self.spawn_queue.append(self.rng.choice(GHOST_SPECS[:3]))
            support_kinds = (
                (GhostKind.SLOWPOKE,)
                if self.boss.row_number == 1
                else (
                    GhostKind.SLOWPOKE,
                    GhostKind.START_LOCKED,
                    GhostKind.FORBIDDEN,
                )
            )
            self.kind_queue.append(self.rng.choice(support_kinds))
        return self.spawn_next(spawn_positions, player_position)

    def spawn_weaver_snarl_burst(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
    ) -> list[Ghost]:
        if (
            not self.boss_battle
            or not isinstance(self.boss, WeaverBoss)
            or self.boss.defeated
            or (
                self.boss.pending_snarl_bursts <= 0
                and self.boss.pending_snarl_singles <= 0
            )
        ):
            return []
        count = 3
        if self.boss.pending_snarl_bursts > 0:
            self.boss.pending_snarl_bursts -= 1
        else:
            self.boss.pending_snarl_singles -= 1
            count = 1
        spawned: list[Ghost] = []
        for _ in range(count):
            self.spawn_queue.append(self.rng.choice(GHOST_SPECS[:3]))
            self.kind_queue.append(GhostKind.SNARL)
            ghost = self.spawn_next(
                spawn_positions,
                player_position,
                allow_seal=False,
            )
            if ghost is not None:
                spawned.append(ghost)
        return spawned

    def update_boss(
        self,
        seconds: float,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
        player_radius: float,
    ) -> int:
        if self.boss is None:
            return 0
        self.boss.update(seconds, self.rng)
        if isinstance(self.boss, WeaverBoss):
            spell_type = self.boss.consume_web_spell()
            if spell_type is not None:
                self.spells.slow_cooldown(spell_type, self.boss.web_spell_duration)
            for ghost in self.ghosts:
                if (
                    ghost.is_interactive
                    and self.boss.web_affects_position((ghost.x, ghost.y))
                ):
                    ghost.slow_remaining = max(
                        ghost.slow_remaining,
                        2.0 if ghost.slow_remaining > 0 else 1.0,
                    )
        if (
            self.boss.is_interactive
            and self.boss.distance_to(player_position)
            <= player_radius + self.boss.radius
        ):
            self.damage(2)
            position = self._clear_boss_spawn_position(
                spawn_positions,
                player_position,
            )
            self.boss.retreat_and_reposition(position)
            return 2
        return 0

    def _clear_boss_spawn_position(
        self,
        spawn_positions: Sequence[tuple[float, float]],
        player_position: tuple[float, float],
    ) -> tuple[float, float]:
        candidates = [
            position
            for position in spawn_positions
            if all(
                ghost.vanishing
                or ghost.distance_to(position) >= self.SPAWN_CLEARANCE
                for ghost in self.ghosts
            )
        ]
        if candidates:
            return self.rng.choice(candidates)
        base_positions = tuple(spawn_positions)
        for extension in (1.35, 1.7, 2.05, 2.4, 2.8):
            for position in base_positions:
                dx = position[0] - player_position[0]
                dy = position[1] - player_position[1]
                candidate = (
                    player_position[0] + dx * extension,
                    player_position[1] + dy * extension,
                )
                if all(
                    ghost.vanishing
                    or ghost.distance_to(candidate) >= self.SPAWN_CLEARANCE
                    for ghost in self.ghosts
                ):
                    return candidate
        position = self.rng.choice(base_positions)
        dx = position[0] - player_position[0]
        dy = position[1] - player_position[1]
        return (
            player_position[0] + dx * 3.2,
            player_position[1] + dy * 3.2,
        )

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

    def defeat_all_ghosts(self) -> None:
        self.spawn_queue.clear()
        self.kind_queue.clear()
        for ghost in self.ghosts:
            if ghost.vanishing:
                continue
            ghost.hidden_remaining = 0.0
            ghost.reappear_remaining = 0.0
            ghost.spawn_elapsed = ghost.spawn_duration
            ghost.knockback_active = False
            ghost.movement_phase = "pause"
            ghost.movement_elapsed = 0.0
            ghost.vanishing = True
            ghost.fade_remaining = ghost.fade_duration

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
            if (
                self.boss is not None
                and self.boss_battle
                and self.boss.is_spell_sealed(spell.spell_type)
            ):
                self.last_message = ""
                return PatternResult.MISSED
            if not self.spells.can_cast(spell):
                self.last_message = ""
                return PatternResult.MISSED
            self.last_spell_cast = True
            self.last_spell_type = spell.spell_type
            self._cast_spell(spell)
            self.last_message = ""
            return PatternResult.SPELL

        boss_result = ""
        if self.boss is not None and self.boss_battle:
            boss_result = self.boss.hit_pattern(entered, self.rng)
            if boss_result:
                self.last_match_count += 1
                self.boss_last_event = boss_result
                if boss_result == "row":
                    self.score += 700
                elif boss_result == "defeated":
                    self.score += self.boss.spec.score
                    self.spells.gain(self.boss.spec.holy_power)
                    self.defeat_all_ghosts()
                    self.defeated_events.append(
                        (self.boss.x, self.boss.y, self.boss.spec.holy_power)
                    )

        active_ghosts = [ghost for ghost in self.ghosts if ghost.is_interactive]
        if not active_ghosts and not boss_result:
            self.last_message = ""
            return PatternResult.MISSED

        matched = [ghost for ghost in active_ghosts if ghost.matches_required(entered)]
        self.last_match_count += len(matched)
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

        if matched or boss_result:
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
        ghosts_are_clear = all(
            other is ghost
            or other.vanishing
            or other.hidden_remaining > 0
            or math.hypot(other.x - candidate[0], other.y - candidate[1])
            >= self.SPAWN_CLEARANCE
            for other in self.ghosts
        )
        boss_is_clear = (
            self.boss is None
            or self.boss.defeated
            or self.boss.distance_to(candidate) >= self.SPAWN_CLEARANCE
        )
        return ghosts_are_clear and boss_is_clear

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
                    webbed = (
                        isinstance(self.boss, WeaverBoss)
                        and self.boss.web_affects_position((ghost.x, ghost.y))
                    )
                    ghost.repel(
                        self.spells.REPEL_DISTANCE * (0.5 if webbed else 1.0)
                    )
                    ghost.slow_remaining = (
                        self.spells.REPEL_SLOW_DURATION * (2.0 if webbed else 1.0)
                    )
            if (
                self.boss is not None
                and self.boss_battle
                and self.boss.is_interactive
                and self.boss.distance_to(
                    (self.boss.target_x, self.boss.target_y)
                )
                <= self.spells.REPEL_RADIUS
            ):
                self.boss.repel(self.spells.REPEL_DISTANCE)
        elif spell.spell_type is SpellType.NULLIFY:
            self.spells.spend(spell)
            self.spells.clear_cooldown_drags()
            if self.boss is not None and self.boss_battle:
                if isinstance(self.boss, WeaverBoss):
                    self.boss.recently_purified_slots.update(
                        self.boss.sealed_slots
                    )
                    self.boss.sealed_slots.clear()
                    self.boss.seal_waiting_for_purify = False
                    self.boss.seal_timer = self.boss.seal_refill_delay
                    self.boss.clear_web_effects()
                else:
                    self.boss.purify_one()
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
