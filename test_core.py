import random
import unittest

from core import (
    GHOST_SPECS,
    GameSession,
    Ghost,
    GhostKind,
    PatternInput,
    PatternResult,
    SpellManager,
    SpellType,
    STAGE_TWO_PATTERN_POOL,
    WEAVER_LAYERED_PATTERN_POOL,
    WEAVER_ORIGIN_PATTERN_POOL,
    WEAVER_PATTERN_POOL,
    WeaverBoss,
    mirrored_pattern,
    pattern_conflicts_spell,
    pattern_attempt_matches,
)


def has_diagonal_edge(pattern: tuple[int, ...]) -> bool:
    for first, second in zip(pattern, pattern[1:]):
        first_row, first_col = divmod(first, 3)
        second_row, second_col = divmod(second, 3)
        if abs(first_row - second_row) == 1 and abs(first_col - second_col) == 1:
            return True
    return False


def is_straight_pattern(pattern: tuple[int, ...]) -> bool:
    rows = {divmod(node, 3)[0] for node in pattern}
    cols = {divmod(node, 3)[1] for node in pattern}
    return len(rows) == 1 or len(cols) == 1


class PatternInputTests(unittest.TestCase):
    def test_records_each_node_once(self) -> None:
        pattern_input = PatternInput()
        pattern_input.begin(0)
        pattern_input.add(1)
        pattern_input.add(1)
        pattern_input.add(4)

        self.assertEqual(pattern_input.finish(), (0, 1, 4))
        self.assertEqual(pattern_input.nodes, [])
        self.assertFalse(pattern_input.dragging)


class GameSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = GameSession(rng=random.Random(7))
        self.normal = Ghost(GHOST_SPECS[0], 700, 200, 400, 300)
        self.forbidden = Ghost(
            GHOST_SPECS[-1],
            600,
            300,
            400,
            300,
            kind=GhostKind.FORBIDDEN,
            forbidden_patterns=[(0, 4, 8)],
        )

    def test_last_correct_pattern_starts_vanishing(self) -> None:
        self.session.ghosts = [self.normal]

        result = self.session.judge_pattern(self.normal.pattern)

        self.assertEqual(result, PatternResult.HIT)
        self.assertEqual(self.session.ghosts, [self.normal])
        self.assertTrue(self.normal.vanishing)
        self.assertEqual(self.normal.remaining_patterns, [])
        self.assertEqual(self.session.score, self.normal.spec.score)
        self.assertEqual(
            self.session.spells.holy_power, self.normal.spec.holy_power
        )

    def test_matching_input_removes_first_pattern_from_every_ghost(self) -> None:
        shared_pattern = (0, 1, 2)
        first = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[shared_pattern, (3, 4, 5)],
        )
        second = Ghost(
            GHOST_SPECS[1],
            100,
            200,
            400,
            300,
            remaining_patterns=[shared_pattern, (6, 7, 8)],
        )
        self.session.ghosts = [first, second]

        result = self.session.judge_pattern(shared_pattern)

        self.assertEqual(result, PatternResult.HIT)
        self.assertEqual(first.remaining_patterns, [(3, 4, 5)])
        self.assertEqual(second.remaining_patterns, [(6, 7, 8)])
        self.assertFalse(first.vanishing)
        self.assertFalse(second.vanishing)

    def test_correct_and_forbidden_patterns_are_judged_independently(self) -> None:
        forbidden_pattern = self.forbidden.forbidden_patterns[0]
        matching = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[forbidden_pattern],
        )
        self.session.ghosts = [matching, self.forbidden]

        result = self.session.judge_pattern(forbidden_pattern)

        self.assertEqual(result, PatternResult.RESONATED)
        self.assertTrue(matching.vanishing)
        self.assertEqual(
            self.forbidden.resonance_remaining,
            self.forbidden.RESONANCE_DURATION,
        )
        self.assertEqual(self.forbidden.forbidden_patterns, [])
        self.assertEqual(self.forbidden.removed_forbidden_pattern, forbidden_pattern)
        self.assertEqual(self.forbidden.pattern_transition_progress, 0.0)
        self.assertEqual(self.session.health, 5)

    def test_forbidden_pattern_accelerates_trap_ghost(self) -> None:
        self.session.ghosts = [self.forbidden]

        result = self.session.judge_pattern(self.forbidden.forbidden_patterns[0])

        self.assertEqual(result, PatternResult.RESONATED)
        self.assertEqual(
            self.forbidden.resonance_remaining,
            self.forbidden.RESONANCE_DURATION,
        )
        self.assertEqual(self.forbidden.forbidden_patterns, [])
        self.assertEqual(self.session.health, 5)

    def test_forbidden_acceleration_expires(self) -> None:
        self.forbidden.resonate()

        self.forbidden.update(self.forbidden.RESONANCE_DURATION + 0.1)

        self.assertEqual(self.forbidden.resonance_remaining, 0.0)

    def test_forbidden_acceleration_refreshes_instead_of_stacking(self) -> None:
        self.forbidden.resonate()
        self.forbidden.update(1.0)

        self.forbidden.resonate()

        self.assertEqual(
            self.forbidden.resonance_remaining,
            self.forbidden.RESONANCE_DURATION,
        )

    def test_normal_ghost_accepts_reverse_direction(self) -> None:
        self.session.ghosts = [self.normal]

        result = self.session.judge_pattern(tuple(reversed(self.normal.pattern)))

        self.assertEqual(result, PatternResult.HIT)
        self.assertTrue(self.normal.vanishing)

    def test_start_locked_ghost_requires_exact_direction(self) -> None:
        locked = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            kind=GhostKind.START_LOCKED,
        )
        self.session.ghosts = [locked]

        result = self.session.judge_pattern(tuple(reversed(locked.pattern)))

        self.assertEqual(result, PatternResult.MISSED)
        self.assertFalse(locked.vanishing)

    def test_start_lock_stays_attached_to_its_original_pattern(self) -> None:
        locked = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
            kind=GhostKind.START_LOCKED,
        )
        self.session.ghosts = [locked]

        result = self.session.judge_pattern((0, 1, 2))

        self.assertEqual(result, PatternResult.HIT)
        self.assertEqual(locked.kind, GhostKind.START_LOCKED)
        self.assertEqual(locked.remaining_patterns, [(3, 4, 5)])
        self.assertEqual(locked.start_locked_slots, [False])
        result = self.session.judge_pattern((5, 4, 3))
        self.assertEqual(result, PatternResult.HIT)

    def test_start_lock_can_be_explicitly_attached_to_multiple_patterns(self) -> None:
        locked = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
            kind=GhostKind.START_LOCKED,
            start_locked_slots=[True, True],
        )
        self.session.ghosts = [locked]

        self.assertEqual(
            self.session.judge_pattern((0, 1, 2)),
            PatternResult.HIT,
        )
        self.assertEqual(
            self.session.judge_pattern((5, 4, 3)),
            PatternResult.MISSED,
        )

    def test_partial_gimmick_does_not_move_to_the_next_pattern(self) -> None:
        partial = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
            kind=GhostKind.PARTIAL,
        )

        self.assertEqual(partial.partial_slots, [True, False])
        partial.remove_first_pattern()

        self.assertTrue(partial.removed_partial)
        self.assertFalse(partial.partial_pattern)
        self.assertEqual(partial.partial_slots, [False])

    def test_heal_consumes_power_and_restores_health(self) -> None:
        self.session.health = 2
        self.session.spells.holy_power = SpellManager.HEAL_COST

        result = self.session.judge_pattern(SpellManager.HEAL_PATTERN)

        self.assertEqual(result, PatternResult.SPELL)
        self.assertEqual(self.session.health, 4)
        self.assertEqual(self.session.spells.holy_power, 0)

    def test_heal_does_not_consume_power_at_full_health(self) -> None:
        self.session.spells.holy_power = SpellManager.HEAL_COST

        result = self.session.judge_pattern(SpellManager.HEAL_PATTERN)

        self.assertEqual(result, PatternResult.SPELL)
        self.assertTrue(self.session.last_spell_cast)
        self.assertEqual(self.session.health, self.session.max_health)
        self.assertEqual(
            self.session.spells.holy_power, SpellManager.HEAL_COST
        )

    def test_holy_power_capacity_is_one_hundred_fifty(self) -> None:
        self.session.spells.gain(999)

        self.assertEqual(
            self.session.spells.holy_power, SpellManager.MAX_POWER
        )

    def test_failed_pattern_does_not_cost_health(self) -> None:
        self.session.ghosts = [self.normal]

        result = self.session.judge_pattern((8, 7, 6))

        self.assertEqual(result, PatternResult.MISSED)
        self.assertEqual(self.session.health, 5)

    def test_ghost_eases_toward_player_smoothly(self) -> None:
        ghost = Ghost(GHOST_SPECS[0], 100, 100, 400, 400)
        before = ghost.distance_to((400, 400))

        ghost.update(0.4)

        self.assertGreater(ghost.x, 100)
        self.assertGreater(ghost.y, 100)
        self.assertLess(ghost.distance_to((400, 400)), before)

    def test_spawn_uses_one_of_the_eight_positions(self) -> None:
        positions = tuple((float(index), float(index * 2)) for index in range(8))
        self.session.spawn_queue.append(GHOST_SPECS[0])

        ghost = self.session.spawn_next(positions, (400, 300))

        self.assertIsNotNone(ghost)
        self.assertIn((ghost.x, ghost.y), positions)
        self.assertEqual((ghost.target_x, ghost.target_y), (400, 300))
        self.assertGreaterEqual(len(ghost.remaining_patterns), 1)
        self.assertLessEqual(len(ghost.remaining_patterns), 3)

    def test_occupied_spawn_position_places_new_ghost_farther_back(self) -> None:
        occupied = Ghost(GHOST_SPECS[0], 0, 0, 400, 300)
        self.session.ghosts = [occupied]
        self.session.spawn_queue.append(GHOST_SPECS[0])

        ghost = self.session.spawn_next(((0.0, 0.0),), (400, 300))

        self.assertIsNotNone(ghost)
        self.assertGreaterEqual(
            ghost.distance_to((occupied.x, occupied.y)),
            self.session.SPAWN_CLEARANCE,
        )
        self.assertGreater(
            ghost.distance_to((400, 300)),
            occupied.distance_to((400, 300)),
        )
        self.assertEqual(len(self.session.spawn_queue), 0)

    def test_spawn_chooses_a_clear_position(self) -> None:
        occupied = Ghost(GHOST_SPECS[0], 0, 0, 400, 300)
        self.session.ghosts = [occupied]
        self.session.spawn_queue.append(GHOST_SPECS[0])

        ghost = self.session.spawn_next(
            ((0.0, 0.0), (400.0, 0.0)), (400, 300)
        )

        self.assertIsNotNone(ghost)
        self.assertEqual((ghost.x, ghost.y), (400.0, 0.0))

    def test_one_or_two_patterns_spawn_much_more_often(self) -> None:
        counts = {1: 0, 2: 0, 3: 0}
        for _ in range(200):
            self.session.spawn_queue.append(GHOST_SPECS[0])
            ghost = self.session.spawn_next(((0.0, 0.0),), (400, 300))
            counts[len(ghost.remaining_patterns)] += 1
            self.session.ghosts.clear()

        self.assertGreater(counts[1], counts[2])
        self.assertGreater(counts[2], counts[3])
        self.assertGreater(counts[1] + counts[2], 180)

    def test_stage_one_uses_three_curated_waves(self) -> None:
        for wave, expected_kinds in GameSession.STAGE_ONE_WAVES.items():
            self.session.wave = wave
            self.session.spawn_queue.clear()
            self.session.kind_queue.clear()
            self.session.fill_wave()

            self.assertEqual(tuple(self.session.kind_queue), expected_kinds)
            self.assertEqual(len(self.session.spawn_queue), len(expected_kinds))
            self.assertTrue(
                set(expected_kinds)
                <= {
                    GhostKind.SLOWPOKE,
                    GhostKind.START_LOCKED,
                    GhostKind.FORBIDDEN,
                }
            )
            self.assertNotIn(GhostKind.CREEP, expected_kinds)

    def test_stage_two_mixes_more_reversed_and_normal_ghosts(self) -> None:
        for wave, expected_kinds in GameSession.STAGE_TWO_WAVES.items():
            self.session.stage = 2
            self.session.wave = wave
            self.session.spawn_queue.clear()
            self.session.kind_queue.clear()
            self.session.fill_wave()

            self.assertEqual(tuple(self.session.kind_queue), expected_kinds)
            self.assertEqual(len(self.session.spawn_queue), len(expected_kinds))
            self.assertGreaterEqual(expected_kinds.count(GhostKind.CREASE), 1)
            self.assertIn(GhostKind.SLOWPOKE, expected_kinds)

        self.assertGreaterEqual(
            GameSession.STAGE_TWO_WAVES[3].count(GhostKind.CREASE),
            3,
        )
        self.assertIn(GhostKind.CREEP, GameSession.STAGE_TWO_WAVES[2])
        self.assertIn(GhostKind.CREEP, GameSession.STAGE_TWO_WAVES[3])

    def test_start_stage_two_resets_queues_and_fills_first_wave(self) -> None:
        self.session.ghosts = [self.normal]
        self.session.wave = 3
        self.session.stage_cleared = True

        self.session.start_stage(2)

        self.assertEqual(self.session.stage, 2)
        self.assertEqual(self.session.wave, 1)
        self.assertFalse(self.session.stage_cleared)
        self.assertEqual(self.session.ghosts, [])
        self.assertEqual(
            tuple(self.session.kind_queue),
            GameSession.STAGE_TWO_WAVES[1],
        )

    def test_stage_two_starts_with_longer_two_pattern_ghosts(self) -> None:
        self.session.start_stage(2)
        sealed_count = 0

        while self.session.spawn_queue:
            ghost = self.session.spawn_next(
                ((800.0, 300.0),),
                (400.0, 300.0),
            )
            self.assertIsNotNone(ghost)
            self.assertGreaterEqual(len(ghost.remaining_patterns), 2)
            sealed_count += bool(ghost.sealed_slots)
            for pattern in ghost.remaining_patterns:
                self.assertFalse(isinstance(pattern[0], tuple))
                self.assertGreaterEqual(len(pattern), 4)
            self.session.ghosts.clear()
        self.assertEqual(
            sealed_count,
            GameSession.STAGE_TWO_SEAL_LIMITS[1],
        )

    def test_seal_support_spawns_when_only_blocked_ghosts_remain(self) -> None:
        blocked = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2)],
            sealed_slots={0},
        )
        self.session.ghosts = [blocked]
        self.session.spawn_queue.clear()
        self.session.kind_queue.clear()
        self.session.spells.holy_power = 0

        support = self.session.spawn_seal_support(
            ((900.0, 500.0),),
            (400.0, 300.0),
        )

        self.assertIsNotNone(support)
        self.assertEqual(support.kind, GhostKind.SLOWPOKE)
        self.assertEqual(len(support.remaining_patterns), 1)
        self.assertEqual(len(support.remaining_patterns[0]), 3)
        self.assertEqual(support.sealed_slots, set())

    def test_seal_support_does_not_spawn_when_sanctify_is_affordable(self) -> None:
        blocked = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2)],
            sealed_slots={0},
        )
        sanctify = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        self.session.ghosts = [blocked]
        self.session.spells.holy_power = sanctify.cost

        self.assertFalse(self.session.needs_seal_support())

    def test_regular_ghost_can_seal_only_one_pattern(self) -> None:
        ghost = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5), (6, 7, 8)],
        )

        self.assertTrue(ghost.apply_random_seal(self.session.rng))
        self.assertFalse(ghost.apply_random_seal(self.session.rng))
        self.assertEqual(len(ghost.sealed_slots), 1)

    def test_stage_one_adds_one_sealed_ghost_only_in_final_wave(self) -> None:
        for wave, expected_seals in (
            (1, 0),
            (2, 0),
            (3, 1),
        ):
            self.session.stage = 1
            self.session.wave = wave
            self.session.spawn_queue.clear()
            self.session.kind_queue.clear()
            self.session.ghosts.clear()
            self.session.fill_wave()
            sealed_count = 0

            while self.session.spawn_queue:
                ghost = self.session.spawn_next(
                    ((800.0, 300.0),),
                    (400.0, 300.0),
                )
                self.assertIsNotNone(ghost)
                sealed_count += bool(ghost.sealed_slots)
                self.session.ghosts.clear()

            self.assertEqual(sealed_count, expected_seals)

    def test_starting_a_new_stage_resets_holy_power_and_cooldowns(self) -> None:
        self.session.spells.holy_power = SpellManager.MAX_POWER
        self.session.spells.cooldowns[SpellType.NULLIFY] = 5.0

        self.session.start_stage(2)

        self.assertEqual(self.session.spells.holy_power, 0)
        self.assertTrue(
            all(
                remaining == 0
                for remaining in self.session.spells.cooldowns.values()
            )
        )

    def test_weaver_has_four_rows_of_six_harder_patterns(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )

        self.assertIsInstance(boss, WeaverBoss)
        self.assertEqual(len(boss.rows), 4)
        self.assertTrue(all(len(row) == 6 for row in boss.rows))
        self.assertTrue(
            any(isinstance(pattern[0], tuple) for row in boss.rows for pattern in row)
        )

    def test_weaver_rows_include_mirrored_patterns(self) -> None:
        mirrored_by_axis = {
            axis: {mirrored_pattern(pattern, axis) for pattern in WEAVER_PATTERN_POOL}
            for axis in ("x", "y", "origin")
        }
        mirrored = {
            mirrored_pattern(pattern, axis)
            for pattern in WEAVER_PATTERN_POOL
            for axis in ("x", "y", "origin")
        }
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )

        self.assertTrue(
            any(
                mirrored_pattern(pattern, axis) in mirrored
                for row, axes in zip(boss.rows, boss.pattern_axis_rows)
                for pattern, axis in zip(row, axes)
                if pattern and isinstance(pattern[0], int)
                and axis
            )
        )
        for row, axes in zip(boss.rows, boss.pattern_axis_rows):
            simple_patterns = [
                mirrored_pattern(pattern, axis)
                for pattern, axis in zip(row, axes)
                if pattern and isinstance(pattern[0], int)
                and axis
            ]
            for axis in ("x", "y", "origin"):
                self.assertTrue(
                    any(pattern in mirrored_by_axis[axis] for pattern in simple_patterns)
                )
        for axes in boss.pattern_axis_rows:
            self.assertEqual(sorted(axis for axis in axes if axis), ["origin", "x", "y"])
        self.assertEqual(sorted(axis for axis in boss.pattern_axes if axis), ["origin", "x", "y"])

    def test_weaver_origin_symmetry_uses_easy_straight_patterns(self) -> None:
        self.assertTrue(
            all(
                is_straight_pattern(pattern)
                for pattern in WEAVER_ORIGIN_PATTERN_POOL
            )
        )
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )

        for row, axes in zip(boss.rows, boss.pattern_axis_rows):
            origin_patterns = [
                pattern
                for pattern, axis in zip(row, axes)
                if axis == "origin"
            ]
            self.assertEqual(len(origin_patterns), 1)
            self.assertTrue(is_straight_pattern(origin_patterns[0]))

    def test_weaver_mirrored_slot_requires_unmirrored_input(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        mirrored_index = next(
            index for index, axis in enumerate(boss.pattern_axes) if axis
        )
        pattern = boss.patterns[mirrored_index]
        axis = boss.pattern_axes[mirrored_index]
        displayed_pattern = mirrored_pattern(pattern, axis)
        boss.patterns = [pattern]
        boss.pattern_axes = [axis]
        boss.sealed_slots.clear()
        boss.spawn_elapsed = boss.spawn_duration

        self.assertEqual(
            self.session.judge_pattern(displayed_pattern),
            PatternResult.MISSED,
        )
        self.assertEqual(self.session.judge_pattern(pattern), PatternResult.HIT)

        self.assertEqual(len(boss.patterns), len(boss.pattern_axes))

    def test_weaver_single_patterns_use_readable_diagonal_paths(self) -> None:
        for pattern in WEAVER_PATTERN_POOL:
            self.assertLessEqual(len(pattern), 6)
            self.assertTrue(has_diagonal_edge(pattern))

    def test_stage_two_pattern_pool_reduces_straight_lines(self) -> None:
        self.assertTrue(
            all(has_diagonal_edge(pattern) for pattern in STAGE_TWO_PATTERN_POOL)
        )

    def test_weaver_layered_patterns_carry_extra_complexity(self) -> None:
        self.assertTrue(
            all(
                sum(len(layer) for layer in layered) >= 7
                for layered in WEAVER_LAYERED_PATTERN_POOL
            )
        )

    def test_boss_patterns_do_not_overlap_spell_patterns(self) -> None:
        piton = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        self.assertTrue(
            all(
                not pattern_conflicts_spell(pattern)
                for row in piton.rows
                for pattern in row
            )
        )

        for seed in range(12):
            session = GameSession(rng=random.Random(seed))
            weaver = session.start_weaver_battle(
                ((800.0, 300.0),),
                (400.0, 300.0),
            )
            for row in weaver.rows:
                for pattern in row:
                    if pattern and isinstance(pattern[0], tuple):
                        self.assertTrue(
                            all(
                                not pattern_conflicts_spell(layer)
                                for layer in pattern
                            )
                        )
                    else:
                        self.assertFalse(pattern_conflicts_spell(pattern))

    def test_weaver_timed_snarl_burst_spawns_three_snarl_ghosts(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0), (950.0, 300.0), (1100.0, 300.0)),
            (400.0, 300.0),
        )
        boss.pending_snarl_bursts = 1

        spawned = self.session.spawn_weaver_snarl_burst(
            ((800.0, 300.0), (950.0, 300.0), (1100.0, 300.0)),
            (400.0, 300.0),
        )

        self.assertEqual(len(spawned), 3)
        self.assertTrue(all(ghost.kind is GhostKind.SNARL for ghost in spawned))
        self.assertEqual(boss.pending_snarl_bursts, 0)

    def test_weaver_row_clear_spawns_one_snarl_ghost(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0), (950.0, 300.0), (1100.0, 300.0)),
            (400.0, 300.0),
        )
        boss.pending_snarl_singles = 1

        spawned = self.session.spawn_weaver_snarl_burst(
            ((800.0, 300.0), (950.0, 300.0), (1100.0, 300.0)),
            (400.0, 300.0),
        )

        self.assertEqual(len(spawned), 1)
        self.assertEqual(spawned[0].kind, GhostKind.SNARL)
        self.assertEqual(boss.pending_snarl_singles, 0)

    def test_weaver_schedules_snarl_bursts_every_forty_seconds(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        boss.snarl_timer = 0.0

        boss.update(0.01, self.session.rng)

        self.assertEqual(boss.pending_snarl_bursts, 1)
        self.assertAlmostEqual(boss.snarl_timer, 39.99)

    def test_weaver_web_attack_places_two_lanes(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        boss.web_lane_timer = 0.0

        boss.update(0.01, self.session.rng)

        self.assertEqual(len(boss.active_web_lanes), 2)

    def test_weaver_pattern_seal_is_delayed_by_twenty_seconds(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration

        self.assertEqual(boss.seal_timer, 20.0)
        self.assertEqual(boss.seal_interval, 20.0)

    def test_weaver_web_slows_spell_cooldown_until_sanctified(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.pending_web_spell = SpellType.REPEL

        self.session.update_boss(0.1, ((800.0, 300.0),), (400.0, 300.0), 44)
        self.assertIn(SpellType.REPEL, self.session.spells.cooldown_drags)

        sanctify = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        self.session.spells.holy_power = sanctify.cost
        self.assertEqual(
            self.session.judge_pattern(sanctify.pattern),
            PatternResult.SPELL,
        )
        self.assertEqual(self.session.spells.cooldown_drags, {})

    def test_weaver_sanctify_clears_all_pattern_seals_after_piton(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.sealed_slots = {0, 1, 3}
        boss.active_web_lanes[0] = 5.0
        sanctify = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        self.session.spells.holy_power = sanctify.cost

        self.assertEqual(
            self.session.judge_pattern(sanctify.pattern),
            PatternResult.SPELL,
        )

        self.assertEqual(boss.sealed_slots, set())
        self.assertEqual(boss.active_web_lanes, {})
        self.assertEqual(boss.recently_purified_slots, {0, 1, 3})

    def test_weaver_does_not_reseal_recently_purified_slots(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.sealed_slots = {0, 1}
        sanctify = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        self.session.spells.holy_power = sanctify.cost
        self.session.judge_pattern(sanctify.pattern)

        boss.seal_timer = 0.0
        boss.update(0.01, self.session.rng)

        self.assertTrue(boss.sealed_slots)
        self.assertTrue(boss.sealed_slots.isdisjoint({0, 1}))

    def test_weaver_web_lane_slows_ghosts_in_that_direction(self) -> None:
        boss = self.session.start_weaver_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.active_web_lanes[0] = 5.0
        ghost = Ghost(
            GHOST_SPECS[0],
            boss.target_x + 260,
            boss.target_y,
            boss.target_x,
            boss.target_y,
        )
        ghost.spawn_elapsed = ghost.spawn_duration
        self.session.ghosts = [ghost]

        self.session.update_boss(0.1, ((800.0, 300.0),), (400.0, 300.0), 44)

        self.assertGreaterEqual(ghost.slow_remaining, 1.0)

    def test_regular_ghost_seal_blocks_pattern_and_moves_with_slot(self) -> None:
        ghost = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
            sealed_slots={1},
        )
        self.session.ghosts = [ghost]

        self.assertEqual(
            self.session.judge_pattern((0, 1, 2)),
            PatternResult.HIT,
        )
        self.assertEqual(ghost.sealed_slots, {0})
        self.assertEqual(
            self.session.judge_pattern((3, 4, 5)),
            PatternResult.MISSED,
        )

    def test_sanctify_removes_regular_ghost_pattern_seal(self) -> None:
        ghost = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2)],
            sealed_slots={0},
        )
        spell = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        self.session.ghosts = [ghost]
        self.session.spells.holy_power = spell.cost

        self.assertEqual(
            self.session.judge_pattern(spell.pattern),
            PatternResult.SPELL,
        )
        self.assertEqual(ghost.sealed_slots, set())

    def test_third_wave_uses_advanced_stage_one_rules(self) -> None:
        self.session.wave = 3
        self.session.fill_wave()
        previous_patterns = []

        while self.session.spawn_queue:
            ghost = self.session.spawn_next(((800.0, 300.0),), (400, 300))
            self.assertIsNotNone(ghost)
            patterns = [
                pattern
                for pattern in ghost.remaining_patterns
                if isinstance(pattern[0], int)
            ]
            if ghost.kind is GhostKind.CREEP:
                self.assertGreaterEqual(len(patterns), 3)
                self.assertTrue(all(len(pattern) >= 4 for pattern in patterns))
            elif ghost.kind is GhostKind.START_LOCKED:
                self.assertGreaterEqual(len(patterns), 2)
                self.assertTrue(all(len(pattern) >= 4 for pattern in patterns))
            elif ghost.kind is GhostKind.FORBIDDEN:
                self.assertIn(ghost.forbidden_patterns[0], previous_patterns)
            previous_patterns.extend(patterns)
            self.session.ghosts.clear()

    def test_third_wave_clear_does_not_create_a_fourth_wave(self) -> None:
        self.session.wave = 3

        advanced = self.session.advance_wave_if_clear()

        self.assertFalse(advanced)
        self.assertTrue(self.session.stage_cleared)
        self.assertEqual(self.session.wave, 3)
        self.assertEqual(len(self.session.spawn_queue), 0)

    def test_piton_has_three_rows_of_five_patterns(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )

        self.assertEqual(len(boss.rows), 3)
        self.assertTrue(all(len(row) == 5 for row in boss.rows))
        self.assertEqual(len(boss.patterns), 5)

    def test_repel_spell_pushes_piton_away_smoothly(self) -> None:
        boss = self.session.start_boss_battle(
            ((650.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        spell = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.REPEL
        )
        self.session.spells.holy_power = spell.cost
        before = boss.distance_to((400.0, 300.0))

        result = self.session.judge_pattern(spell.pattern)

        self.assertEqual(result, PatternResult.SPELL)
        self.assertTrue(boss.knockback_active)
        self.assertTrue(boss.is_hit_reacting)
        self.assertEqual(boss.distance_to((400.0, 300.0)), before)
        boss.update(boss.knockback_duration / 2, self.session.rng)
        self.assertGreater(boss.distance_to((400.0, 300.0)), before)
        self.assertTrue(boss.knockback_active)
        boss.update(boss.knockback_duration / 2, self.session.rng)
        self.assertFalse(boss.knockback_active)

    def test_piton_sealed_pattern_requires_one_purify_per_slot(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        boss.sealed_slots = {0, 1, 2}
        sealed_pattern = boss.patterns[0]
        sanctify = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        self.session.spells.holy_power = SpellManager.MAX_POWER

        self.assertEqual(
            self.session.judge_pattern(sealed_pattern),
            PatternResult.MISSED,
        )
        self.assertEqual(
            self.session.judge_pattern(sanctify.pattern),
            PatternResult.SPELL,
        )
        self.assertEqual(len(boss.sealed_slots), 2)

    def test_piton_refills_five_patterns_for_three_rows(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration

        for row in range(3):
            for _ in range(5):
                boss.sealed_slots.clear()
                self.session.judge_pattern(boss.patterns[0])
            if row < 2:
                self.assertEqual(boss.row_number, row + 2)
                self.assertEqual(len(boss.patterns), 5)

        self.assertTrue(boss.defeated)

    def test_defeating_piton_immediately_cancels_all_support_ghosts(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        support = Ghost(
            GHOST_SPECS[0],
            600.0,
            300.0,
            400.0,
            300.0,
        )
        hidden_support = Ghost(
            GHOST_SPECS[1],
            700.0,
            300.0,
            400.0,
            300.0,
            kind=GhostKind.CREEP,
        )
        hidden_support.hide_and_reappear_at((750.0, 300.0))
        self.session.ghosts = [support, hidden_support]
        boss.row_index = len(boss.rows) - 1
        boss.patterns = [boss.rows[-1][0]]
        boss.sealed_slots.clear()

        result = self.session.judge_pattern(boss.patterns[0])

        self.assertEqual(result, PatternResult.HIT)
        self.assertTrue(boss.defeated)
        self.assertTrue(all(ghost.vanishing for ghost in self.session.ghosts))
        self.assertTrue(
            all(not ghost.is_interactive for ghost in self.session.ghosts)
        )
        self.assertEqual(hidden_support.hidden_remaining, 0.0)
        self.assertEqual(len(self.session.spawn_queue), 0)
        self.assertEqual(len(self.session.kind_queue), 0)

    def test_piton_pattern_seals_stop_at_four_slots(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration

        for _ in range(12):
            boss.apply_random_seal(self.session.rng)

        self.assertEqual(len(boss.sealed_slots), 4)
        self.assertTrue(boss.seal_waiting_for_purify)
        boss.seal_timer = 1.0
        boss.update(5.0, self.session.rng)
        self.assertEqual(len(boss.sealed_slots), 4)
        self.assertEqual(boss.seal_timer, boss.seal_refill_delay)
        self.assertTrue(boss.purify_one())
        self.assertEqual(boss.seal_timer, boss.seal_refill_delay)
        self.assertFalse(boss.seal_waiting_for_purify)

    def test_piton_refills_after_purify_delay_only(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        for _ in range(8):
            boss.apply_random_seal(self.session.rng)
        self.assertEqual(len(boss.sealed_slots), 4)

        self.assertTrue(boss.purify_one())
        self.assertEqual(len(boss.sealed_slots), 3)
        boss.update(7.99, self.session.rng)
        self.assertEqual(len(boss.sealed_slots), 3)
        boss.update(0.02, self.session.rng)
        self.assertEqual(len(boss.sealed_slots), 4)

    def test_piton_does_not_reseal_recently_purified_slot(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        boss.sealed_slots = {0, 1, 2, 3}

        self.assertTrue(boss.purify_one())
        self.assertIn(0, boss.recently_purified_slots)
        boss.seal_timer = 0.0
        boss.update(0.01, self.session.rng)

        self.assertNotIn(0, boss.sealed_slots)
        self.assertEqual(len(boss.sealed_slots), 4)

    def test_piton_seals_one_random_spell_every_twenty_seconds(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        boss.spell_seal_timer = 0.0

        boss.update(0.01, self.session.rng)

        self.assertEqual(len(boss.sealed_spells), 1)
        self.assertAlmostEqual(
            boss.spell_seal_timer,
            boss.spell_seal_interval - 0.01,
        )

    def test_piton_does_not_seal_more_than_two_spells(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.sealed_spells = {
            SpellManager.SPELLS[0].spell_type: 5.0,
            SpellManager.SPELLS[1].spell_type: 5.0,
        }

        self.assertFalse(boss.apply_random_spell_seal(self.session.rng))
        self.assertEqual(len(boss.sealed_spells), 2)

    def test_clearing_a_piton_row_immediately_seals_one_spell(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration

        for _ in range(7):
            boss.sealed_slots.clear()
            self.session.judge_pattern(boss.patterns[0])

        self.assertEqual(boss.row_number, 2)
        self.assertEqual(len(boss.sealed_spells), 1)

    def test_piton_spell_seal_blocks_the_selected_spell_until_expired(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration
        spell = SpellManager.SPELLS[0]
        boss.sealed_spells[spell.spell_type] = 5.0
        self.session.spells.holy_power = spell.cost

        self.assertEqual(
            self.session.judge_pattern(spell.pattern),
            PatternResult.MISSED,
        )
        boss.update(5.0, self.session.rng)
        self.assertEqual(
            self.session.judge_pattern(spell.pattern),
            PatternResult.SPELL,
        )

    def test_boss_support_spawns_clear_of_piton(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )

        ghost = self.session.spawn_boss_support(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )

        self.assertIsNotNone(ghost)
        self.assertGreaterEqual(
            ghost.distance_to((boss.x, boss.y)),
            self.session.SPAWN_CLEARANCE,
        )

    def test_piton_collision_deals_two_damage_and_repositions(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0), (0.0, 300.0)),
            (400.0, 300.0),
        )
        boss.x = 400.0
        boss.y = 300.0
        boss.spawn_elapsed = boss.spawn_duration

        damage = self.session.update_boss(
            0.0,
            ((800.0, 300.0), (0.0, 300.0)),
            (400.0, 300.0),
            44,
        )

        self.assertEqual(damage, 2)
        self.assertEqual(self.session.health, 3)
        self.assertGreater(boss.hidden_remaining, 0.0)

    def test_forbidden_ghost_prefers_an_active_ghost_pattern(self) -> None:
        anchor = Ghost(
            GHOST_SPECS[0],
            100,
            100,
            400,
            300,
            remaining_patterns=[(0, 1, 2)],
        )
        self.session.wave = 2
        self.session.ghosts = [anchor]
        overlapping_trap = None

        for _ in range(200):
            self.session.spawn_queue.append(GHOST_SPECS[0])
            ghost = self.session.spawn_next(((800.0, 600.0),), (400, 300))
            if (
                ghost.kind is GhostKind.FORBIDDEN
                and anchor.pattern not in ghost.remaining_patterns
            ):
                overlapping_trap = ghost
                break
            self.session.ghosts = [anchor]

        self.assertIsNotNone(overlapping_trap)
        self.assertEqual(overlapping_trap.forbidden_patterns, [anchor.pattern])

    def test_collision_is_detected_from_above_player(self) -> None:
        ghost = Ghost(GHOST_SPECS[0], 400, 250, 400, 300)
        self.session.ghosts = [ghost]

        escaped = self.session.update_ghosts(0.0, (400, 300), 20)

        self.assertEqual(escaped, 1)
        self.assertEqual(self.session.health, 4)

    def test_nearest_ghost_to_center_is_targeted(self) -> None:
        far_ghost = Ghost(GHOST_SPECS[0], 100, 100, 400, 300)
        near_ghost = Ghost(GHOST_SPECS[1], 450, 300, 400, 300)
        self.session.ghosts = [far_ghost, near_ghost]

        self.assertIs(self.session.target_ghost(), near_ghost)

    def test_vanishing_ghost_stays_still_then_is_removed(self) -> None:
        self.normal.remove_first_pattern()
        self.session.ghosts = [self.normal]
        position = (self.normal.x, self.normal.y)

        self.session.update_ghosts(0.4, (400, 300), 20)

        self.assertEqual((self.normal.x, self.normal.y), position)
        self.assertIn(self.normal, self.session.ghosts)
        self.assertLess(self.normal.alpha, 255)

        self.session.update_ghosts(0.5, (400, 300), 20)

        self.assertNotIn(self.normal, self.session.ghosts)

    def test_pattern_removal_creates_a_smooth_transition(self) -> None:
        ghost = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
        )

        ghost.remove_first_pattern()

        self.assertEqual(ghost.removed_pattern, (0, 1, 2))
        self.assertEqual(ghost.remaining_patterns, [(3, 4, 5)])
        self.assertEqual(ghost.pattern_transition_progress, 0.0)
        ghost.update(ghost.pattern_transition_duration)
        self.assertEqual(ghost.removed_pattern, ())

    def test_pattern_removal_starts_hit_reaction(self) -> None:
        ghost = Ghost(
            GHOST_SPECS[0],
            700,
            200,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
        )

        self.assertFalse(ghost.is_hit_reacting)
        ghost.remove_first_pattern()

        self.assertTrue(ghost.is_hit_reacting)
        self.assertEqual(ghost.hit_reaction_progress, 0.0)
        ghost.update(ghost.hit_reaction_duration)
        self.assertFalse(ghost.is_hit_reacting)

    def test_spawn_fades_in(self) -> None:
        ghost = Ghost(GHOST_SPECS[0], 700, 200, 400, 300)

        self.assertEqual(ghost.alpha, 0)
        ghost.update(ghost.spawn_duration / 2)
        self.assertGreater(ghost.alpha, 0)
        self.assertLess(ghost.alpha, 255)
        ghost.update(ghost.spawn_duration / 2)
        self.assertEqual(ghost.alpha, 255)

    def test_repel_spell_pushes_existing_ghosts_away(self) -> None:
        spell = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.REPEL
        )
        self.session.ghosts = [self.normal]
        self.session.spells.holy_power = spell.cost
        before = self.normal.distance_to((400, 300))

        result = self.session.judge_pattern(spell.pattern)

        self.assertEqual(result, PatternResult.SPELL)
        self.assertTrue(self.normal.knockback_active)
        self.assertEqual(
            self.normal.slow_remaining,
            SpellManager.REPEL_SLOW_DURATION,
        )
        self.assertEqual(self.normal.distance_to((400, 300)), before)
        self.normal.update(self.normal.knockback_duration)
        self.assertGreater(self.normal.distance_to((400, 300)), before)

    def test_spell_cooldown_blocks_repeat_cast_until_updated(self) -> None:
        spell = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.REPEL
        )
        self.session.ghosts = [self.normal]
        self.session.spells.holy_power = spell.cost * 2

        self.assertEqual(self.session.judge_pattern(spell.pattern), PatternResult.SPELL)
        self.assertEqual(self.session.judge_pattern(spell.pattern), PatternResult.MISSED)
        self.session.update_ghosts(spell.cooldown, (400, 300), 20)

        self.assertEqual(self.session.judge_pattern(spell.pattern), PatternResult.SPELL)

    def test_repel_moves_smoothly_before_reaching_destination(self) -> None:
        before = (self.normal.x, self.normal.y)
        self.normal.repel(SpellManager.REPEL_DISTANCE)

        self.normal.update(self.normal.knockback_duration / 2)

        self.assertNotEqual((self.normal.x, self.normal.y), before)
        self.assertTrue(self.normal.knockback_active)
        self.assertNotEqual(
            (self.normal.x, self.normal.y),
            (self.normal.knockback_end_x, self.normal.knockback_end_y),
        )

    def test_nullify_removes_all_active_gimmicks(self) -> None:
        spell = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.NULLIFY
        )
        forbidden = Ghost(
            GHOST_SPECS[0],
            450,
            300,
            400,
            300,
            kind=GhostKind.FORBIDDEN,
            forbidden_patterns=[(0, 1, 2)],
        )
        wavy = Ghost(
            GHOST_SPECS[0],
            900,
            300,
            400,
            300,
            kind=GhostKind.WAVY,
        )
        locked = Ghost(
            GHOST_SPECS[0],
            300,
            300,
            400,
            300,
            kind=GhostKind.START_LOCKED,
        )
        self.session.ghosts = [forbidden, wavy, locked]
        self.session.spells.holy_power = spell.cost

        self.session.judge_pattern(spell.pattern)

        self.assertEqual(forbidden.kind, GhostKind.SLOWPOKE)
        self.assertEqual(forbidden.forbidden_patterns, [])
        self.assertEqual(wavy.kind, GhostKind.SLOWPOKE)
        self.assertEqual(locked.kind, GhostKind.SLOWPOKE)

    def test_spawn_protected_forbidden_ghost_does_not_resonate(self) -> None:
        ghost = Ghost(
            GHOST_SPECS[0],
            800,
            300,
            400,
            300,
            remaining_patterns=[(3, 4, 5)],
            kind=GhostKind.FORBIDDEN,
            forbidden_patterns=[(0, 1, 2)],
            spawn_protected=True,
        )
        self.session.ghosts = [ghost]

        result = self.session.judge_pattern((0, 1, 2))

        self.assertEqual(result, PatternResult.MISSED)
        self.assertEqual(ghost.resonance_remaining, 0.0)

    def test_spawned_ghost_moves_while_fading_in(self) -> None:
        self.session.spawn_queue.append(GHOST_SPECS[0])
        ghost = self.session.spawn_next(((800.0, 300.0),), (400, 300))
        self.assertIsNotNone(ghost)
        before = ghost.distance_to((400, 300))

        ghost.update(ghost.spawn_duration / 2)

        self.assertGreater(ghost.alpha, 0)
        self.assertLess(ghost.distance_to((400, 300)), before)

    def test_layered_patterns_match_by_combined_layers(self) -> None:
        expected = ((0, 1, 2), (6, 7, 8))

        self.assertTrue(pattern_attempt_matches(((6, 7, 8), (0, 1, 2)), expected))
        self.assertFalse(pattern_attempt_matches((0, 1, 2, 6, 7, 8), expected))

    def test_mirrored_pattern_transforms_grid_axes(self) -> None:
        self.assertEqual(mirrored_pattern((0, 1, 2), "x"), (6, 7, 8))
        self.assertEqual(mirrored_pattern((0, 3, 6), "y"), (2, 5, 8))
        self.assertEqual(mirrored_pattern((0, 1, 4), "origin"), (8, 7, 4))

    def test_hidden_creep_ignores_patterns_until_reappearing(self) -> None:
        creep = Ghost(
            GHOST_SPECS[0],
            700,
            300,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
            kind=GhostKind.CREEP,
        )
        self.session.ghosts = [creep]

        self.session.judge_pattern((0, 1, 2))
        hidden_position = (creep.x, creep.y)
        result = self.session.judge_pattern((3, 4, 5))

        self.assertEqual(result, PatternResult.MISSED)
        self.assertGreaterEqual(creep.hidden_remaining, creep.hidden_duration_min)
        self.assertGreaterEqual(creep.hidden_remaining, 5.0)
        self.assertLessEqual(creep.hidden_remaining, creep.hidden_duration_max)
        self.assertEqual(creep.remaining_patterns, [(3, 4, 5)])
        self.assertEqual((creep.x, creep.y), hidden_position)
        creep.update(creep.hidden_duration)
        self.assertGreater(creep.resonance_remaining, 0.0)
        result = self.session.judge_pattern((3, 4, 5))
        self.assertEqual(result, PatternResult.MISSED)
        creep.update(creep.reappear_duration)
        result = self.session.judge_pattern((3, 4, 5))
        self.assertEqual(result, PatternResult.HIT)

    def test_creep_reappears_in_clear_position(self) -> None:
        creep = Ghost(
            GHOST_SPECS[0],
            700,
            300,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
            kind=GhostKind.CREEP,
        )
        blocker = Ghost(GHOST_SPECS[0], 605, 300, 400, 300)
        self.session.ghosts = [creep, blocker]

        self.session.judge_pattern((0, 1, 2))
        creep.update(creep.hidden_duration)

        self.assertGreaterEqual(
            creep.distance_to((blocker.x, blocker.y)),
            self.session.SPAWN_CLEARANCE,
        )

    def test_crease_requires_the_mirrored_pattern(self) -> None:
        source = (0, 1, 4)
        mirrored = mirrored_pattern(source, "y")
        crease = Ghost(
            GHOST_SPECS[0],
            700,
            300,
            400,
            300,
            remaining_patterns=[mirrored],
            kind=GhostKind.CREASE,
            crease_axis="y",
            crease_source_pattern=source,
        )
        self.session.ghosts = [crease]

        self.assertEqual(self.session.judge_pattern(source), PatternResult.MISSED)
        self.assertEqual(self.session.judge_pattern(mirrored), PatternResult.HIT)

    def test_crease_axes_stay_attached_to_their_original_patterns(self) -> None:
        first_source = (0, 1, 4)
        second_source = (3, 4, 5)
        first = mirrored_pattern(first_source, "y")
        second = mirrored_pattern(second_source, "x")
        crease = Ghost(
            GHOST_SPECS[0],
            700,
            300,
            400,
            300,
            remaining_patterns=[first, second],
            kind=GhostKind.CREASE,
            crease_axis="y",
            crease_source_pattern=first_source,
            crease_target_pattern=first,
            crease_axes=["y", "x"],
        )
        self.session.ghosts = [crease]

        self.assertEqual(self.session.judge_pattern(first), PatternResult.HIT)

        self.assertEqual(crease.remaining_patterns, [second])
        self.assertEqual(crease.crease_axes, ["x"])
        self.assertEqual(self.session.judge_pattern(second), PatternResult.HIT)

    def test_creep_spawns_with_at_least_two_patterns(self) -> None:
        found = None
        self.session.stage = 2
        self.session.wave = 2
        for _ in range(300):
            self.session.spawn_queue.append(GHOST_SPECS[0])
            ghost = self.session.spawn_next(((800.0, 300.0),), (400, 300))
            if ghost.kind is GhostKind.CREEP:
                found = ghost
                break
            self.session.ghosts.clear()

        self.assertIsNotNone(found)
        self.assertGreaterEqual(len(found.remaining_patterns), 2)

    def test_truth_spell_reveals_creeps_and_clears_forbidden_gimmick(self) -> None:
        spell = next(
            spell
            for spell in SpellManager.SPELLS
            if spell.spell_type is SpellType.TRUTH
        )
        creep = Ghost(
            GHOST_SPECS[0],
            700,
            300,
            400,
            300,
            remaining_patterns=[(0, 1, 2), (3, 4, 5)],
            kind=GhostKind.CREEP,
        )
        forbidden = Ghost(
            GHOST_SPECS[0],
            500,
            300,
            400,
            300,
            kind=GhostKind.FORBIDDEN,
            forbidden_patterns=[(0, 1, 2)],
        )
        creep.hide_and_reappear_at((650, 300))
        self.session.ghosts = [creep, forbidden]
        self.session.spells.holy_power = spell.cost

        self.session.judge_pattern(spell.pattern)

        self.assertEqual(creep.hidden_remaining, 0.0)
        self.assertGreater(creep.reappear_remaining, 0.0)
        self.assertEqual(creep.resonance_remaining, 0.0)
        self.assertEqual(forbidden.kind, GhostKind.SLOWPOKE)
        self.assertEqual(forbidden.forbidden_patterns, [])


if __name__ == "__main__":
    unittest.main()
