from __future__ import annotations

import math
from pathlib import Path
import random
import shutil
import subprocess
import time

try:
    import pygame
except ModuleNotFoundError:
    print("pygame is required. Install it with: python -m pip install pygame")
    raise SystemExit(1)

from core import (
    GameSession,
    Ghost,
    GhostKind,
    PitonBoss,
    PatternInput,
    PatternResult,
    SpellDefinition,
    SpellManager,
    SpellType,
    mirrored_pattern,
    patterns_match,
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


class VideoPlayer:
    def __init__(
        self,
        path: Path,
        size: tuple[int, int],
        fps: float = 30.0,
        duration: float = 10.0,
    ) -> None:
        self.size = size
        self.fps = fps
        self.total_frames = round(fps * duration)
        self.frame_size = size[0] * size[1] * 3
        self.frame_index = 0
        self.elapsed = 0.0
        self.started_at: float | None = None
        self.ended = False
        self.surface: pygame.Surface | None = None
        self.process: subprocess.Popen[bytes] | None = None
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None or not path.exists():
            self.ended = True
            return
        command = [
            ffmpeg,
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-an",
            "-vf",
            f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,"
            f"crop={size[0]}:{size[1]}",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ]
        startup_info = None
        creation_flags = 0
        if hasattr(subprocess, "STARTUPINFO"):
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            startupinfo=startup_info,
            creationflags=creation_flags,
        )
        self._read_next_frame()

    def update(self, seconds: float) -> None:
        if self.ended:
            return
        if self.started_at is None:
            self.elapsed += seconds
        else:
            self.elapsed = time.perf_counter() - self.started_at
        target_frame = min(
            self.total_frames - 1,
            int(self.elapsed * self.fps),
        )
        while self.frame_index <= target_frame and not self.ended:
            self._read_next_frame()
        if self.frame_index >= self.total_frames:
            self.ended = True
            self.close()

    def sync_start(self) -> None:
        self.elapsed = 0.0
        self.started_at = time.perf_counter()

    def _read_next_frame(self) -> None:
        if self.process is None or self.process.stdout is None:
            self.ended = True
            return
        data = self.process.stdout.read(self.frame_size)
        if len(data) != self.frame_size:
            self.ended = True
            self.close()
            return
        self.surface = pygame.image.frombuffer(
            data, self.size, "RGB"
        ).copy()
        self.frame_index += 1

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
        self.process = None


class ExorcismGame:
    def __init__(self) -> None:
        pygame.init()
        pygame.mixer.set_num_channels(24)
        pygame.mixer.set_reserved(1)
        pygame.display.set_caption("Exocism")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.Font(None, 24)
        self.font = pygame.font.Font(None, 32)
        self.font_large = pygame.font.Font(None, 54)
        self.font_title = pygame.font.Font(None, 92)
        dialogue_font_path = (
            pygame.font.match_font("malgungothic")
            or pygame.font.match_font("nanumgothic")
            or pygame.font.match_font("notosanscjkkr")
        )
        self.dialogue_font = pygame.font.Font(dialogue_font_path, 30)
        self.state = "menu"
        self.running = True
        self.menu_background = self._load_cover_image("main.png")
        self.menu_reveal_elapsed = 0.0
        self.menu_reveal_duration = 1.0
        self.screen_transition_target: str | None = None
        self.screen_transition_elapsed = 0.0
        self.screen_transition_duration = 0.9
        self.screen_transition_switched = False
        self.bgm_volume = 1.0
        self.sfx_volume = 1.0
        self.active_slider: str | None = None
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
        self.player_attack_image = self._load_scaled_image(
            "peter_attack1.png",
            145,
        )
        self.player_attack_timer = 0.0
        self.player_attack_duration = 0.65
        self.ghost_images = self._load_ghost_images()
        self.piton_images = {
            state: self._load_scaled_image(f"piton_{state}.png", 176)
            for state in ("idle", "attacked", "defeated")
        }
        self.defeat_background = self._load_cover_image(
            "peter_defeat_scene.png"
        )
        self.stage_background = self._load_cover_image("stage1.png")
        self.story_background: pygame.Surface | None = None
        self.boss_epilogue_background = self._load_cover_image("scene2.png")
        self.pending_shift_pattern: tuple[int, ...] = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.grid_intro_elapsed = 0.0
        self.grid_intro_duration = 1.05
        self.start_button = Button(pygame.Rect(470, 405, 260, 58), "START")
        self.settings_button = Button(
            pygame.Rect(470, 478, 260, 58),
            "SETTINGS",
        )
        self.settings_back_button = Button(
            pygame.Rect(470, 585, 260, 54),
            "BACK",
        )
        self.bgm_slider_rect = pygame.Rect(430, 322, 340, 12)
        self.sfx_slider_rect = pygame.Rect(430, 432, 340, 12)
        self.retry_button = Button(pygame.Rect(490, 480, 220, 64), "RETRY")
        self.resume_button = Button(pygame.Rect(490, 330, 220, 64), "RESUME")
        self.pause_restart_button = Button(pygame.Rect(490, 410, 220, 64), "RESTART")
        self.node_positions = self._make_grid_positions()
        self.tutorial_pattern = (3, 4, 5)
        self.tutorial_reveal_elapsed = 0.0
        self.tutorial_reveal_duration = 1.05
        self.tutorial_success_elapsed = 0.0
        self.tutorial_success_duration = 1.2
        self.tutorial_success_active = False
        self.tutorial_video = VideoPlayer(
            Path(__file__).with_name("exorcism_sceen1.mp4"),
            (WIDTH, HEIGHT),
        )
        self.tutorial_video_sound = self._load_tutorial_video_sound(
            Path(__file__).with_name("exorcism_sceen1.mp4")
        )
        self.tutorial_video_channel: pygame.mixer.Channel | None = None
        self.magic_spell_sound = self._load_audio_sound(
            Path(__file__).with_name("magic_spell.mp3"),
            volume_gain=1.0,
        )
        self.magic_spell_channel = pygame.mixer.Channel(0)
        self.story_video: VideoPlayer | None = None
        self.story_video_sound: pygame.mixer.Sound | None = None
        self.story_video_channel: pygame.mixer.Channel | None = None
        self.story_music_path = Path(__file__).with_name("intro_atmosphere.mp3")
        self.story_music_sound = self._load_audio_sound(
            self.story_music_path,
            volume_gain=3.0,
            start_seconds=8.0,
        )
        self.story_music_channel: pygame.mixer.Channel | None = None
        self.intro_story_dialogue_lines = (
            "...기운이 깊다. 이곳인가.",
            "의뢰인은 이 저택에서 사라진 가족의 목소리를 들었다고 했지.",
            "그 목소리의 근원... 확인해야겠군",
        )
        self.story_dialogue_lines = self.intro_story_dialogue_lines
        self.story_dialogue_index = 0
        self.story_dialogue_elapsed = 0.0
        self.story_dialogue_fade_duration = 0.24
        self.story_dialogue_typing_elapsed = 0.0
        self.story_dialogue_visible_characters = 0
        self.story_dialogue_spoken_pairs = 0
        self.story_dialogue_character_delay = 0.035
        self.story_dialogue_character_rise_duration = 0.12
        self.story_prompt_elapsed = 0.0
        self.story_prompt_fade_duration = 0.28
        self.story_dialogue_active = False
        self.story_dialogue_phase = "fade_in"
        self.story_transition_elapsed = 0.0
        self.story_transition_duration = 1.8
        self.story_game_ready = False
        self.story_destination_stage = 1
        self.stage_clear_elapsed = 0.0
        self.stage_clear_delay = 1.35
        self.boss_transition_elapsed = 0.0
        self.boss_transition_duration = 1.5
        self.boss_video: VideoPlayer | None = None
        self.boss_video_sound = self._load_tutorial_video_sound(
            Path(__file__).with_name("exorcism3.mp4")
        )
        self.boss_video_channel: pygame.mixer.Channel | None = None
        self.boss_support_timer = 4.5
        self.boss_epilogue_elapsed = 0.0
        self.boss_epilogue_duration = 1.8
        self.boss_epilogue_scene_ready = False
        self.boss_epilogue_started = False
        self.defeat_transition_elapsed = 0.0
        self.defeat_transition_duration = 1.4
        self.defeat_scene_ready = False
        self.peter_speak_sound = self._load_sound("peter_speak.wav")
        if self.peter_speak_sound is not None:
            self.peter_speak_sound.set_volume(0.42)
        self.boo_sounds = [
            sound
            for filename in ("boo1.mp3", "boo2.mp3", "boo3.mp3")
            if (sound := self._load_sound(filename)) is not None
        ]
        for sound in self.boo_sounds:
            sound.set_volume(0.72)
        self.ghost_defeated_sound = self._load_sound("ghost_defeated.mp3")
        if self.ghost_defeated_sound is not None:
            self.ghost_defeated_sound.set_volume(0.85)
        self.ghost_boo_channels: dict[int, pygame.mixer.Channel] = {}
        self._apply_audio_settings()
        self._start_ambient_audio()

    def _load_sound(self, filename: str) -> pygame.mixer.Sound | None:
        sound_path = Path(__file__).with_name(filename)
        if not sound_path.exists():
            return None
        try:
            return pygame.mixer.Sound(str(sound_path))
        except pygame.error:
            return None

    def _load_tutorial_video_sound(
        self, video_path: Path
    ) -> pygame.mixer.Sound | None:
        return self._load_audio_sound(video_path)

    def _load_audio_sound(
        self,
        audio_path: Path,
        volume_gain: float = 1.0,
        start_seconds: float = 0.0,
    ) -> pygame.mixer.Sound | None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None or not audio_path.exists():
            return None
        command = [
            ffmpeg,
            "-loglevel",
            "error",
        ]
        if start_seconds > 0.0:
            command.extend(["-ss", str(start_seconds)])
        command.extend([
            "-i",
            str(audio_path),
            "-vn",
        ])
        if volume_gain != 1.0:
            command.extend(["-af", f"volume={volume_gain}"])
        command.extend([
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-",
        ])
        startup_info = None
        creation_flags = 0
        if hasattr(subprocess, "STARTUPINFO"):
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
                startupinfo=startup_info,
                creationflags=creation_flags,
            )
            return pygame.mixer.Sound(buffer=result.stdout)
        except (OSError, subprocess.CalledProcessError, pygame.error):
            return None

    def _start_ambient_audio(self) -> None:
        if self.story_music_sound is not None:
            self.story_music_channel = self.story_music_sound.play(loops=-1)
        self._apply_audio_settings()

    def _begin_tutorial(self) -> None:
        self.tutorial_video.close()
        tutorial_path = Path(__file__).with_name("exorcism_sceen1.mp4")
        self.tutorial_video = VideoPlayer(tutorial_path, (WIDTH, HEIGHT))
        self.tutorial_reveal_elapsed = 0.0
        self.tutorial_success_elapsed = 0.0
        self.tutorial_success_active = False
        self.pattern_input.clear()
        self.state = "tutorial"
        if self.tutorial_video_sound is not None:
            self.tutorial_video_channel = self.tutorial_video_sound.play()
        self.tutorial_video.sync_start()
        self._apply_audio_settings()

    def _apply_audio_settings(self) -> None:
        if self.story_music_channel is not None:
            self.story_music_channel.set_volume(0.2 * self.bgm_volume)
        if self.tutorial_video_channel is not None:
            self.tutorial_video_channel.set_volume(self.sfx_volume)
        if self.story_video_channel is not None:
            self.story_video_channel.set_volume(0.72 * self.sfx_volume)
        if self.boss_video_channel is not None:
            self.boss_video_channel.set_volume(0.78 * self.sfx_volume)
        if self.peter_speak_sound is not None:
            self.peter_speak_sound.set_volume(0.42 * self.sfx_volume)
        for sound in self.boo_sounds:
            sound.set_volume(0.72 * self.sfx_volume)
        if self.ghost_defeated_sound is not None:
            self.ghost_defeated_sound.set_volume(0.85 * self.sfx_volume)
        if self.magic_spell_sound is not None:
            self.magic_spell_sound.set_volume(self.sfx_volume)

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

    def _load_cover_image(self, filename: str) -> pygame.Surface | None:
        image_path = Path(__file__).with_name(filename)
        if not image_path.exists():
            return None
        image = pygame.image.load(image_path).convert()
        scale = max(WIDTH / image.get_width(), HEIGHT / image.get_height())
        size = (
            round(image.get_width() * scale),
            round(image.get_height() * scale),
        )
        scaled = pygame.transform.smoothscale(image, size)
        source = pygame.Rect(
            (scaled.get_width() - WIDTH) // 2,
            (scaled.get_height() - HEIGHT) // 2,
            WIDTH,
            HEIGHT,
        )
        return scaled.subsurface(source).copy()

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
        self.tutorial_video.close()
        if self.story_video is not None:
            self.story_video.close()
        if self.boss_video is not None:
            self.boss_video.close()
        if self.tutorial_video_channel is not None:
            self.tutorial_video_channel.stop()
        if self.story_video_channel is not None:
            self.story_video_channel.stop()
        if self.boss_video_channel is not None:
            self.boss_video_channel.stop()
        if self.story_music_channel is not None:
            self.story_music_channel.stop()
        if self.magic_spell_channel is not None:
            self.magic_spell_channel.stop()
        self._stop_all_ghost_boo()
        pygame.quit()

    def _start_game(self) -> None:
        self._stop_all_ghost_boo()
        self.session.reset()
        self.pattern_input.clear()
        self.last_drag_position = None
        self.success_pattern = ()
        self.success_timer = 0.0
        self.pending_shift_pattern = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.grid_intro_elapsed = 0.0
        self.spell_pattern = ()
        self.spell_timer = 0.0
        self.spell_panel_progress = 0.0
        self.spell_panel_hover_grace = 0.0
        self.reward_orbs.clear()
        self.player_attack_timer = 0.0
        self.stage_clear_elapsed = 0.0
        self.boss_transition_elapsed = 0.0
        self.boss_support_timer = 4.5
        self.spawn_timer = self.grid_intro_duration + 0.25
        self.message_timer = 0.0
        self.state = "playing"

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif self.screen_transition_target is not None:
                continue
            elif (
                event.type == pygame.KEYDOWN
                and event.key == pygame.K_g
                and event.mod & pygame.KMOD_CTRL
                and event.mod & pygame.KMOD_SHIFT
            ):
                self._handle_secret_skip()
                continue
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.state == "playing":
                    self._pause_game()
                elif self.state == "paused":
                    self._resume_game()
                elif self.state == "settings":
                    self._start_screen_transition("menu")
                else:
                    self.running = False

            if self.state == "menu":
                if self.start_button.clicked(event):
                    self._start_screen_transition("tutorial")
                elif self.settings_button.clicked(event):
                    self._start_screen_transition("settings")
                elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                ):
                    self._start_screen_transition("tutorial")
            elif self.state == "settings":
                self._handle_settings_event(event)
            elif self.state == "tutorial":
                self._handle_tutorial_event(event)
            elif self.state == "story":
                self._handle_story_event(event)
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

    def _handle_settings_event(self, event: pygame.event.Event) -> None:
        if self.settings_back_button.clicked(event):
            self.active_slider = None
            self._start_screen_transition("menu")
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.bgm_slider_rect.inflate(0, 30).collidepoint(event.pos):
                self.active_slider = "bgm"
            elif self.sfx_slider_rect.inflate(0, 30).collidepoint(event.pos):
                self.active_slider = "sfx"
            if self.active_slider is not None:
                self._set_slider_volume(event.pos[0])
        elif event.type == pygame.MOUSEMOTION and self.active_slider is not None:
            self._set_slider_volume(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.active_slider = None

    def _set_slider_volume(self, mouse_x: int) -> None:
        rect = (
            self.bgm_slider_rect
            if self.active_slider == "bgm"
            else self.sfx_slider_rect
        )
        value = max(0.0, min(1.0, (mouse_x - rect.left) / rect.width))
        if self.active_slider == "bgm":
            self.bgm_volume = value
        else:
            self.sfx_volume = value
        self._apply_audio_settings()

    def _start_screen_transition(self, target: str) -> None:
        if self.screen_transition_target is not None:
            return
        self.screen_transition_target = target
        self.screen_transition_elapsed = 0.0
        self.screen_transition_switched = False

    def _switch_screen_transition_target(self) -> None:
        target = self.screen_transition_target
        if target == "tutorial":
            self._begin_tutorial()
        elif target in ("menu", "settings"):
            self.state = target
            if target == "menu":
                self.menu_reveal_elapsed = self.menu_reveal_duration
        self.screen_transition_switched = True

    def _handle_tutorial_event(self, event: pygame.event.Event) -> None:
        if (
            not self.tutorial_video.ended
            or self.tutorial_reveal_elapsed < self.tutorial_reveal_duration
            or self.tutorial_success_active
        ):
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            node = self._node_at(event.pos)
            if node is not None:
                self.pattern_input.begin(node)
                self.last_drag_position = event.pos
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
            if patterns_match(pattern, self.tutorial_pattern):
                self._start_tutorial_success()

    def _start_tutorial_success(self) -> None:
        if self.tutorial_success_active:
            return
        self.tutorial_success_active = True
        self.tutorial_success_elapsed = 0.0
        self.pattern_input.clear()
        self._play_magic_spell_sound()

    def _finish_tutorial(self) -> None:
        if self.tutorial_video_channel is not None:
            self.tutorial_video_channel.stop()
            self.tutorial_video_channel = None
        if self.magic_spell_channel is not None:
            self.magic_spell_channel.stop()
        self.tutorial_video.close()
        self._start_story_scene()

    def _start_story_scene(self) -> None:
        self.state = "story"
        self.story_background = None
        self.story_destination_stage = 1
        self.story_dialogue_lines = self.intro_story_dialogue_lines
        self.story_dialogue_index = 0
        self.story_dialogue_elapsed = 0.0
        self.story_dialogue_typing_elapsed = 0.0
        self.story_dialogue_visible_characters = 0
        self.story_dialogue_spoken_pairs = 0
        self.story_prompt_elapsed = 0.0
        self.story_dialogue_active = False
        self.story_dialogue_phase = "fade_in"
        self.story_transition_elapsed = 0.0
        self.story_game_ready = False
        story_path = Path(__file__).with_name("exorcism_sceen2.mp4")
        self.story_video = VideoPlayer(
            story_path,
            (WIDTH, HEIGHT),
            duration=5.92,
        )
        self.story_video_sound = self._load_tutorial_video_sound(story_path)
        if self.story_video_sound is not None:
            self.story_video_channel = self.story_video_sound.play()
        if self.story_video is not None:
            self.story_video.sync_start()
        self._apply_audio_settings()

    def _handle_story_event(self, event: pygame.event.Event) -> None:
        if (
            not self.story_dialogue_active
            or self.story_dialogue_phase != "hold"
        ):
            return
        advance = (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
        ) or (
            event.type == pygame.KEYDOWN
            and event.key in (pygame.K_RETURN, pygame.K_SPACE)
        )
        if not advance:
            return
        self.story_dialogue_phase = "fade_out"
        self.story_dialogue_elapsed = 0.0

    def _start_story_transition(self) -> None:
        self.state = "story_transition"
        self.story_transition_elapsed = 0.0
        self.story_game_ready = False
        if self.story_video_channel is not None:
            self.story_video_channel.stop()
            self.story_video_channel = None
        if self.story_video is not None:
            self.story_video.close()

    def _prepare_game_after_story(self) -> None:
        if self.story_destination_stage == 2:
            self._prepare_stage_two()
        else:
            self._start_game()
        self.state = "story_transition"
        self.story_game_ready = True

    def _start_boss_intro_transition(self) -> None:
        self.state = "boss_intro_transition"
        self.boss_transition_elapsed = 0.0
        self.pattern_input.clear()
        self._stop_all_ghost_boo()

    def _start_boss_video(self) -> None:
        boss_path = Path(__file__).with_name("exorcism3.mp4")
        self.boss_video = VideoPlayer(
            boss_path,
            (WIDTH, HEIGHT),
            duration=6.04,
        )
        if self.boss_video_sound is not None:
            self.boss_video_channel = self.boss_video_sound.play()
        self.boss_video.sync_start()
        self._apply_audio_settings()
        self.state = "boss_video"

    def _start_boss_return_transition(self) -> None:
        self.state = "boss_return_transition"
        self.boss_transition_elapsed = 0.0
        if self.boss_video_channel is not None:
            self.boss_video_channel.stop()
            self.boss_video_channel = None

    def _prepare_boss_battle(self) -> None:
        self.session.start_boss_battle(SPAWN_POSITIONS, PLAYER_POSITION)
        self.grid_intro_elapsed = 0.0
        self.spawn_timer = self.grid_intro_duration + 0.25
        self.boss_support_timer = 2.8

    def _skip_intro(self) -> None:
        if self.tutorial_video_channel is not None:
            self.tutorial_video_channel.stop()
            self.tutorial_video_channel = None
        if self.story_video_channel is not None:
            self.story_video_channel.stop()
            self.story_video_channel = None
        self.magic_spell_channel.stop()
        self.tutorial_video.close()
        if self.story_video is not None:
            self.story_video.close()
        self._start_game()

    def _handle_secret_skip(self) -> None:
        if (
            self.state in ("story", "story_transition")
            and self.story_destination_stage == 2
        ):
            return
        if self.state in ("tutorial", "story", "story_transition"):
            self._skip_intro()
        elif self.state == "playing" and self.session.boss_battle:
            self._skip_to_boss_epilogue()
        elif self.state == "playing" and not self.session.boss_battle:
            self.session.spawn_queue.clear()
            self.session.kind_queue.clear()
            self.session.ghosts.clear()
            self.session.stage_cleared = True
            self.stage_clear_elapsed = self.stage_clear_delay
            self._start_boss_intro_transition()
        elif self.state in (
            "boss_intro_transition",
            "boss_video",
            "boss_return_transition",
        ):
            self._skip_to_boss_battle()

    def _skip_to_boss_battle(self) -> None:
        if self.boss_video_channel is not None:
            self.boss_video_channel.stop()
            self.boss_video_channel = None
        if self.boss_video is not None:
            self.boss_video.close()
        if self.session.boss is None:
            self._prepare_boss_battle()
        self.state = "playing"
        self.grid_intro_elapsed = 0.0

    def _skip_to_boss_epilogue(self) -> None:
        boss = self.session.boss
        if boss is None:
            return
        boss.defeated = True
        boss.fade_remaining = boss.fade_duration
        boss.knockback_active = False
        self.session.defeat_all_ghosts()
        self.session.boss_last_event = "defeated"
        self._stop_all_ghost_boo()
        if self.ghost_defeated_sound is not None:
            self.ghost_defeated_sound.play()
        self.pattern_input.clear()
        self.last_drag_position = None
        self.pending_shift_pattern = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.state = "playing"

    def _prepare_stage_two(self) -> None:
        self._stop_all_ghost_boo()
        self.session.start_stage(2)
        self.pattern_input.clear()
        self.last_drag_position = None
        self.pending_shift_pattern = ()
        self.input_shift_layer = False
        self.input_shift_cancelled = False
        self.success_pattern = ()
        self.success_timer = 0.0
        self.spell_pattern = ()
        self.spell_timer = 0.0
        self.reward_orbs.clear()
        self.player_attack_timer = 0.0
        self.stage_clear_elapsed = 0.0
        self.grid_intro_elapsed = 0.0
        self.spawn_timer = self.grid_intro_duration + 0.25
        self.message_timer = 0.0
        self.boss_epilogue_started = False

    def _start_boss_epilogue_transition(self) -> None:
        if self.boss_epilogue_started:
            return
        self.boss_epilogue_started = True
        self.boss_epilogue_elapsed = 0.0
        self.boss_epilogue_scene_ready = False
        self.pattern_input.clear()
        self._stop_all_ghost_boo()
        self.state = "boss_epilogue_transition"

    def _start_boss_epilogue_story(self) -> None:
        self.story_dialogue_lines = (
            "융합된 영혼들... 의지로 모인 게 아니었군.",
            "누군가 이들을 묶고, 본관 쪽으로 흘려보낸 것이겠지.",
            "의뢰인은 창고를 말했지만... 진짜 근원은 저택 안쪽이군.",
        )
        self.story_dialogue_index = 0
        self.story_dialogue_elapsed = 0.0
        self.story_dialogue_typing_elapsed = 0.0
        self.story_dialogue_visible_characters = 0
        self.story_dialogue_spoken_pairs = 0
        self.story_prompt_elapsed = 0.0
        self.story_dialogue_active = False
        self.story_dialogue_phase = "fade_in"
        self.story_transition_elapsed = 0.0
        self.story_game_ready = False
        self.story_destination_stage = 2
        self.story_background = self.boss_epilogue_background
        self.story_video = None
        self.story_video_sound = None
        self.story_video_channel = None
        self.state = "story"

    def _start_defeat_transition(self) -> None:
        if self.state in ("defeat_transition", "gameover"):
            return
        self.state = "defeat_transition"
        self.defeat_transition_elapsed = 0.0
        self.defeat_scene_ready = False
        self.pattern_input.clear()
        self._stop_all_ghost_boo()

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
        if self.grid_intro_elapsed < self.grid_intro_duration:
            return
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
        previously_vanishing = {
            id(ghost) for ghost in self.session.ghosts if ghost.vanishing
        }
        result = self.session.judge_pattern(pattern)
        if (
            self.session.boss_last_event == "defeated"
            and self.ghost_defeated_sound is not None
        ):
            self.ghost_defeated_sound.play()
        defeated_ghosts = [
            ghost
            for ghost in self.session.ghosts
            if ghost.vanishing and id(ghost) not in previously_vanishing
        ]
        for ghost in defeated_ghosts:
            self._play_ghost_defeated_sound(ghost)
        if self.session.last_match_count or self.session.last_spell_cast:
            self.success_pattern = pattern if pattern and isinstance(pattern[0], int) else ()
            self.success_timer = self.success_duration
            self.player_attack_timer = self.player_attack_duration
            self._play_magic_spell_sound()
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

    def _play_magic_spell_sound(self) -> None:
        if self.magic_spell_sound is not None:
            self.magic_spell_channel.play(self.magic_spell_sound)

    def _play_ghost_spawn_sound(self, ghost: Ghost) -> None:
        if not self.boo_sounds:
            return
        channel = random.choice(self.boo_sounds).play()
        if channel is not None:
            self.ghost_boo_channels[id(ghost)] = channel

    def _play_ghost_defeated_sound(self, ghost: Ghost) -> None:
        channel = self.ghost_boo_channels.pop(id(ghost), None)
        if channel is not None:
            channel.stop()
            if self.ghost_defeated_sound is not None:
                channel.play(self.ghost_defeated_sound)
        elif self.ghost_defeated_sound is not None:
            self.ghost_defeated_sound.play()

    def _stop_all_ghost_boo(self) -> None:
        for channel in self.ghost_boo_channels.values():
            channel.stop()
        self.ghost_boo_channels.clear()

    def _remove_inactive_ghost_boo_channels(self) -> None:
        active_ids = {id(ghost) for ghost in self.session.ghosts}
        for ghost_id, channel in list(self.ghost_boo_channels.items()):
            if ghost_id not in active_ids or not channel.get_busy():
                if ghost_id not in active_ids:
                    channel.stop()
                self.ghost_boo_channels.pop(ghost_id, None)

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
        if self.screen_transition_target is not None:
            self.screen_transition_elapsed = min(
                self.screen_transition_duration,
                self.screen_transition_elapsed + seconds,
            )
            midpoint = self.screen_transition_duration / 2.0
            if (
                not self.screen_transition_switched
                and self.screen_transition_elapsed >= midpoint
            ):
                self._switch_screen_transition_target()
            if self.screen_transition_elapsed >= self.screen_transition_duration:
                self.screen_transition_target = None
                self.screen_transition_switched = False
        if self.state == "menu":
            self.menu_reveal_elapsed = min(
                self.menu_reveal_duration,
                self.menu_reveal_elapsed + seconds,
            )
            return
        if self.state == "settings":
            return
        if self.state == "tutorial":
            self._update_tutorial(seconds)
            return
        if self.state == "story":
            self._update_story(seconds)
            return
        if self.state == "story_transition":
            self._update_story_transition(seconds)
            return
        if self.state == "boss_intro_transition":
            self.boss_transition_elapsed = min(
                self.boss_transition_duration,
                self.boss_transition_elapsed + seconds,
            )
            if self.boss_transition_elapsed >= self.boss_transition_duration:
                self._start_boss_video()
            return
        if self.state == "boss_video":
            if self.boss_video is not None:
                self.boss_video.update(seconds)
                if self.boss_video.ended:
                    self._start_boss_return_transition()
            return
        if self.state == "boss_return_transition":
            self._update_boss_return_transition(seconds)
            return
        if self.state == "boss_epilogue_transition":
            self._update_boss_epilogue_transition(seconds)
            return
        if self.state == "defeat_transition":
            self._update_defeat_transition(seconds)
            return
        if self.state != "playing":
            return

        if self.session.stage_cleared and not self.session.boss_battle:
            self.stage_clear_elapsed += seconds
            if self.stage_clear_elapsed >= self.stage_clear_delay:
                self._start_boss_intro_transition()
            return

        if self.session.boss_battle:
            self._update_boss_battle(seconds)
        else:
            self.spawn_timer -= seconds
            active_limit = min(2 + self.session.wave // 2, 5)
            if (
                self.spawn_timer <= 0
                and self.session.spawn_queue
                and len(self.session.ghosts) < active_limit
            ):
                existing_ghost_ids = {id(ghost) for ghost in self.session.ghosts}
                spawned = self.session.spawn_next(
                    SPAWN_POSITIONS,
                    PLAYER_POSITION,
                )
                if spawned:
                    for ghost in self.session.ghosts:
                        if id(ghost) not in existing_ghost_ids:
                            self._play_ghost_spawn_sound(ghost)
                self.spawn_timer = (
                    max(0.75, 2.15 - self.session.wave * 0.1)
                    if spawned
                    else 0.25
                )

        escaped = self.session.update_ghosts(
            seconds, PLAYER_POSITION, PLAYER_RADIUS
        )
        self._remove_inactive_ghost_boo_channels()
        boss = self.session.boss
        if (
            self.session.boss_battle
            and boss is not None
            and boss.defeated
            and boss.fade_remaining <= 0
            and not self.session.ghosts
        ):
            self._start_boss_epilogue_transition()
            return
        if escaped:
            self.message_timer = 1.8
            self.flash_color = RED
            self.flash_timer = 0.22
        if self.session.health <= 0:
            self._start_defeat_transition()
            return

        if self.session.advance_wave_if_clear():
            self.spawn_timer = 1.1
            self.message_timer = 1.8

        self.message_timer = max(0.0, self.message_timer - seconds)
        self.flash_timer = max(0.0, self.flash_timer - seconds)
        self.success_timer = max(0.0, self.success_timer - seconds)
        self.spell_timer = max(0.0, self.spell_timer - seconds)
        self.player_attack_timer = max(
            0.0,
            self.player_attack_timer - seconds,
        )
        self.grid_intro_elapsed = min(
            self.grid_intro_duration,
            self.grid_intro_elapsed + seconds,
        )
        self._update_spell_panel(seconds)
        for orb in list(self.reward_orbs):
            orb["elapsed"] = float(orb["elapsed"]) + seconds
            if float(orb["elapsed"]) >= float(orb["duration"]):
                self.reward_orbs.remove(orb)

    def _update_tutorial(self, seconds: float) -> None:
        self.tutorial_video.update(seconds)
        if self.tutorial_video.ended:
            if self.tutorial_video_channel is not None:
                self.tutorial_video_channel.stop()
                self.tutorial_video_channel = None
            self.tutorial_reveal_elapsed = min(
                self.tutorial_reveal_duration,
                self.tutorial_reveal_elapsed + seconds,
            )
        if self.tutorial_success_active:
            self.tutorial_success_elapsed = min(
                self.tutorial_success_duration,
                self.tutorial_success_elapsed + seconds,
            )
            if self.tutorial_success_elapsed >= self.tutorial_success_duration:
                self._finish_tutorial()

    def _update_story(self, seconds: float) -> None:
        if self.story_video is None:
            self._activate_story_dialogue()
        else:
            self.story_video.update(seconds)
            if self.story_video.ended:
                if self.story_video_channel is not None:
                    self.story_video_channel.stop()
                    self.story_video_channel = None
                self._activate_story_dialogue()
        if not self.story_dialogue_active:
            return
        if self.story_dialogue_phase == "fade_in":
            self.story_dialogue_elapsed = min(
                self.story_dialogue_fade_duration,
                self.story_dialogue_elapsed + seconds,
            )
            if self.story_dialogue_elapsed >= self.story_dialogue_fade_duration:
                self.story_dialogue_phase = "typing"
                self.story_dialogue_typing_elapsed = 0.0
                self.story_dialogue_visible_characters = 0
                self.story_dialogue_spoken_pairs = 0
        elif self.story_dialogue_phase == "typing":
            self.story_dialogue_typing_elapsed += seconds
            line = self.story_dialogue_lines[self.story_dialogue_index]
            visible_characters = min(
                len(line),
                int(
                    self.story_dialogue_typing_elapsed
                    / self.story_dialogue_character_delay
                )
                + 1,
            )
            spoken_pairs = visible_characters // 2
            for _ in range(self.story_dialogue_spoken_pairs, spoken_pairs):
                if self.peter_speak_sound is not None:
                    self.peter_speak_sound.play()
            self.story_dialogue_visible_characters = visible_characters
            self.story_dialogue_spoken_pairs = spoken_pairs
            typing_duration = (
                max(0, len(line) - 1) * self.story_dialogue_character_delay
                + self.story_dialogue_character_rise_duration
            )
            if self.story_dialogue_typing_elapsed >= typing_duration:
                self.story_dialogue_phase = "hold"
                self.story_prompt_elapsed = 0.0
        elif self.story_dialogue_phase == "hold":
            self.story_prompt_elapsed = min(
                self.story_prompt_fade_duration,
                self.story_prompt_elapsed + seconds,
            )
        elif self.story_dialogue_phase == "fade_out":
            self.story_dialogue_elapsed = min(
                self.story_dialogue_fade_duration,
                self.story_dialogue_elapsed + seconds,
            )
            if self.story_dialogue_elapsed >= self.story_dialogue_fade_duration:
                if self.story_dialogue_index < len(self.story_dialogue_lines) - 1:
                    self.story_dialogue_index += 1
                    self.story_dialogue_phase = "fade_in"
                    self.story_dialogue_elapsed = 0.0
                    self.story_dialogue_typing_elapsed = 0.0
                    self.story_dialogue_visible_characters = 0
                    self.story_dialogue_spoken_pairs = 0
                    self.story_prompt_elapsed = 0.0
                else:
                    self._start_story_transition()

    def _activate_story_dialogue(self) -> None:
        if self.story_dialogue_active:
            return
        self.story_dialogue_active = True
        self.story_dialogue_phase = "fade_in"
        self.story_dialogue_elapsed = 0.0
        self.story_dialogue_typing_elapsed = 0.0
        self.story_dialogue_visible_characters = 0
        self.story_dialogue_spoken_pairs = 0
        self.story_prompt_elapsed = 0.0

    def _update_story_transition(self, seconds: float) -> None:
        self.story_transition_elapsed = min(
            self.story_transition_duration,
            self.story_transition_elapsed + seconds,
        )
        midpoint = self.story_transition_duration / 2.0
        if (
            not self.story_game_ready
            and self.story_transition_elapsed >= midpoint
        ):
            self._prepare_game_after_story()
        if self.story_game_ready:
            self.grid_intro_elapsed = min(
                self.grid_intro_duration,
                self.story_transition_elapsed - midpoint,
            )
        if self.story_transition_elapsed >= self.story_transition_duration:
            self.state = "playing"

    def _update_boss_return_transition(self, seconds: float) -> None:
        self.boss_transition_elapsed = min(
            self.story_transition_duration,
            self.boss_transition_elapsed + seconds,
        )
        midpoint = self.story_transition_duration / 2.0
        if (
            self.session.boss is None
            and self.boss_transition_elapsed >= midpoint
        ):
            self._prepare_boss_battle()
        if self.session.boss is not None:
            self.grid_intro_elapsed = min(
                self.grid_intro_duration,
                self.boss_transition_elapsed - midpoint,
            )
        if self.boss_transition_elapsed >= self.story_transition_duration:
            self.state = "playing"

    def _update_boss_epilogue_transition(self, seconds: float) -> None:
        self.boss_epilogue_elapsed = min(
            self.boss_epilogue_duration,
            self.boss_epilogue_elapsed + seconds,
        )
        midpoint = self.boss_epilogue_duration / 2.0
        if (
            not self.boss_epilogue_scene_ready
            and self.boss_epilogue_elapsed >= midpoint
        ):
            self.boss_epilogue_scene_ready = True
        if self.boss_epilogue_elapsed >= self.boss_epilogue_duration:
            self._start_boss_epilogue_story()

    def _update_boss_battle(self, seconds: float) -> None:
        boss = self.session.boss
        if boss is None:
            return
        damage = self.session.update_boss(
            seconds,
            SPAWN_POSITIONS,
            PLAYER_POSITION,
            PLAYER_RADIUS,
        )
        if damage:
            self.flash_color = RED
            self.flash_timer = 0.3
        if boss.defeated:
            return
        self.boss_support_timer -= seconds
        support_limits = (3, 4, 5)
        support_limit = support_limits[boss.row_index]
        if self.boss_support_timer <= 0 and len(self.session.ghosts) < support_limit:
            ghost = self.session.spawn_boss_support(
                SPAWN_POSITIONS,
                PLAYER_POSITION,
            )
            if ghost is not None:
                self._play_ghost_spawn_sound(ghost)
            intervals = (3.8, 2.7, 1.8)
            self.boss_support_timer = (
                intervals[boss.row_index] if ghost is not None else 0.25
            )

    def _update_defeat_transition(self, seconds: float) -> None:
        self.defeat_transition_elapsed = min(
            self.defeat_transition_duration,
            self.defeat_transition_elapsed + seconds,
        )
        midpoint = self.defeat_transition_duration / 2.0
        if (
            not self.defeat_scene_ready
            and self.defeat_transition_elapsed >= midpoint
        ):
            self.defeat_scene_ready = True
        if self.defeat_transition_elapsed >= self.defeat_transition_duration:
            self.state = "gameover"

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
        if self.state == "menu":
            self._draw_menu()
        elif self.state == "settings":
            self._draw_settings()
        elif self.state == "tutorial":
            self._draw_tutorial()
        elif self.state == "story":
            self._draw_story()
        elif self.state == "story_transition":
            self._draw_story_transition()
        elif self.state == "boss_intro_transition":
            self._draw_boss_intro_transition()
        elif self.state == "boss_video":
            self._draw_boss_video()
        elif self.state == "boss_return_transition":
            self._draw_boss_return_transition()
        elif self.state == "boss_epilogue_transition":
            self._draw_boss_epilogue_transition()
        elif self.state == "defeat_transition":
            self._draw_defeat_transition()
        elif self.state == "playing":
            self._draw_playing()
        elif self.state == "paused":
            self._draw_paused()
        else:
            self._draw_gameover()
        self._draw_screen_fade()

    def _draw_boss_intro_transition(self) -> None:
        self._draw_playing()
        progress = min(
            1.0,
            self.boss_transition_elapsed / self.boss_transition_duration,
        )
        eased = progress * progress * (3.0 - 2.0 * progress)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, round(255 * eased)))
        self.screen.blit(overlay, (0, 0))

    def _draw_boss_video(self) -> None:
        if self.boss_video is not None and self.boss_video.surface is not None:
            self.screen.blit(self.boss_video.surface, (0, 0))
        else:
            self.screen.fill((0, 0, 0))

    def _draw_boss_return_transition(self) -> None:
        midpoint = self.story_transition_duration / 2.0
        if self.session.boss is None:
            self._draw_boss_video()
            fade = min(1.0, self.boss_transition_elapsed / midpoint)
        else:
            self._draw_playing()
            fade = max(
                0.0,
                1.0
                - (self.boss_transition_elapsed - midpoint) / midpoint,
            )
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, round(255 * fade)))
        self.screen.blit(overlay, (0, 0))

    def _draw_boss_epilogue_background(self) -> None:
        if self.boss_epilogue_background is not None:
            self.screen.blit(self.boss_epilogue_background, (0, 0))
        else:
            self.screen.fill((6, 7, 12))

    def _draw_boss_epilogue_transition(self) -> None:
        midpoint = self.boss_epilogue_duration / 2.0
        if self.boss_epilogue_scene_ready:
            self._draw_boss_epilogue_background()
            fade = max(
                0.0,
                1.0
                - (self.boss_epilogue_elapsed - midpoint) / midpoint,
            )
        else:
            self._draw_playing()
            fade = min(1.0, self.boss_epilogue_elapsed / midpoint)
        eased = fade * fade * (3.0 - 2.0 * fade)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, round(255 * eased)))
        self.screen.blit(overlay, (0, 0))

    def _draw_defeat_background(self) -> None:
        if self.defeat_background is not None:
            self.screen.blit(self.defeat_background, (0, 0))
        else:
            self.screen.fill((8, 7, 14))

    def _draw_defeat_transition(self) -> None:
        midpoint = self.defeat_transition_duration / 2.0
        if self.defeat_scene_ready:
            self._draw_defeat_background()
            fade = max(
                0.0,
                1.0
                - (self.defeat_transition_elapsed - midpoint) / midpoint,
            )
        else:
            self._draw_playing()
            fade = min(1.0, self.defeat_transition_elapsed / midpoint)
        eased = fade * fade * (3.0 - 2.0 * fade)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, round(255 * eased)))
        self.screen.blit(overlay, (0, 0))

    def _draw_menu_background(self) -> None:
        if self.menu_background is not None:
            self.screen.blit(self.menu_background, (0, 0))
        else:
            self.screen.fill(BG)
            self._draw_background()
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((4, 5, 12, 72))
        self.screen.blit(shade, (0, 0))

    def _draw_menu(self) -> None:
        self._draw_menu_background()
        progress = min(
            1.0,
            self.menu_reveal_elapsed / self.menu_reveal_duration,
        )
        eased = progress * progress * (3.0 - 2.0 * progress)
        controls = max(0.0, min(1.0, (eased - 0.28) / 0.72))
        self._draw_menu_button(self.start_button, controls)
        self._draw_menu_button(self.settings_button, controls)
        black = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        black.fill((0, 0, 0, round(255 * (1.0 - eased))))
        self.screen.blit(black, (0, 0))

    def _draw_menu_button(self, button: Button, alpha_scale: float = 1.0) -> None:
        hovered = button.rect.collidepoint(pygame.mouse.get_pos())
        lift = 3 if hovered else 0
        rect = button.rect.move(0, -lift)
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            layer,
            (10, 12, 24, round(205 * alpha_scale)),
            layer.get_rect(),
            border_radius=14,
        )
        border = GOLD if hovered else (178, 183, 202)
        pygame.draw.rect(
            layer,
            (*border, round((225 if hovered else 125) * alpha_scale)),
            layer.get_rect(),
            2,
            border_radius=14,
        )
        label = self.font.render(button.text, True, WHITE)
        label.set_alpha(round(255 * alpha_scale))
        layer.blit(label, label.get_rect(center=layer.get_rect().center))
        self.screen.blit(layer, rect)

    def _draw_settings(self) -> None:
        self._draw_menu_background()
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 82))
        self.screen.blit(veil, (0, 0))
        panel = pygame.Surface((520, 480), pygame.SRCALPHA)
        pygame.draw.rect(
            panel,
            (8, 10, 20, 226),
            panel.get_rect(),
            border_radius=22,
        )
        pygame.draw.rect(
            panel,
            (*GOLD, 115),
            panel.get_rect(),
            2,
            border_radius=22,
        )
        self.screen.blit(panel, panel.get_rect(center=(WIDTH // 2, 365)))
        title = self.font_large.render("SETTINGS", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 180)))
        self._draw_volume_slider(
            "BACKGROUND MUSIC",
            self.bgm_slider_rect,
            self.bgm_volume,
        )
        self._draw_volume_slider(
            "SOUND EFFECTS",
            self.sfx_slider_rect,
            self.sfx_volume,
        )
        self._draw_menu_button(self.settings_back_button)

    def _draw_volume_slider(
        self,
        label: str,
        rect: pygame.Rect,
        value: float,
    ) -> None:
        text = self.font.render(label, True, WHITE)
        self.screen.blit(text, (rect.left, rect.top - 48))
        value_text = self.font_small.render(
            f"{round(value * 100)}%",
            True,
            MUTED,
        )
        self.screen.blit(
            value_text,
            value_text.get_rect(bottomright=(rect.right, rect.top - 13)),
        )
        pygame.draw.rect(
            self.screen,
            (40, 43, 58),
            rect,
            border_radius=6,
        )
        fill = rect.copy()
        fill.width = round(rect.width * value)
        if fill.width > 0:
            pygame.draw.rect(self.screen, GOLD, fill, border_radius=6)
        knob = (rect.left + round(rect.width * value), rect.centery)
        pygame.draw.circle(self.screen, (15, 17, 28), knob, 13)
        pygame.draw.circle(self.screen, GOLD, knob, 9)

    def _draw_screen_fade(self) -> None:
        if self.screen_transition_target is None:
            return
        midpoint = self.screen_transition_duration / 2.0
        if self.screen_transition_elapsed <= midpoint:
            progress = self.screen_transition_elapsed / midpoint
        else:
            progress = (
                self.screen_transition_duration - self.screen_transition_elapsed
            ) / midpoint
        eased = max(0.0, min(1.0, progress))
        eased = eased * eased * (3.0 - 2.0 * eased)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, round(255 * eased)))
        self.screen.blit(overlay, (0, 0))

    def _draw_story(self) -> None:
        if self.story_video is not None and self.story_video.surface is not None:
            self.screen.blit(self.story_video.surface, (0, 0))
        elif self.story_background is not None:
            self.screen.blit(self.story_background, (0, 0))
        else:
            self.screen.fill(BG)
            self._draw_background()
        if not self.story_dialogue_active:
            return

        progress = min(
            1.0,
            self.story_dialogue_elapsed / self.story_dialogue_fade_duration,
        )
        smooth = progress * progress * (3.0 - 2.0 * progress)
        visibility = 1.0 - smooth if self.story_dialogue_phase == "fade_out" else smooth
        if self.story_dialogue_phase == "hold":
            visibility = 1.0
        text_alpha = round(255 * visibility)
        panel_visibility = (
            visibility
            if self.story_dialogue_index == 0
            and self.story_dialogue_phase == "fade_in"
            else 1.0
        )
        panel_alpha = round(255 * panel_visibility)
        panel = pygame.Surface((WIDTH - 150, 148), pygame.SRCALPHA)
        pygame.draw.rect(
            panel,
            (7, 9, 18, round(panel_alpha * 0.88)),
            panel.get_rect(),
            border_radius=18,
        )
        pygame.draw.rect(
            panel,
            (171, 190, 214, round(panel_alpha * 0.42)),
            panel.get_rect(),
            2,
            border_radius=18,
        )
        pygame.draw.rect(
            panel,
            (*GOLD, round(panel_alpha * 0.9)),
            pygame.Rect(0, 0, 6, panel.get_height()),
            border_top_left_radius=18,
            border_bottom_left_radius=18,
        )
        speaker = self.font_small.render("PETER", True, GOLD)
        speaker.set_alpha(panel_alpha)
        panel.blit(speaker, (34, 19))
        pygame.draw.line(
            panel,
            (171, 190, 214, round(panel_alpha * 0.3)),
            (34, 49),
            (panel.get_width() - 34, 49),
            1,
        )
        line = self.story_dialogue_lines[self.story_dialogue_index]
        text_x = 34
        text_y = 66
        for index, character in enumerate(line):
            character_surface = self.dialogue_font.render(
                character,
                True,
                WHITE,
            )
            if self.story_dialogue_phase == "fade_in":
                character_progress = 0.0
            elif self.story_dialogue_phase == "typing":
                character_progress = max(
                    0.0,
                    min(
                        1.0,
                        (
                            self.story_dialogue_typing_elapsed
                            - index * self.story_dialogue_character_delay
                        )
                        / self.story_dialogue_character_rise_duration,
                    ),
                )
            else:
                character_progress = 1.0
            character_eased = 1.0 - (1.0 - character_progress) ** 3
            character_surface.set_alpha(round(text_alpha * character_eased))
            rise = round((1.0 - character_eased) * 10)
            panel.blit(character_surface, (text_x, text_y + rise))
            text_x += character_surface.get_width()
        prompt = self.font_small.render("CLICK / ENTER", True, MUTED)
        prompt_progress = (
            min(
                1.0,
                self.story_prompt_elapsed / self.story_prompt_fade_duration,
            )
            if self.story_dialogue_phase == "hold"
            else 0.0
        )
        prompt_eased = 1.0 - (1.0 - prompt_progress) ** 3
        prompt_alpha = round(text_alpha * 0.78 * prompt_eased)
        prompt.set_alpha(prompt_alpha)
        prompt_rect = prompt.get_rect(
            bottomright=(panel.get_width() - 28, 128)
        )
        prompt_rect.y += round((1.0 - prompt_eased) * 6)
        panel.blit(
            prompt,
            prompt_rect,
        )
        panel.set_alpha(panel_alpha)
        y_offset = round((1.0 - panel_visibility) * 8)
        self.screen.blit(panel, (75, HEIGHT - 178 + y_offset))

    def _draw_story_transition(self) -> None:
        midpoint = self.story_transition_duration / 2.0
        if self.story_game_ready:
            self._draw_playing()
            fade = max(
                0.0,
                1.0
                - (self.story_transition_elapsed - midpoint) / midpoint,
            )
        else:
            self._draw_story()
            fade = min(1.0, self.story_transition_elapsed / midpoint)
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, round(255 * fade)))
        self.screen.blit(overlay, (0, 0))

    def _draw_tutorial(self) -> None:
        if self.tutorial_video.surface is not None:
            self.screen.blit(self.tutorial_video.surface, (0, 0))
        else:
            self.screen.fill(BG)
            self._draw_background()
        if not self.tutorial_video.ended:
            return

        progress = min(
            1.0,
            self.tutorial_reveal_elapsed / self.tutorial_reveal_duration,
        )
        eased = progress * progress * progress * (
            progress * (progress * 6.0 - 15.0) + 10.0
        )
        alpha = round(255 * eased)
        self._draw_tutorial_target(alpha)
        self._draw_tutorial_grid(eased, alpha)
        if self.tutorial_success_active:
            self._draw_tutorial_success()

    def _draw_tutorial_success(self) -> None:
        progress = min(
            1.0,
            self.tutorial_success_elapsed / self.tutorial_success_duration,
        )
        eased = 1.0 - (1.0 - progress) ** 3
        fade = (
            progress / 0.28
            if progress < 0.28
            else max(0.0, (1.0 - progress) / 0.72)
        )
        alpha = round(255 * min(1.0, fade))
        gap = round(32 + eased * 125)
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self._draw_pattern_on_surface(
            layer,
            self.tutorial_pattern,
            GRID_CENTER,
            gap,
            (*GOLD, alpha),
            9,
        )
        glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(
            glow,
            (*GOLD, alpha // 8),
            GRID_CENTER,
            round(70 + eased * 180),
        )
        self.screen.blit(glow, (0, 0))
        self.screen.blit(layer, (0, 0))

    def _draw_tutorial_target(self, alpha: int) -> None:
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        center = (WIDTH // 2, 145)
        card = pygame.Rect(center[0] - 78, center[1] - 42, 156, 84)
        pygame.draw.rect(layer, (10, 12, 24, alpha // 2), card, border_radius=12)
        pygame.draw.rect(layer, (*PATTERN_COLOR, alpha // 2), card, 2, border_radius=12)
        nodes = [
            (
                center[0] + (index % 3 - 1) * 25,
                center[1] + (index // 3 - 1) * 25,
            )
            for index in range(9)
        ]
        for first, second in zip(
            self.tutorial_pattern, self.tutorial_pattern[1:]
        ):
            pygame.draw.line(
                layer,
                (*PATTERN_COLOR, alpha),
                nodes[first],
                nodes[second],
                7,
            )
        for node in self.tutorial_pattern:
            pygame.draw.circle(
                layer, (*PATTERN_COLOR, alpha), nodes[node], 5
            )
        self.screen.blit(layer, (0, 0))

    def _draw_tutorial_grid(self, eased: float, alpha: int) -> None:
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        positions = [
            (
                GRID_CENTER[0] + (position[0] - GRID_CENTER[0]) * eased,
                GRID_CENTER[1] + (position[1] - GRID_CENTER[1]) * eased,
            )
            for position in self.node_positions
        ]
        selected = self.pattern_input.nodes
        for first, second in zip(selected, selected[1:]):
            self._draw_neon_line(
                layer, positions[first], positions[second], alpha
            )
        if self.pattern_input.dragging and selected:
            start = positions[selected[-1]]
            mouse = pygame.mouse.get_pos()
            dx = mouse[0] - start[0]
            dy = mouse[1] - start[1]
            distance = math.hypot(dx, dy)
            end = (
                (
                    start[0] + dx / distance * GRID_GAP,
                    start[1] + dy / distance * GRID_GAP,
                )
                if distance > GRID_GAP
                else mouse
            )
            self._draw_neon_line(layer, start, end, min(alpha, 190))
        for index, position in enumerate(positions):
            active = index in selected
            pygame.draw.circle(
                layer, (13, 15, 28, alpha // 4), position, NODE_RADIUS + 8
            )
            pygame.draw.circle(
                layer,
                (*CYAN, alpha) if active else (180, 184, 205, alpha // 2),
                position,
                NODE_RADIUS,
                4,
            )
            if active:
                pygame.draw.circle(layer, (*CYAN, alpha), position, 7)
        self.screen.blit(layer, (0, 0))

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
        self._draw_stage_background()
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
        self._draw_stage_background()
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

    def _draw_stage_background(self) -> None:
        if self.stage_background is not None:
            self.screen.blit(self.stage_background, (0, 0))
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((8, 8, 18, 58))
            self.screen.blit(shade, (0, 0))
        else:
            self.screen.fill(BG)
            self._draw_background()

    def _draw_world(self) -> None:
        if self.player_attack_timer > 0 and self.player_attack_image is not None:
            frame = self.player_attack_image
            rect = frame.get_rect(center=PLAYER_POSITION)
            self.screen.blit(frame, rect)
        elif self.player_images:
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
        if self.session.boss is not None:
            self._draw_piton(self.session.boss)

        self._draw_large_grid()

    def _draw_piton(self, boss: PitonBoss) -> None:
        alpha = boss.alpha
        if alpha <= 0:
            return
        x = round(boss.x)
        y = round(boss.y + math.sin(boss.pulse * 1.3) * 3)
        aura = pygame.Surface((230, 230), pygame.SRCALPHA)
        pygame.draw.circle(aura, (124, 68, 184, alpha // 5), (115, 115), 108)
        pygame.draw.circle(aura, (205, 146, 255, alpha // 2), (115, 115), 94, 3)
        self.screen.blit(aura, aura.get_rect(center=(x, y)))
        state = (
            "defeated"
            if boss.defeated
            else "attacked"
            if boss.is_hit_reacting or boss.knockback_active
            else "idle"
        )
        source_image = self.piton_images.get(state)
        if source_image is not None:
            image = source_image.copy()
            image.set_alpha(alpha)
            self.screen.blit(image, image.get_rect(center=(x, y)))
        else:
            pygame.draw.circle(self.screen, (90, 48, 125), (x, y), boss.radius)
        name = self.font.render(
            f"PITON  SEAL {boss.row_number}/3",
            True,
            (226, 195, 255),
        )
        name.set_alpha(alpha)
        self.screen.blit(name, name.get_rect(center=(x, y - 122)))
        self._draw_piton_patterns(boss, (x, y - 82), alpha)

    def _draw_piton_patterns(
        self,
        boss: PitonBoss,
        center: tuple[int, int],
        opacity: int,
    ) -> None:
        slot_width = 54
        count = len(boss.patterns)
        total_width = max(1, count) * slot_width
        start_x = max(
            24,
            min(WIDTH - total_width - 24, center[0] - total_width // 2),
        )
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        card = pygame.Rect(start_x - 8, center[1] - 29, total_width + 16, 58)
        pygame.draw.rect(layer, (10, 8, 22, 205), card, border_radius=9)
        pygame.draw.rect(layer, (160, 112, 210, 155), card, 2, border_radius=9)
        for index, pattern in enumerate(boss.patterns):
            pattern_center = (
                start_x + index * slot_width + slot_width // 2,
                center[1],
            )
            frame = pygame.Rect(
                pattern_center[0] - 20,
                pattern_center[1] - 20,
                40,
                40,
            )
            color = (120, 84, 145) if index in boss.sealed_slots else PATTERN_COLOR
            pygame.draw.rect(layer, (*color, 145), frame, 2, border_radius=5)
            self._draw_pattern_on_surface(
                layer,
                pattern,
                pattern_center,
                11,
                (*color, opacity),
                5,
            )
        for first, last in self._contiguous_ranges(boss.sealed_slots):
            seal_rect = pygame.Rect(
                start_x + first * slot_width + 2,
                center[1] - 25,
                (last - first + 1) * slot_width - 4,
                50,
            )
            pygame.draw.rect(
                layer,
                (91, 32, 118, 88),
                seal_rect,
                border_radius=7,
            )
            pygame.draw.rect(
                layer,
                (226, 107, 255, 235),
                seal_rect,
                3,
                border_radius=7,
            )
            pygame.draw.line(
                layer,
                (226, 107, 255, 210),
                seal_rect.topleft,
                seal_rect.bottomright,
                2,
            )
            pygame.draw.line(
                layer,
                (226, 107, 255, 210),
                seal_rect.topright,
                seal_rect.bottomleft,
                2,
            )
        layer.set_alpha(opacity)
        self.screen.blit(layer, (0, 0))

    def _contiguous_ranges(
        self,
        indices: set[int],
    ) -> list[tuple[int, int]]:
        if not indices:
            return []
        ordered = sorted(indices)
        ranges: list[tuple[int, int]] = []
        start = previous = ordered[0]
        for index in ordered[1:]:
            if index == previous + 1:
                previous = index
                continue
            ranges.append((start, previous))
            start = previous = index
        ranges.append((start, previous))
        return ranges

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
        if self.session.boss_battle and self.session.boss is not None:
            wave_text = f"PITON  ROW {self.session.boss.row_number}/3"
        else:
            wave_text = (
                f"STAGE {self.session.stage}  WAVE {self.session.wave}"
            )
        wave = self.font.render(wave_text, True, GOLD)
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
            spell_seal_remaining = (
                self.session.boss.spell_seal_remaining(spell.spell_type)
                if self.session.boss is not None
                and self.session.boss_battle
                else 0.0
            )
            spell_is_sealed = spell_seal_remaining > 0
            spell_color = (
                RED
                if spell_is_sealed
                else GOLD
                if self.session.spells.can_cast(spell)
                else MUTED
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
            if spell_is_sealed:
                sealed = self.font_small.render(
                    f"SEALED {spell_seal_remaining:.1f}s",
                    True,
                    RED,
                )
                self.screen.blit(
                    sealed,
                    sealed.get_rect(
                        center=(panel_rect.x + 245, row_y + 79)
                    ),
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
        intro_progress = min(
            1.0,
            self.grid_intro_elapsed / self.grid_intro_duration,
        )
        intro_eased = (
            intro_progress
            * intro_progress
            * intro_progress
            * (
                intro_progress
                * (intro_progress * 6.0 - 15.0)
                + 10.0
            )
        )
        intro_alpha = round(255 * intro_eased)
        display_positions = [
            (
                GRID_CENTER[0] + (position[0] - GRID_CENTER[0]) * intro_eased,
                GRID_CENTER[1] + (position[1] - GRID_CENTER[1]) * intro_eased,
            )
            for position in self.node_positions
        ]
        for first, second in zip(self.pending_shift_pattern, self.pending_shift_pattern[1:]):
            self._draw_neon_line(
                layer,
                display_positions[first],
                display_positions[second],
                190,
                GOLD,
            )
        for node in self.pending_shift_pattern:
            pygame.draw.circle(layer, (*GOLD, 220), display_positions[node], 8)
        line_color = GOLD if self.input_shift_layer and not self.input_shift_cancelled else CYAN
        for first, second in zip(selected, selected[1:]):
            self._draw_neon_line(
                layer,
                display_positions[first],
                display_positions[second],
                255,
                line_color,
            )
        if dragging and selected:
            start = display_positions[selected[-1]]
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

        for index, position in enumerate(display_positions):
            active = index in selected
            base_alpha = round((125 if dragging else 38) * intro_alpha / 255)
            border_alpha = round((220 if dragging else 82) * intro_alpha / 255)
            pygame.draw.circle(
                layer, (18, 17, 38, base_alpha), position, NODE_RADIUS + 8
            )
            pygame.draw.circle(
                layer,
                (*line_color, intro_alpha)
                if active
                else (132, 125, 166, border_alpha),
                position,
                NODE_RADIUS,
                4,
            )
            if active:
                pygame.draw.circle(
                    layer,
                    (*line_color, round(235 * intro_alpha / 255)),
                    position,
                    7,
                )
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
        self._draw_defeat_background()
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((9, 7, 22, 112))
        self.screen.blit(overlay, (0, 0))
        title = self.font_title.render("GAME OVER", True, RED)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 170)))
        score = self.font_large.render(
            f"FINAL SCORE  {self.session.score}", True, WHITE
        )
        self.screen.blit(score, score.get_rect(center=(WIDTH // 2, 285)))
        wave = self.font.render(f"Reached wave {self.session.wave}", True, MUTED)
        self.screen.blit(wave, wave.get_rect(center=(WIDTH // 2, 335)))
        self.retry_button.draw(self.screen, self.font)


def main() -> None:
    game = ExorcismGame()
    game.run()


if __name__ == "__main__":
    main()
