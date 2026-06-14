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
    mirrored_pattern,
    pattern_attempt_matches,
)


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

    def test_start_locked_can_apply_to_multiple_patterns_without_changing_them(self) -> None:
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
        result = self.session.judge_pattern((5, 4, 3))
        self.assertEqual(result, PatternResult.MISSED)
        result = self.session.judge_pattern((3, 4, 5))
        self.assertEqual(result, PatternResult.HIT)

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
                    GhostKind.CREEP,
                    GhostKind.FORBIDDEN,
                }
            )

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

    def test_piton_has_three_rows_of_seven_patterns(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )

        self.assertEqual(len(boss.rows), 3)
        self.assertTrue(all(len(row) == 7 for row in boss.rows))
        self.assertEqual(len(boss.patterns), 7)

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

    def test_piton_refills_seven_patterns_for_three_rows(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration

        for row in range(3):
            for _ in range(7):
                boss.sealed_slots.clear()
                self.session.judge_pattern(boss.patterns[0])
            if row < 2:
                self.assertEqual(boss.row_number, row + 2)
                self.assertEqual(len(boss.patterns), 7)

        self.assertTrue(boss.defeated)

    def test_piton_pattern_seals_stop_at_four_slots(self) -> None:
        boss = self.session.start_boss_battle(
            ((800.0, 300.0),),
            (400.0, 300.0),
        )
        boss.spawn_elapsed = boss.spawn_duration

        for _ in range(12):
            boss.apply_random_seal(self.session.rng)

        self.assertEqual(len(boss.sealed_slots), 4)
        boss.seal_timer = 1.0
        boss.update(5.0, self.session.rng)
        self.assertEqual(len(boss.sealed_slots), 4)
        self.assertEqual(boss.seal_timer, boss.seal_interval)
        self.assertTrue(boss.purify_one())
        self.assertEqual(boss.seal_timer, boss.seal_interval)

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
