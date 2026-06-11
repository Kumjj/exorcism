from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
import math
import random
from typing import Deque, Iterable, Optional, Sequence


Pattern = tuple[int, ...]
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


class SpellType(Enum):
    HEAL = auto()
    REPEL = auto()
    NULLIFY = auto()
    SLOW = auto()


@dataclass(frozen=True)
class SpellDefinition:
    spell_type: SpellType
    name: str
    pattern: Pattern
    cost: int
    description: str


def patterns_match(entered: Pattern, expected: Pattern, strict_start: bool = False) -> bool:
    if entered == expected:
        return True
    return not strict_start and entered == tuple(reversed(expected))


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
    remaining_patterns: list[Pattern] = field(default_factory=list)
    vanishing: bool = False
    fade_remaining: float = 0.0
    fade_duration: float = 0.85
    movement_phase: str = "pause"
    movement_elapsed: float = 0.0
    movement_pause: float = 0.85
    movement_duration: float = 1.1
    step_start_x: float = 0.0
    step_start_y: float = 0.0
    step_end_x: float = 0.0
    step_end_y: float = 0.0
    kind: GhostKind = GhostKind.SLOWPOKE
    forbidden_patterns: list[Pattern] = field(default_factory=list)
    spawn_elapsed: float = 0.0
    spawn_duration: float = 0.7
    slow_remaining: float = 0.0
    resonance_remaining: float = 0.0
    removed_pattern: Pattern = ()
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

    def __post_init__(self) -> None:
        if not self.remaining_patterns:
            self.remaining_patterns = [self.spec.pattern]

    @property
    def pattern(self) -> Pattern:
        return self.remaining_patterns[0] if self.remaining_patterns else ()

    @property
    def is_resonant(self) -> bool:
        return self.kind is GhostKind.FORBIDDEN

    @property
    def strict_start(self) -> bool:
        return self.kind is GhostKind.START_LOCKED

    def matches_required(self, entered: Pattern) -> bool:
        return patterns_match(entered, self.pattern, self.strict_start)

    def matches_forbidden(self, entered: Pattern) -> bool:
        return any(
            patterns_match(entered, forbidden)
            for forbidden in self.forbidden_patterns
        )

    def update(self, seconds: float) -> None:
        self.spawn_elapsed = min(self.spawn_duration, self.spawn_elapsed + seconds)
        if self.pattern_transition_elapsed < self.pattern_transition_duration:
            self.pattern_transition_elapsed = min(
                self.pattern_transition_duration,
                self.pattern_transition_elapsed + seconds,
            )
            if self.pattern_transition_elapsed >= self.pattern_transition_duration:
                self.removed_pattern = ()
        self.slow_remaining = max(0.0, self.slow_remaining - seconds)
        self.resonance_remaining = max(
            0.0, self.resonance_remaining - seconds
        )
        if self.vanishing:
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

    def distance_to(self, position: tuple[float, float]) -> float:
        return math.hypot(self.x - position[0], self.y - position[1])

    def resonate(self) -> None:
        self.resonance_remaining = self.RESONANCE_DURATION

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
        self.pattern_transition_elapsed = 0.0
        if not self.remaining_patterns:
            self.vanishing = True
            self.fade_remaining = self.fade_duration
        return True

    @property
    def alpha(self) -> int:
        spawn_alpha = min(1.0, self.spawn_elapsed / self.spawn_duration)
        vanish_alpha = (
            self.fade_remaining / self.fade_duration if self.vanishing else 1.0
        )
        return round(255 * spawn_alpha * vanish_alpha)

    @property
    def pattern_transition_progress(self) -> float:
        if not self.removed_pattern:
            return 1.0
        return min(
            1.0,
            self.pattern_transition_elapsed / self.pattern_transition_duration,
        )


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
    SLOW_DURATION = 9.0
    SPELLS = (
        SpellDefinition(
            SpellType.HEAL,
            "HEAL",
            (6, 4, 2, 1, 0, 5, 8),
            40,
            "+2 HP",
        ),
        SpellDefinition(
            SpellType.REPEL,
            "REPEL",
            (0, 4, 8, 5, 2),
            35,
            "Push ghosts away",
        ),
        SpellDefinition(
            SpellType.NULLIFY,
            "SANCTIFY",
            (0, 1, 4, 7, 8),
            45,
            "Clear nearby gimmicks",
        ),
        SpellDefinition(
            SpellType.SLOW,
            "SLOW",
            (2, 1, 4, 3, 6),
            45,
            "Slow current ghosts 9s",
        ),
    )
    HEAL_PATTERN = SPELLS[0].pattern
    HEAL_COST = SPELLS[0].cost

    def __init__(self) -> None:
        self.holy_power = 0

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
        return self.holy_power >= spell.cost

    def spend(self, spell: SpellDefinition) -> None:
        self.holy_power -= spell.cost


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
        pattern_count = self.rng.choices(
            (1, 2, 3), weights=(65, 30, 5), k=1
        )[0]
        remaining_patterns = self.rng.sample(PATTERN_POOL, k=pattern_count)
        kind_weights = (
            (75, 5, 8, 7, 3, 2)
            if self.wave == 1
            else (55, 8, 10, 10, 10, 7)
        )
        kind = self.rng.choices(tuple(GhostKind), weights=kind_weights, k=1)[0]
        forbidden_patterns: list[Pattern] = []
        if kind is GhostKind.FORBIDDEN:
            overlapping = [
                ghost.pattern
                for ghost in self.ghosts
                if not ghost.vanishing and ghost.pattern not in remaining_patterns
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
        )
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
        escaped = 0
        for ghost in list(self.ghosts):
            ghost.update(seconds)
            if ghost.vanishing and ghost.fade_remaining <= 0:
                self.ghosts.remove(ghost)
            elif (
                not ghost.vanishing
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

    def judge_pattern(self, pattern: Iterable[int]) -> PatternResult:
        entered = tuple(pattern)
        self.last_match_count = 0
        self.last_spell_cast = False
        self.last_spell_type = None
        self.defeated_events.clear()
        if not entered:
            return PatternResult.EMPTY

        spell = self.spells.matching_spell(entered)
        if spell is not None:
            if not self.spells.can_cast(spell):
                self.last_message = ""
                return PatternResult.MISSED
            self.last_spell_cast = True
            self.last_spell_type = spell.spell_type
            self._cast_spell(spell)
            self.last_message = ""
            return PatternResult.SPELL

        active_ghosts = [ghost for ghost in self.ghosts if not ghost.vanishing]
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
        forbidden_hits = [
            ghost
            for ghost in active_ghosts
            if all(ghost is not matched_ghost for matched_ghost in matched)
            and ghost.matches_forbidden(entered)
        ]
        if forbidden_hits:
            for ghost in forbidden_hits:
                ghost.resonate()
            self.last_message = ""
            return PatternResult.RESONATED

        if matched:
            self.last_message = ""
            return PatternResult.HIT

        self.last_message = ""
        return PatternResult.MISSED

    def _cast_spell(self, spell: SpellDefinition) -> None:
        active_ghosts = [ghost for ghost in self.ghosts if not ghost.vanishing]
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
        elif spell.spell_type is SpellType.NULLIFY:
            self.spells.spend(spell)
            for ghost in active_ghosts:
                if ghost.distance_to((ghost.target_x, ghost.target_y)) <= (
                    self.spells.NULLIFY_RADIUS
                ):
                    ghost.nullify_gimmick()
        elif spell.spell_type is SpellType.SLOW:
            self.spells.spend(spell)
            for ghost in active_ghosts:
                ghost.slow_remaining = self.spells.SLOW_DURATION

    def target_ghost(self) -> Optional[Ghost]:
        if not self.ghosts:
            return None
        return min(
            (ghost for ghost in self.ghosts if not ghost.vanishing),
            key=lambda ghost: ghost.distance_to((ghost.target_x, ghost.target_y)),
            default=None,
        )
