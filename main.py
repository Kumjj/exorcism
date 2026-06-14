from __future__ import annotations

import math
from pathlib import Path
import random

try:
    import pygame
except ModuleNotFoundError:
    print("pygame is required. Install it with: python -m pip install pygame")
    raise SystemExit(1)

from core import (
    GameSession,
    Ghost,
    GhostKind,
    PatternInput,
    PatternResult,
    SpellDefinition,
    SpellManager,
    SpellType,
    mirrored_pattern,
)


WIDTH, HEIGHT = 1200, 720
FPS = 60
PLAYER_POSITION = (WIDTH // 2, HEIGHT // 2 + 25)
PLAYER_RADIUS = 44
GRID_CENTER = PLAYER_POSITION
GRID_GAP = 98
NODE_RADIUS = 23
SPAWN_POSITIONS = (
    (600.0, 145.0),
    (960.0, 205.0),
    (1110.0, 385.0),
    (960.0, 625.0),
    (600.0, 645.0),
    (240.0, 625.0),
    (90.0, 385.0),
    (240.0, 205.0),
)

BG = (12, 12, 28)
PANEL = (27, 25, 52)
PANEL_LIGHT = (43, 39, 76)
WHITE = (238, 235, 255)
MUTED = (158, 153, 190)
GOLD = (255, 210, 100)
CYAN = (103, 232, 255)
PINK = (255, 105, 180)
RED = (255, 91, 112)
GREEN = (99, 230, 164)
PATTERN_COLOR = (222, 231, 240)


class Button:
    def __init__(self, rect: pygame.Rect, text: str) -> None:
        self.rect = rect
        self.text = text

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        color = (92, 73, 145) if hovered else (65, 53, 106)
        pygame.draw.rect(surface, color, self.rect, border_radius=12)
        pygame.draw.rect(surface, (158, 132, 224), self.rect, 2, border_radius=12)
        label = font.render(self.text, True, WHITE)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def clicked(self, event: pygame.event.Event) -> bool:
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class ExorcismGame:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Exocism")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.Font(None, 24)
        self.font = pygame.font.Font(None, 32)
        self.font_large = pygame.font.Font(None, 54)
        self.font_title = pygame.font.Font(None, 92)
        self.state = "start"
        self.running = True
        self.session = GameSession(rng=random.Random())
        self.pattern_input = PatternInput()
        self.last_drag_position: tuple[int, int] | None = None
        self.spawn_timer = 0.0
        self.message_timer = 0.0
        self.flash_color: tuple[int, int, int] | None = None
        self.flash_timer = 0.0
        self.success_pattern: tuple[int, ...] = ()
        self.success_timer = 0.0
        self.success_duration = 0.48
        self.spell_pattern: tuple[int, ...] = ()
        self.spell_timer = 0.0
        self.spell_duration = 1.15
        self.spell_tab_rect = pygame.Rect(WIDTH - 42, 245, 42, 145)
        self.spell_panel_size = (300, 468)
        self.spell_panel_open_x = WIDTH - self.spell_tab_rect.width - 300
        self.spell_panel_closed_x = WIDTH
        self.spell_panel_y = 126
        self.spell_panel_progress = 0.0
        self.spell_panel_duration = 0.22
        self.spell_panel_close_delay = 0.12
        self.spell_panel_hover_grace = 0.0
        self.reward_orbs: list[dict[str, object]] = []
        self.player_images = self._load_player_images()
        self.ghost_images = self._load_ghost_images()
        self.pending_shift_pattern: tuple[int, ...] = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.start_button = Button(pygame.Rect(490, 465, 220, 64), "START")
        self.retry_button = Button(pygame.Rect(490, 480, 220, 64), "RETRY")
        self.resume_button = Button(pygame.Rect(490, 330, 220, 64), "RESUME")
        self.pause_restart_button = Button(pygame.Rect(490, 410, 220, 64), "RESTART")
        self.node_positions = self._make_grid_positions()

    def _load_player_images(self) -> list[pygame.Surface]:
        frames = [
            image
            for index in range(1, 4)
            if (image := self._load_scaled_image(f"peter_idle{index}.png", 145))
            is not None
        ]
        fallback = self._load_scaled_image("exorcism_MC.png", 145)
        return frames or ([fallback] if fallback is not None else [])

    def _load_scaled_image(self, filename: str, width: int) -> pygame.Surface | None:
        image_path = Path(__file__).with_name(filename)
        if not image_path.exists():
            return None
        image = pygame.image.load(image_path).convert_alpha()
        height = round(image.get_height() * width / image.get_width())
        return pygame.transform.smoothscale(image, (width, height))

    def _load_ghost_images(self) -> dict[object, dict[str, pygame.Surface]]:
        images: dict[object, dict[str, pygame.Surface]] = {}
        for variant in (1, 2):
            variant_images: dict[str, pygame.Surface] = {}
            for state in ("idle", "attacked", "defeated"):
                image = self._load_scaled_image(f"slow{variant}_{state}.png", 96)
                if image is not None:
                    variant_images[state] = image
            if variant_images:
                images[variant] = variant_images
        for name in ("creep", "crease", "snarl"):
            variant_images = {}
            for state in ("idle", "attacked", "defeated"):
                image = self._load_scaled_image(f"{name}_{state}.png", 96)
                if image is not None:
                    variant_images[state] = image
            if variant_images:
                images[name] = variant_images
        return images

    def _make_grid_positions(self) -> list[tuple[int, int]]:
        positions = []
        for row in range(3):
            for col in range(3):
                positions.append(
                    (
                        GRID_CENTER[0] + (col - 1) * GRID_GAP,
                        GRID_CENTER[1] + (row - 1) * GRID_GAP,
                    )
                )
        return positions

    def run(self) -> None:
        while self.running:
            seconds = self.clock.tick(FPS) / 1000.0
            self._handle_events()
            self._update(seconds)
            self._draw()
            pygame.display.flip()
        pygame.quit()

    def _start_game(self) -> None:
        self.session.reset()
        self.pattern_input.clear()
        self.last_drag_position = None
        self.success_pattern = ()
        self.success_timer = 0.0
        self.pending_shift_pattern = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.spell_pattern = ()
        self.spell_timer = 0.0
        self.spell_panel_progress = 0.0
        self.spell_panel_hover_grace = 0.0
        self.reward_orbs.clear()
        self.spawn_timer = 0.5
        self.message_timer = 0.0
        self.state = "playing"

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.state == "playing":
                    self._pause_game()
                elif self.state == "paused":
                    self._resume_game()
                else:
                    self.running = False

            if self.state == "start":
                if self.start_button.clicked(event):
                    self._start_game()
                elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                ):
                    self._start_game()
            elif self.state == "gameover":
                if self.retry_button.clicked(event):
                    self._start_game()
                elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                ):
                    self._start_game()
            elif self.state == "playing":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                    self._pause_game()
                    continue
                self._handle_pattern_event(event)
            elif self.state == "paused":
                if self.resume_button.clicked(event):
                    self._resume_game()
                elif self.pause_restart_button.clicked(event):
                    self._start_game()
                elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_p,
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                ):
                    self._resume_game()

    def _pause_game(self) -> None:
        self.pattern_input.clear()
        self.last_drag_position = None
        self.pending_shift_pattern = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.state = "paused"

    def _resume_game(self) -> None:
        self.pattern_input.clear()
        self.last_drag_position = None
        self.pending_shift_pattern = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.state = "playing"

    def _handle_pattern_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            node = self._node_at(event.pos)
            if node is not None:
                self.pattern_input.begin(node)
                self.last_drag_position = event.pos
                modifiers = pygame.key.get_mods()
                self.input_shift_layer = bool(
                    modifiers & (pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT)
                )
                self.input_shift_cancelled = False
        elif (
            event.type == pygame.KEYUP
            and event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT)
            and self.pattern_input.dragging
            and self.input_shift_layer
        ):
            self.input_shift_cancelled = True
        elif event.type == pygame.MOUSEMOTION and self.pattern_input.dragging:
            self._add_nodes_along_segment(
                self.last_drag_position or event.pos, event.pos
            )
            self.last_drag_position = event.pos
        elif (
            event.type == pygame.MOUSEBUTTONUP
            and event.button == 1
            and self.pattern_input.dragging
        ):
            self._add_nodes_along_segment(
                self.last_drag_position or event.pos, event.pos
            )
            pattern = self.pattern_input.finish()
            self.last_drag_position = None
            if self.input_shift_layer and not self.input_shift_cancelled:
                self.pending_shift_pattern = pattern
            elif self.pending_shift_pattern:
                self._submit_pattern((self.pending_shift_pattern, pattern))
                self.pending_shift_pattern = ()
            else:
                self._submit_pattern(pattern)
            self.input_shift_layer = False
            self.input_shift_cancelled = False

    def _submit_pattern(
        self, pattern: tuple[int, ...] | tuple[tuple[int, ...], tuple[int, ...]]
    ) -> PatternResult:
        result = self.session.judge_pattern(pattern)
        if self.session.last_match_count or self.session.last_spell_cast:
            self.success_pattern = pattern if pattern and isinstance(pattern[0], int) else ()
            self.success_timer = self.success_duration
        if self.session.last_spell_cast:
            self.spell_pattern = pattern
            self.spell_timer = self.spell_duration
        for x, y, amount in self.session.defeated_events:
            self.reward_orbs.append(
                {
                    "start": (x, y),
                    "elapsed": 0.0,
                    "duration": 0.95,
                    "amount": amount,
                }
            )
        self.message_timer = 0.0
        self._set_result_flash(result)
        return result

    def _node_at(self, position: tuple[int, int]) -> int | None:
        for index, node_position in enumerate(self.node_positions):
            if math.dist(position, node_position) <= NODE_RADIUS + 20:
                return index
        return None

    def _add_nodes_along_segment(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = dx * dx + dy * dy
        crossed: list[tuple[float, int]] = []
        for index, node_position in enumerate(self.node_positions):
            if index in self.pattern_input.nodes:
                continue
            if length_squared == 0:
                progress = 0.0
            else:
                progress = (
                    (node_position[0] - start[0]) * dx
                    + (node_position[1] - start[1]) * dy
                ) / length_squared
                progress = max(0.0, min(1.0, progress))
            closest = (start[0] + dx * progress, start[1] + dy * progress)
            if math.dist(node_position, closest) <= NODE_RADIUS + 20:
                crossed.append((progress, index))
        for _, index in sorted(crossed):
            self.pattern_input.add(index)

    def _set_result_flash(self, result: PatternResult) -> None:
        colors = {
            PatternResult.HIT: GREEN,
            PatternResult.SPELL: GOLD,
            PatternResult.RESONATED: PINK,
        }
        self.flash_color = colors.get(result)
        self.flash_timer = 0.22 if self.flash_color else 0.0

    def _update(self, seconds: float) -> None:
        if self.state != "playing":
            return

        self.spawn_timer -= seconds
        active_limit = min(2 + self.session.wave // 2, 5)
        if (
            self.spawn_timer <= 0
            and self.session.spawn_queue
            and len(self.session.ghosts) < active_limit
        ):
            spawned = self.session.spawn_next(SPAWN_POSITIONS, PLAYER_POSITION)
            self.spawn_timer = (
                max(0.75, 2.15 - self.session.wave * 0.1)
                if spawned
                else 0.25
            )

        escaped = self.session.update_ghosts(
            seconds, PLAYER_POSITION, PLAYER_RADIUS
        )
        if escaped:
            self.message_timer = 1.8
            self.flash_color = RED
            self.flash_timer = 0.22
        if self.session.health <= 0:
            self.state = "gameover"
            self.pattern_input.clear()
            return

        if self.session.advance_wave_if_clear():
            self.spawn_timer = 1.1
            self.message_timer = 1.8

        self.message_timer = max(0.0, self.message_timer - seconds)
        self.flash_timer = max(0.0, self.flash_timer - seconds)
        self.success_timer = max(0.0, self.success_timer - seconds)
        self.spell_timer = max(0.0, self.spell_timer - seconds)
        self._update_spell_panel(seconds)
        for orb in list(self.reward_orbs):
            orb["elapsed"] = float(orb["elapsed"]) + seconds
            if float(orb["elapsed"]) >= float(orb["duration"]):
                self.reward_orbs.remove(orb)

    def _spell_panel_rect(self) -> pygame.Rect:
        eased = 1.0 - (1.0 - self.spell_panel_progress) ** 3
        x = self.spell_panel_closed_x + (
            self.spell_panel_open_x - self.spell_panel_closed_x
        ) * eased
        return pygame.Rect(
            round(x),
            self.spell_panel_y,
            self.spell_panel_size[0],
            self.spell_panel_size[1],
        )

    def _update_spell_panel(self, seconds: float) -> None:
        mouse_position = pygame.mouse.get_pos()
        open_panel_rect = pygame.Rect(
            self.spell_panel_open_x,
            self.spell_panel_y,
            self.spell_panel_size[0],
            self.spell_panel_size[1],
        )
        hover_bridge = open_panel_rect.union(self.spell_tab_rect).inflate(12, 12)
        hovered = hover_bridge.collidepoint(mouse_position)
        if hovered:
            self.spell_panel_hover_grace = self.spell_panel_close_delay
        else:
            self.spell_panel_hover_grace = max(
                0.0, self.spell_panel_hover_grace - seconds
            )
        direction = (
            1.0 if hovered or self.spell_panel_hover_grace > 0 else -1.0
        )
        self.spell_panel_progress = max(
            0.0,
            min(
                1.0,
                self.spell_panel_progress
                + direction * seconds / self.spell_panel_duration,
            ),
        )

    def _draw(self) -> None:
        self.screen.fill(BG)
        self._draw_background()
        if self.state == "start":
            self._draw_start()
        elif self.state == "playing":
            self._draw_playing()
        elif self.state == "paused":
            self._draw_paused()
        else:
            self._draw_gameover()

    def _draw_background(self) -> None:
        for i in range(70):
            x = (i * 173 + 47) % WIDTH
            y = (i * 97 + 31) % HEIGHT
            brightness = 55 + (i % 4) * 18
            pygame.draw.circle(
                self.screen, (brightness, brightness, brightness + 25), (x, y), 1
            )
        pygame.draw.circle(self.screen, (30, 27, 58), (95, 100), 160)
        pygame.draw.circle(self.screen, (20, 19, 42), (95, 100), 125)

    def _draw_start(self) -> None:
        title = self.font_title.render("EXOCISM", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 170)))
        subtitle = self.font.render(
            "Connect the magic circle. Judge the pattern. Exorcise the dead.",
            True,
            MUTED,
        )
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, 245)))
        self._draw_demo_pattern((0, 1, 4, 7, 8), (WIDTH // 2, 350), 48, CYAN)
        self.start_button.draw(self.screen, self.font)
        help_text = self.font_small.render(
            "Hold the left mouse button and pass through the nine nodes.",
            True,
            MUTED,
        )
        self.screen.blit(help_text, help_text.get_rect(center=(WIDTH // 2, 570)))

    def _draw_playing(self) -> None:
        self._draw_world()
        self._draw_reward_orbs()
        self._draw_hud()
        self._draw_spell_bookmark()
        if self.spell_timer > 0 and self.spell_pattern:
            self._draw_spell_cast_animation()
        if self.flash_timer > 0 and self.flash_color:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((*self.flash_color, int(75 * self.flash_timer / 0.22)))
            self.screen.blit(overlay, (0, 0))

    def _draw_paused(self) -> None:
        self._draw_world()
        self._draw_reward_orbs()
        self._draw_hud()
        self._draw_spell_bookmark()
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 7, 17, 185))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Surface((420, 300), pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL, 230), panel.get_rect(), border_radius=14)
        pygame.draw.rect(panel, (*CYAN, 120), panel.get_rect(), 2, border_radius=14)
        panel_rect = panel.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        self.screen.blit(panel, panel_rect)

        title = self.font_large.render("PAUSED", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 255)))
        hint = self.font_small.render("Press P or Esc to resume.", True, MUTED)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 525)))
        self.resume_button.draw(self.screen, self.font)
        self.pause_restart_button.draw(self.screen, self.font)

    def _draw_world(self) -> None:
        aura = pygame.Surface((164, 164), pygame.SRCALPHA)
        pygame.draw.circle(aura, (*CYAN, 22), (82, 82), 75)
        pygame.draw.circle(aura, (*GOLD, 65), (82, 82), PLAYER_RADIUS + 9, 2)
        self.screen.blit(aura, aura.get_rect(center=PLAYER_POSITION))
        if self.player_images:
            frame = self._player_idle_frame()
            rect = frame.get_rect(center=PLAYER_POSITION)
            self.screen.blit(frame, rect)
        else:
            pygame.draw.circle(
                self.screen, (83, 67, 123), PLAYER_POSITION, PLAYER_RADIUS
            )

        for ghost in sorted(
            self.session.ghosts,
            key=lambda item: item.distance_to(PLAYER_POSITION),
            reverse=True,
        ):
            self._draw_ghost(ghost)

        self._draw_large_grid()

    def _player_idle_frame(self) -> pygame.Surface:
        hold_ms = 1800
        frame_ms = 260
        cycle_ms = hold_ms + frame_ms * len(self.player_images)
        elapsed = pygame.time.get_ticks() % cycle_ms
        if elapsed < hold_ms:
            return self.player_images[0]
        index = min(
            len(self.player_images) - 1,
            (elapsed - hold_ms) // frame_ms,
        )
        return self.player_images[index]

    def _draw_ghost(self, ghost: Ghost) -> None:
        x, y = int(ghost.x), int(ghost.y)
        bob = (
            0
            if ghost.vanishing
            else round(math.sin(ghost.pulse * 1.35 + ghost.y * 0.01) * 2)
        )
        y += bob
        alpha = ghost.alpha
        if ghost.kind is GhostKind.BLINKING and not ghost.vanishing:
            visibility = (math.sin(ghost.pulse * 2.2) + 1.0) / 2.0
            alpha = round(45 + visibility * 210)
        if alpha <= 0:
            return
        image = self._ghost_image_for_state(ghost)
        if image:
            image = self._prepare_ghost_image(image, ghost)
            draw_x, draw_y = self._ghost_draw_center(ghost, x, y)
            image.set_alpha(alpha)
            self.screen.blit(image, image.get_rect(center=(draw_x, draw_y)))
        else:
            fallback = pygame.Surface((100, 90), pygame.SRCALPHA)
            pygame.draw.circle(fallback, (*PATTERN_COLOR, alpha), (50, 45), 38)
            self.screen.blit(fallback, fallback.get_rect(center=(x, y)))

        if not ghost.vanishing or ghost.removed_pattern or ghost.removed_forbidden_pattern:
            self._draw_ghost_patterns(ghost, (x, y - 62), alpha)

    def _ghost_image_for_state(self, ghost: Ghost) -> pygame.Surface | None:
        state = "idle"
        if ghost.vanishing:
            state = "defeated"
        elif ghost.is_hit_reacting:
            state = "attacked"
        image_key: object = ghost.art_variant
        if ghost.kind is GhostKind.CREEP:
            image_key = "creep"
        elif ghost.kind is GhostKind.CREASE:
            image_key = "crease"
        elif ghost.kind is GhostKind.SNARL:
            image_key = "snarl"
        variant_images = self.ghost_images.get(image_key)
        if not variant_images:
            variant_images = self.ghost_images.get(1) or self.ghost_images.get(2)
        if not variant_images:
            return None
        return (
            variant_images.get(state)
            or variant_images.get("idle")
            or next(iter(variant_images.values()))
        )

    def _prepare_ghost_image(
        self, image: pygame.Surface, ghost: Ghost
    ) -> pygame.Surface:
        prepared = image.copy()
        if not ghost.facing_right:
            prepared = pygame.transform.flip(prepared, True, False)
        if ghost.vanishing:
            progress = 1.0 - ghost.fade_remaining / ghost.fade_duration
            stretch = 1.0 + 0.38 * progress
            prepared = pygame.transform.smoothscale(
                prepared,
                (
                    prepared.get_width(),
                    max(1, round(prepared.get_height() * stretch)),
                ),
            )
        elif ghost.is_hit_reacting:
            impulse = self._ghost_hit_reaction_amount(ghost)
            angle = 8.0 * impulse * (1 if ghost.facing_right else -1)
            prepared = pygame.transform.rotate(prepared, angle)
        return prepared

    def _ghost_draw_center(
        self, ghost: Ghost, x: int, y: int
    ) -> tuple[float, float]:
        if not ghost.is_hit_reacting:
            return x, y
        dx = ghost.x - ghost.target_x
        dy = ghost.y - ghost.target_y
        length = math.hypot(dx, dy) or 1.0
        impulse = self._ghost_hit_reaction_amount(ghost)
        offset = ghost.hit_reaction_distance * impulse
        return (
            x + dx / length * offset,
            y + dy / length * offset,
        )

    def _ghost_hit_reaction_amount(self, ghost: Ghost) -> float:
        progress = ghost.hit_reaction_progress
        push_end = 0.22
        settle_start = 0.78
        if progress < push_end:
            return self._smootherstep(progress / push_end)
        if progress < settle_start:
            return 1.0 - 0.82 * self._smootherstep(
                (progress - push_end) / (settle_start - push_end)
            )
        return 0.18 * (
            1.0 - self._smootherstep((progress - settle_start) / (1.0 - settle_start))
        )

    def _smootherstep(self, value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)

    def _draw_ghost_patterns(
        self, ghost: Ghost, center: tuple[int, int], opacity: int
    ) -> None:
        transition = ghost.pattern_transition_progress
        easing = 1.0 - (1.0 - transition) ** 3
        forbidden_count = (
            1
            if (
                ghost.kind is GhostKind.FORBIDDEN
                and (ghost.forbidden_patterns or ghost.removed_forbidden_pattern)
            )
            else 0
        )
        old_count = max(
            ghost.pattern_transition_from_count,
            len(ghost.remaining_patterns),
        )
        visible_count = max(old_count, len(ghost.remaining_patterns)) + forbidden_count
        total_width = max(1, visible_count) * 54
        start_x = max(
            28,
            min(WIDTH - total_width - 28, center[0] - total_width // 2),
        )
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        card_rect = pygame.Rect(start_x - 6, center[1] - 25, total_width + 12, 50)
        pygame.draw.rect(layer, (13, 15, 28, 150), card_rect, border_radius=8)

        def layout_start(count: int) -> float:
            width = max(1, count + forbidden_count) * 54
            return max(28, min(WIDTH - width - 28, center[0] - width / 2))

        def visual_slot(index: int) -> int:
            return index + (1 if forbidden_count and index >= 1 else 0)

        entries: list[
            tuple[tuple[int, ...], tuple[int, int, int], tuple[float, float], float, bool]
        ] = []
        if ghost.removed_pattern:
            old_start = layout_start(old_count)
            entries.append(
                (
                    ghost.removed_pattern,
                    PATTERN_COLOR,
                    (old_start + visual_slot(0) * 54 + 27, center[1]),
                    1.0 - transition,
                    False,
                )
            )
            new_start = layout_start(len(ghost.remaining_patterns))
            for index, pattern in enumerate(ghost.remaining_patterns):
                old_x = old_start + visual_slot(index + 1) * 54 + 27
                new_x = new_start + visual_slot(index) * 54 + 27
                entries.append(
                    (
                        pattern,
                        PATTERN_COLOR,
                        (old_x + (new_x - old_x) * easing, center[1]),
                        1.0,
                        index == 0,
                    )
                )
        else:
            stable_start = layout_start(len(ghost.remaining_patterns))
            for index, pattern in enumerate(ghost.remaining_patterns):
                entries.append(
                    (
                        pattern,
                        PATTERN_COLOR,
                        (
                            stable_start + visual_slot(index) * 54 + 27,
                            center[1],
                        ),
                        1.0,
                        index == 0,
                    )
                )

        if ghost.removed_forbidden_pattern:
            insert_index = min(1, len(ghost.remaining_patterns))
            forbidden_x = layout_start(len(ghost.remaining_patterns)) + insert_index * 54 + 27
            entries.append(
                (
                    ghost.removed_forbidden_pattern,
                    RED,
                    (forbidden_x, center[1]),
                    1.0 - transition,
                    False,
                )
            )

        if ghost.kind is GhostKind.FORBIDDEN and ghost.forbidden_patterns:
            insert_index = min(1, len(ghost.remaining_patterns))
            forbidden_x = layout_start(len(ghost.remaining_patterns)) + insert_index * 54 + 27
            entries.append(
                (
                    ghost.forbidden_patterns[0],
                    RED,
                    (forbidden_x, center[1]),
                    1.0,
                    False,
                )
            )

        for pattern, color, pattern_center, entry_alpha, is_first_required in entries:
            crease_axis = self._crease_axis_for_pattern(ghost, pattern)
            display_pattern = self._display_pattern_for_ghost(
                ghost, pattern, crease_axis
            )
            wave_strength = 1.0 if ghost.kind is GhostKind.WAVY else 0.0
            nodes = [
                (
                    pattern_center[0]
                    + (node % 3 - 1) * 11
                    + math.sin(ghost.pulse * 4.6 + node * 1.35) * 3.0 * wave_strength,
                    pattern_center[1]
                    + (node // 3 - 1) * 11
                    + math.sin(ghost.pulse * 5.2 + node * 0.95) * 6.0 * wave_strength,
                )
                for node in range(9)
            ]
            frame_rect = pygame.Rect(
                pattern_center[0] - 18,
                pattern_center[1] - 18,
                36,
                36,
            )
            pygame.draw.rect(
                layer,
                (*color, round(105 * entry_alpha)),
                frame_rect,
                2,
                border_radius=4,
            )
            pygame.draw.line(
                layer,
                (*color, round(45 * entry_alpha)),
                (pattern_center[0], frame_rect.top + 3),
                (pattern_center[0], frame_rect.bottom - 3),
                1,
            )
            pygame.draw.line(
                layer,
                (*color, round(45 * entry_alpha)),
                (frame_rect.left + 3, pattern_center[1]),
                (frame_rect.right - 3, pattern_center[1]),
                1,
            )
            pattern_layers = (
                display_pattern
                if display_pattern and isinstance(display_pattern[0], tuple)
                else (display_pattern,)
            )
            segment_groups: list[tuple[list[tuple[int, int]], float, tuple[int, int, int]]]
            if len(pattern_layers) == 2:
                segment_groups = [
                    (list(zip(pattern_layers[0], pattern_layers[0][1:])), 0.95, CYAN),
                    (list(zip(pattern_layers[1], pattern_layers[1][1:])), 0.95, GOLD),
                ]
            elif ghost.kind is GhostKind.PARTIAL and is_first_required:
                segments = list(zip(display_pattern, display_pattern[1:]))
                blend = (math.sin(ghost.pulse * 1.8) + 1.0) / 2.0
                segment_groups = [
                    (
                        [
                            segment
                            for index, segment in enumerate(segments)
                            if index % 2 == 0
                        ],
                        0.12 + 0.88 * (1.0 - blend),
                        color,
                    ),
                    (
                        [
                            segment
                            for index, segment in enumerate(segments)
                            if index % 2 == 1
                        ],
                        0.12 + 0.88 * blend,
                        color,
                    ),
                ]
            else:
                segments = list(zip(display_pattern, display_pattern[1:]))
                segment_groups = [(segments, 1.0, color)]
            if crease_axis:
                self._draw_crease_axis(layer, frame_rect, crease_axis, color, entry_alpha)
            for group, group_alpha, group_color in segment_groups:
                visible_nodes: set[int] = set()
                draw_alpha = round(255 * entry_alpha * group_alpha)
                for first, second in group:
                    visible_nodes.update((first, second))
                    pygame.draw.line(
                        layer,
                        (*group_color, draw_alpha),
                        nodes[first],
                        nodes[second],
                        6,
                    )
                    pygame.draw.circle(
                        layer, (*group_color, draw_alpha), nodes[first], 3
                    )
                    pygame.draw.circle(
                        layer, (*group_color, draw_alpha), nodes[second], 3
                    )
            if ghost.strict_start and display_pattern and is_first_required:
                pygame.draw.circle(
                    layer,
                    (*color, round(255 * entry_alpha)),
                    nodes[display_pattern[0]],
                    8,
                    2,
                )
        layer.set_alpha(opacity)
        self.screen.blit(layer, (0, 0))

    def _display_pattern_for_ghost(
        self, ghost: Ghost, pattern: object, crease_axis: str
    ) -> object:
        if (
            ghost.kind is GhostKind.CREASE
            and crease_axis
            and pattern
            and not isinstance(pattern[0], tuple)
        ):
            return mirrored_pattern(pattern, crease_axis)
        return pattern

    def _crease_axis_for_pattern(self, ghost: Ghost, pattern: object) -> str:
        if ghost.kind is not GhostKind.CREASE or not ghost.crease_axes:
            return ""
        try:
            index = ghost.remaining_patterns.index(pattern)
        except ValueError:
            return ""
        if index >= len(ghost.crease_axes):
            return ""
        return ghost.crease_axes[index]

    def _draw_crease_axis(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        axis: str,
        color: tuple[int, int, int],
        alpha: float,
    ) -> None:
        if axis == "x":
            lines = [((rect.left + 1, rect.centery), (rect.right - 1, rect.centery), GOLD)]
        elif axis == "y":
            lines = [((rect.centerx, rect.top + 1), (rect.centerx, rect.bottom - 1), GOLD)]
        else:
            lines = [((rect.left + 2, rect.bottom - 2), (rect.right - 2, rect.top + 2), GOLD)]
        for start, end, line_color in lines:
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = max(1.0, math.hypot(dx, dy))
            step = 7
            dash = 4
            count = int(length // step) + 1
            for index in range(count):
                a = min(length, index * step)
                b = min(length, a + dash)
                if a >= length:
                    break
                start_point = (
                    start[0] + dx * a / length,
                    start[1] + dy * a / length,
                )
                end_point = (
                    start[0] + dx * b / length,
                    start[1] + dy * b / length,
                )
                pygame.draw.line(
                    surface,
                    (*line_color, round(255 * alpha)),
                    start_point,
                    end_point,
                    2,
                )

    def _draw_hud(self) -> None:
        hud = pygame.Surface((710, 84), pygame.SRCALPHA)
        pygame.draw.rect(hud, (*PANEL, 165), hud.get_rect(), border_radius=14)
        self.screen.blit(hud, (20, 18))
        self._draw_hearts((44, 48))
        score = self.font.render(f"SCORE  {self.session.score:06d}", True, WHITE)
        self.screen.blit(score, (255, 34))
        wave = self.font.render(f"WAVE  {self.session.wave}", True, GOLD)
        self.screen.blit(wave, (500, 34))

        holy = self.session.spells.holy_power
        pygame.draw.rect(self.screen, PANEL_LIGHT, (255, 71, 220, 12), border_radius=6)
        pygame.draw.rect(
            self.screen,
            CYAN,
            (
                255,
                71,
                int(220 * holy / SpellManager.MAX_POWER),
                12,
            ),
            border_radius=6,
        )
        holy_label = self.font_small.render(
            f"HOLY POWER {holy}/{SpellManager.MAX_POWER}", True, CYAN
        )
        self.screen.blit(holy_label, (255, 88))

        if self.message_timer > 0 and self.session.last_message:
            message = self.font.render(self.session.last_message, True, WHITE)
            box = message.get_rect(center=(470, 135)).inflate(30, 18)
            message_bg = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(
                message_bg, (*PANEL, 175), message_bg.get_rect(), border_radius=10
            )
            self.screen.blit(message_bg, box)
            self.screen.blit(message, message.get_rect(center=box.center))

    def _draw_hearts(self, position: tuple[int, int]) -> None:
        for index in range(self.session.max_health):
            color = RED if index < self.session.health else (67, 54, 72)
            x = position[0] + index * 37
            y = position[1]
            pygame.draw.circle(self.screen, color, (x, y), 10)
            pygame.draw.circle(self.screen, color, (x + 14, y), 10)
            pygame.draw.polygon(
                self.screen,
                color,
                [(x - 10, y + 2), (x + 24, y + 2), (x + 7, y + 23)],
            )

    def _draw_spell_bookmark(self) -> None:
        tab = pygame.Surface(self.spell_tab_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            tab,
            (
                65,
                56,
                105,
                round(185 + 40 * self.spell_panel_progress),
            ),
            tab.get_rect(),
            border_radius=10,
        )
        label = self.font_small.render("SPELLS", True, WHITE)
        label = pygame.transform.rotate(label, 90)
        tab.blit(label, label.get_rect(center=tab.get_rect().center))
        self.screen.blit(tab, self.spell_tab_rect)
        if self.spell_panel_progress <= 0:
            return

        panel_rect = self._spell_panel_rect()
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*PANEL, 112), panel.get_rect(), border_radius=14)
        pygame.draw.rect(
            panel, (94, 80, 136, 175), panel.get_rect(), 2, border_radius=14
        )
        self.screen.blit(panel, panel_rect)
        for index, spell in enumerate(SpellManager.SPELLS):
            row_y = panel_rect.y + 18 + index * 110
            spell_color = (
                GOLD if self.session.spells.can_cast(spell) else MUTED
            )
            title = self.font.render(spell.name, True, spell_color)
            self.screen.blit(title, (panel_rect.x + 18, row_y))
            detail = self.font_small.render(
                f"{spell.description} / {spell.cost}",
                True,
                spell_color,
            )
            self.screen.blit(detail, (panel_rect.x + 18, row_y + 30))
            self._draw_demo_pattern(
                spell.pattern,
                (panel_rect.x + 245, row_y + 40),
                17,
                spell_color,
                show_start=False,
            )
            self._draw_spell_cooldown_gauge(
                spell,
                pygame.Rect(panel_rect.x + 218, row_y + 13, 54, 54),
                spell_color,
            )

    def _draw_spell_cooldown_gauge(
        self,
        spell: SpellDefinition,
        rect: pygame.Rect,
        color: tuple[int, int, int],
    ) -> None:
        progress = self.session.spells.cooldown_progress(spell)
        gauge = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(gauge, (9, 10, 22, 110), gauge.get_rect(), border_radius=6)
        fill_height = round(rect.height * progress)
        if fill_height > 0:
            fill_rect = pygame.Rect(0, rect.height - fill_height, rect.width, fill_height)
            pygame.draw.rect(gauge, (*color, 72), fill_rect, border_radius=6)
        if progress < 1.0:
            veil_height = rect.height - fill_height
            pygame.draw.rect(gauge, (0, 0, 0, 105), (0, 0, rect.width, veil_height), border_radius=6)
        pygame.draw.rect(gauge, (*color, 150), gauge.get_rect(), 2, border_radius=6)
        self.screen.blit(gauge, rect)

    def _draw_reward_orbs(self) -> None:
        target = (365.0, 77.0)
        for orb in self.reward_orbs:
            progress = min(
                1.0, float(orb["elapsed"]) / float(orb["duration"])
            )
            eased = 1.0 - (1.0 - progress) ** 3
            start_x, start_y = orb["start"]
            arc = math.sin(progress * math.pi) * 55
            x = start_x + (target[0] - start_x) * eased
            y = start_y + (target[1] - start_y) * eased - arc
            alpha = round(255 * (1.0 - progress * 0.35))
            glow = pygame.Surface((42, 42), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*CYAN, alpha // 5), (21, 21), 19)
            points = [(21, 7), (32, 21), (21, 35), (10, 21)]
            pygame.draw.polygon(glow, (*CYAN, alpha), points)
            pygame.draw.polygon(glow, (238, 255, 255, alpha), points, 2)
            self.screen.blit(glow, glow.get_rect(center=(round(x), round(y))))

    def _draw_large_grid(self) -> None:
        selected = self.pattern_input.nodes
        dragging = self.pattern_input.dragging
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for first, second in zip(self.pending_shift_pattern, self.pending_shift_pattern[1:]):
            self._draw_neon_line(
                layer,
                self.node_positions[first],
                self.node_positions[second],
                190,
                GOLD,
            )
        for node in self.pending_shift_pattern:
            pygame.draw.circle(layer, (*GOLD, 220), self.node_positions[node], 8)
        line_color = GOLD if self.input_shift_layer and not self.input_shift_cancelled else CYAN
        for first, second in zip(selected, selected[1:]):
            self._draw_neon_line(
                layer,
                self.node_positions[first],
                self.node_positions[second],
                255,
                line_color,
            )
        if dragging and selected:
            start = self.node_positions[selected[-1]]
            mouse = pygame.mouse.get_pos()
            dx = mouse[0] - start[0]
            dy = mouse[1] - start[1]
            distance = math.hypot(dx, dy)
            if distance > GRID_GAP:
                end = (
                    start[0] + dx / distance * GRID_GAP,
                    start[1] + dy / distance * GRID_GAP,
                )
            else:
                end = mouse
            self._draw_neon_line(
                layer,
                start,
                end,
                180,
                line_color,
            )

        for index, position in enumerate(self.node_positions):
            active = index in selected
            base_alpha = 125 if dragging else 38
            border_alpha = 220 if dragging else 82
            pygame.draw.circle(
                layer, (18, 17, 38, base_alpha), position, NODE_RADIUS + 8
            )
            pygame.draw.circle(
                layer,
                (*line_color, 255) if active else (132, 125, 166, border_alpha),
                position,
                NODE_RADIUS,
                4,
            )
            if active:
                pygame.draw.circle(layer, (*line_color, 235), position, 7)
        if self.success_timer > 0 and self.success_pattern:
            progress = 1.0 - self.success_timer / self.success_duration
            self._draw_success_path(layer, self.success_pattern, progress)
        self.screen.blit(layer, (0, 0))

    def _draw_neon_line(
        self,
        surface: pygame.Surface,
        start: tuple[float, float],
        end: tuple[float, float],
        alpha: int,
        color: tuple[int, int, int] = CYAN,
    ) -> None:
        pygame.draw.line(surface, (*color, alpha // 5), start, end, 22)
        pygame.draw.line(surface, (*color, alpha // 2), start, end, 12)
        pygame.draw.line(surface, (225, 255, 255, alpha), start, end, 5)
        for point in (start, end):
            pygame.draw.circle(surface, (*color, alpha // 5), point, 11)
            pygame.draw.circle(surface, (*color, alpha // 2), point, 6)
            pygame.draw.circle(surface, (225, 255, 255, alpha), point, 3)

    def _draw_success_path(
        self,
        surface: pygame.Surface,
        pattern: tuple[int, ...],
        progress: float,
    ) -> None:
        eased = 1.0 - (1.0 - min(1.0, progress)) ** 3
        segments = [
            (
                self.node_positions[first],
                self.node_positions[second],
                math.dist(self.node_positions[first], self.node_positions[second]),
            )
            for first, second in zip(pattern, pattern[1:])
        ]
        total_length = sum(length for _, _, length in segments)
        remaining = total_length * eased
        for start, end, length in segments:
            if remaining <= 0:
                break
            ratio = min(1.0, remaining / length)
            partial_end = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            self._draw_neon_line(surface, start, partial_end, 255)
            remaining -= length

    def _draw_spell_cast_animation(self) -> None:
        progress = 1.0 - self.spell_timer / self.spell_duration
        eased = 1.0 - (1.0 - progress) ** 3
        alpha = round(220 * (1.0 - progress))
        gap = round(30 + eased * 95)
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self._draw_pattern_on_surface(
            layer,
            self.spell_pattern,
            PLAYER_POSITION,
            gap,
            (*GOLD, alpha),
            8,
        )
        self.screen.blit(layer, (0, 0))

    def _draw_pattern_on_surface(
        self,
        surface: pygame.Surface,
        pattern: tuple[int, ...],
        center: tuple[int, int],
        gap: int,
        color: tuple[int, ...],
        width: int,
    ) -> None:
        nodes = [
            (center[0] + (index % 3 - 1) * gap, center[1] + (index // 3 - 1) * gap)
            for index in range(9)
        ]
        for first, second in zip(pattern, pattern[1:]):
            pygame.draw.line(surface, color, nodes[first], nodes[second], width)
        for index in pattern:
            pygame.draw.circle(surface, color, nodes[index], max(5, width // 2 + 1))

    def _draw_demo_pattern(
        self,
        pattern: tuple[int, ...],
        center: tuple[int, int],
        gap: int,
        color: tuple[int, int, int],
        show_start: bool = False,
    ) -> None:
        nodes = [
            (center[0] + (index % 3 - 1) * gap, center[1] + (index // 3 - 1) * gap)
            for index in range(9)
        ]
        for first, second in zip(pattern, pattern[1:]):
            pygame.draw.line(self.screen, color, nodes[first], nodes[second], 4)
        for index in pattern:
            pygame.draw.circle(self.screen, color, nodes[index], 6)
        if show_start and pattern:
            pygame.draw.circle(self.screen, color, nodes[pattern[0]], 9, 2)

    def _draw_gameover(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((9, 7, 22, 205))
        self.screen.blit(overlay, (0, 0))
        title = self.font_title.render("GAME OVER", True, RED)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 220)))
        score = self.font_large.render(
            f"FINAL SCORE  {self.session.score}", True, WHITE
        )
        self.screen.blit(score, score.get_rect(center=(WIDTH // 2, 335)))
        wave = self.font.render(f"Reached wave {self.session.wave}", True, MUTED)
        self.screen.blit(wave, wave.get_rect(center=(WIDTH // 2, 390)))
        self.retry_button.draw(self.screen, self.font)


def main() -> None:
    game = ExorcismGame()
    game.run()


if __name__ == "__main__":
    main()
