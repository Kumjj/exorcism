"""Audio management for Exocism.

This module gathers every piece of sound playback that used to live on
``ExorcismGame``: background music, the looping intro atmosphere, video
soundtracks, and the one-shot combat/voice sound effects.  Keeping it here lets
``main.py`` stay focused on game state and rendering while the mixing details
(channels, per-sound volume scaling, BGM track selection) live in one place.

The game owns a single :class:`AudioManager`.  It tells the manager *what* it
wants to hear (``set_bgm("stage1")``, ``play_sfx("weaver_death")``,
``play_video("story", path)``) and the manager handles the pygame mixer.
"""

from __future__ import annotations

from pathlib import Path
import random

import pygame

from assets import AssetLoader


ASSET_DIR = Path(__file__).resolve().parent

# Music is mixed quieter than effects so dialogue and combat cues stay audible.
BGM_VOLUME_SCALE = 0.45

# Background-music tracks keyed by an abstract "what is happening" name.  Each
# value is a tuple of candidate filenames tried in order, so a missing asset
# falls back gracefully instead of crashing.
BGM_TRACKS: dict[str, tuple[str, ...]] = {
    "title": ("title_bgm.mp3",),
    "gameover": ("Game_over_bgm.mp3",),
    "stage1": ("Pition_bgm.mp3",),
    "stage2": ("Weaver_bgm.mp3",),
    "stage3": ("Veil of Lucien.mp3",),
    "boss1": ("Pition_bgm.mp3",),
    "boss2": ("Weaver_bgm.mp3",),
    "final_boss": ("Veil of Lucien.mp3",),
    "ending": ("ending_bgm.mp3",),
}

# Soundtrack volume for each cutscene video, relative to the SFX volume.
VIDEO_VOLUMES: dict[str, float] = {
    "tutorial": 1.0,
    "story": 0.72,
    "boss": 0.78,
    "stage_end": 0.95,
    "weaver_epilogue": 0.95,
    "stage_three": 0.95,
}

# One-shot sound effects: name -> (filename, volume relative to SFX volume).
SFX_TRACKS: dict[str, tuple[str, float]] = {
    "peter_speak": ("peter_speak.wav", 0.42),
    "luciel_speak": ("luciel_speak.wav", 0.42),
    "ghost_defeated": ("ghost_defeated.mp3", 0.85),
    "attacked": ("attacked.mp3", 0.82),
    "piton_attack": ("piton_attack.mp3", 0.82),
    "piton_death": ("piton_death.mp3", 0.82),
    "weaver_attack": ("weaver_attack.mp3", 0.82),
    "weaver_death": ("weaver_death.mp3", 0.82),
    "weaver_web": ("weaver_web.mp3", 0.82),
    "luciel_disappear": ("luciel_disappear.mp3", 0.82),
    "luciel_magic_attack": ("luciel_magic_attack.mp3", 0.82),
}

# Spoken-line voices keyed by the speaker name used in dialogue scripts.
SPEAK_SFX: dict[str, str] = {
    "PETER": "peter_speak",
    "LUCIEL": "luciel_speak",
}

BOO_FILES = ("boo1.mp3", "boo2.mp3", "boo3.mp3")
BOO_VOLUME = 0.72
MAGIC_SPELL_VOLUME = 1.0
# The looping intro atmosphere is part of the ambience, so it tracks BGM volume.
INTRO_ATMOSPHERE_VOLUME = 0.12


class AudioManager:
    """Owns the pygame mixer state for music, ambience, and sound effects."""

    def __init__(self, assets: AssetLoader) -> None:
        self.assets = assets
        pygame.mixer.set_num_channels(24)
        pygame.mixer.set_reserved(1)

        self.bgm_volume = 1.0
        self.sfx_volume = 1.0
        self.current_bgm_key: str | None = None
        self.current_bgm_path: Path | None = None

        # Cutscene soundtracks.  Sounds for the tutorial and boss intro are
        # pre-loaded because they replay often; the rest are loaded on demand.
        self.video_sounds: dict[str, pygame.mixer.Sound | None] = {
            name: None for name in VIDEO_VOLUMES
        }
        self.video_channels: dict[str, pygame.mixer.Channel | None] = {
            name: None for name in VIDEO_VOLUMES
        }
        self.video_sounds["tutorial"] = self.assets.load_audio_sound(
            self._path("exorcism_sceen1.mp4")
        )
        self.video_sounds["boss"] = self.assets.load_audio_sound(
            self._path("exorcism3.mp4")
        )

        # Looping ambience that plays under the tutorial intro.
        self.intro_atmosphere_sound = self.assets.load_audio_sound(
            self._path("intro_atmosphere.mp3"),
            start_seconds=8.0,
        )
        self.intro_atmosphere_channel: pygame.mixer.Channel | None = None

        # The spell cast cue lives on a reserved channel so it can be retriggered
        # cleanly without fighting for a free channel.
        self.magic_spell_sound = self.assets.load_audio_sound(
            self._path("magic_spell.mp3"),
        )
        self.magic_spell_channel = pygame.mixer.Channel(0)

        self.sfx: dict[str, pygame.mixer.Sound | None] = {
            name: self.assets.load_sound(filename)
            for name, (filename, _volume) in SFX_TRACKS.items()
        }
        self.boo_sounds = [
            sound
            for filename in BOO_FILES
            if (sound := self.assets.load_sound(filename)) is not None
        ]
        # Each spawned ghost gets its own boo channel so it can be silenced when
        # that specific ghost is defeated.
        self.ghost_boo_channels: dict[int, pygame.mixer.Channel] = {}

        self.apply_settings()

    def _path(self, filename: str) -> Path:
        return ASSET_DIR / filename

    # -- Volume --------------------------------------------------------------

    def apply_settings(self) -> None:
        """Re-apply the current BGM/SFX volumes across every active source."""
        pygame.mixer.music.set_volume(BGM_VOLUME_SCALE * self.bgm_volume)
        if self.magic_spell_sound is not None:
            self.magic_spell_sound.set_volume(MAGIC_SPELL_VOLUME * self.sfx_volume)
        if self.intro_atmosphere_channel is not None:
            self.intro_atmosphere_channel.set_volume(
                INTRO_ATMOSPHERE_VOLUME * self.bgm_volume
            )
        for name, (_filename, volume) in SFX_TRACKS.items():
            sound = self.sfx.get(name)
            if sound is not None:
                sound.set_volume(volume * self.sfx_volume)
        for sound in self.boo_sounds:
            sound.set_volume(BOO_VOLUME * self.sfx_volume)
        for name, channel in self.video_channels.items():
            if channel is not None:
                channel.set_volume(VIDEO_VOLUMES[name] * self.sfx_volume)

    def set_bgm_volume(self, value: float) -> None:
        self.bgm_volume = value
        self.apply_settings()

    def set_sfx_volume(self, value: float) -> None:
        self.sfx_volume = value
        self.apply_settings()

    # -- Background music ----------------------------------------------------

    def bgm_path_for_key(self, key: str) -> Path | None:
        for filename in BGM_TRACKS.get(key, ()):
            path = self._path(filename)
            if path.exists():
                return path
        return None

    def set_bgm(self, key: str | None) -> None:
        """Switch background music to ``key`` (``None`` stops the music)."""
        if key is None:
            if self.current_bgm_key is not None:
                self.stop_bgm()
            return
        path = self.bgm_path_for_key(key)
        if path is None:
            if self.current_bgm_key is not None:
                self.stop_bgm()
            return
        if self.current_bgm_key == key and self.current_bgm_path == path:
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(BGM_VOLUME_SCALE * self.bgm_volume)
            pygame.mixer.music.play(loops=-1)
        except pygame.error:
            self.current_bgm_key = None
            self.current_bgm_path = None
            return
        self.current_bgm_key = key
        self.current_bgm_path = path

    def stop_bgm(self) -> None:
        pygame.mixer.music.stop()
        self.current_bgm_key = None
        self.current_bgm_path = None

    # -- Cutscene video soundtracks -----------------------------------------

    def play_video(
        self, name: str, sound: pygame.mixer.Sound | None
    ) -> pygame.mixer.Channel | None:
        """Play ``sound`` as the soundtrack for cutscene ``name``."""
        self.stop_video(name)
        self.video_sounds[name] = sound
        if sound is not None:
            channel = sound.play()
            self.video_channels[name] = channel
            if channel is not None:
                channel.set_volume(VIDEO_VOLUMES[name] * self.sfx_volume)
        return self.video_channels[name]

    def load_video(
        self, name: str, path: Path, **load_kwargs: float
    ) -> pygame.mixer.Channel | None:
        """Load the soundtrack for ``path`` and play it under cutscene ``name``."""
        sound = self.assets.load_audio_sound(path, **load_kwargs)
        return self.play_video(name, sound)

    def replay_video(self, name: str) -> pygame.mixer.Channel | None:
        """Replay a pre-loaded cutscene soundtrack (tutorial, boss intro)."""
        return self.play_video(name, self.video_sounds.get(name))

    def stop_video(self, name: str) -> None:
        channel = self.video_channels.get(name)
        if channel is not None:
            channel.stop()
        self.video_channels[name] = None

    def stop_videos(self, *names: str) -> None:
        """Stop the named cutscene soundtracks, or all of them if none given."""
        for name in names or tuple(self.video_channels):
            self.stop_video(name)

    def clear_video(self, name: str) -> None:
        """Stop and forget a cutscene soundtrack (used when no video plays)."""
        self.stop_video(name)
        self.video_sounds[name] = None

    # -- Intro atmosphere ----------------------------------------------------

    def start_intro_atmosphere(self) -> None:
        if (
            self.intro_atmosphere_sound is not None
            and self.intro_atmosphere_channel is None
        ):
            self.intro_atmosphere_channel = self.intro_atmosphere_sound.play(loops=-1)
            if self.intro_atmosphere_channel is not None:
                self.intro_atmosphere_channel.set_volume(
                    INTRO_ATMOSPHERE_VOLUME * self.bgm_volume
                )

    def stop_intro_atmosphere(self) -> None:
        if self.intro_atmosphere_channel is not None:
            self.intro_atmosphere_channel.stop()
            self.intro_atmosphere_channel = None

    # -- Sound effects -------------------------------------------------------

    def play_sfx(self, name: str | None) -> None:
        sound = self.sfx.get(name) if name is not None else None
        if sound is not None:
            sound.play()

    def play_speak(self, speaker: str) -> None:
        self.play_sfx(SPEAK_SFX.get(speaker))

    def play_magic_spell(self) -> None:
        if self.magic_spell_sound is not None:
            self.magic_spell_channel.play(self.magic_spell_sound)

    def stop_magic_spell(self) -> None:
        if self.magic_spell_channel is not None:
            self.magic_spell_channel.stop()

    # -- Ghost ambience ------------------------------------------------------

    def play_ghost_spawn(self, ghost: object) -> None:
        if not self.boo_sounds:
            return
        channel = random.choice(self.boo_sounds).play()
        if channel is not None:
            self.ghost_boo_channels[id(ghost)] = channel

    def play_ghost_defeated(self, ghost: object) -> None:
        channel = self.ghost_boo_channels.pop(id(ghost), None)
        defeated = self.sfx.get("ghost_defeated")
        if channel is not None:
            channel.stop()
            if defeated is not None:
                channel.play(defeated)
        elif defeated is not None:
            defeated.play()

    def stop_all_ghost_boo(self) -> None:
        for channel in self.ghost_boo_channels.values():
            channel.stop()
        self.ghost_boo_channels.clear()

    def remove_inactive_ghost_boo(self, active_ids: set[int]) -> None:
        for ghost_id, channel in list(self.ghost_boo_channels.items()):
            if ghost_id not in active_ids or not channel.get_busy():
                if ghost_id not in active_ids:
                    channel.stop()
                self.ghost_boo_channels.pop(ghost_id, None)

    # -- Shutdown ------------------------------------------------------------

    def shutdown(self) -> None:
        """Silence every audio source (called on quit)."""
        self.stop_videos()
        self.stop_intro_atmosphere()
        self.stop_bgm()
        self.stop_magic_spell()
        self.stop_all_ghost_boo()
