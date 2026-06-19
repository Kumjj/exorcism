"""Asset loading helpers for Exocism.

This module groups the file-loading logic (fonts, images, sounds) that used to
live as private methods on ``ExorcismGame``.  Every loader is stateless apart
from the target screen size, so they are gathered into a small ``AssetLoader``
that resolves files relative to the game directory.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pygame


ASSET_DIR = Path(__file__).resolve().parent


class AssetLoader:
    """Loads fonts, images, and sounds from the game directory."""

    def __init__(self, screen_size: tuple[int, int]) -> None:
        self.screen_width, self.screen_height = screen_size

    def _path(self, filename: str) -> Path:
        return ASSET_DIR / filename

    def korean_font_path(self) -> str | None:
        candidates = (
            ASSET_DIR / "NotoSansKR-VF.ttf",
            ASSET_DIR / "malgun.ttf",
            Path("/mnt/c/Windows/Fonts/NotoSansKR-VF.ttf"),
            Path("/mnt/c/Windows/Fonts/malgun.ttf"),
            Path("/mnt/c/Windows/Fonts/gulim.ttc"),
            Path("/mnt/c/Windows/Fonts/GOTHIC.TTF"),
        )
        for path in candidates:
            if path.exists():
                return str(path)
        return (
            pygame.font.match_font("malgungothic")
            or pygame.font.match_font("nanumgothic")
            or pygame.font.match_font("notosanscjkkr")
        )

    def load_sound(self, filename: str) -> pygame.mixer.Sound | None:
        sound_path = self._path(filename)
        if not sound_path.exists():
            return None
        try:
            return pygame.mixer.Sound(str(sound_path))
        except pygame.error:
            return None

    def load_video_sound(self, video_path: Path) -> pygame.mixer.Sound | None:
        return self.load_audio_sound(video_path)

    def load_audio_sound(
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

    def load_player_images(self) -> list[pygame.Surface]:
        frames = [
            image
            for index in range(1, 4)
            if (image := self.load_scaled_image(f"peter_idle{index}.png", 145))
            is not None
        ]
        fallback = self.load_scaled_image("exorcism_MC.png", 145)
        return frames or ([fallback] if fallback is not None else [])

    def load_scaled_image(self, filename: str, width: int) -> pygame.Surface | None:
        image_path = self._path(filename)
        if not image_path.exists():
            return None
        image = pygame.image.load(image_path).convert_alpha()
        height = round(image.get_height() * width / image.get_width())
        return pygame.transform.smoothscale(image, (width, height))

    def load_cover_image(self, filename: str) -> pygame.Surface | None:
        image_path = self._path(filename)
        if not image_path.exists():
            return None
        image = pygame.image.load(image_path).convert()
        scale = max(
            self.screen_width / image.get_width(),
            self.screen_height / image.get_height(),
        )
        size = (
            round(image.get_width() * scale),
            round(image.get_height() * scale),
        )
        scaled = pygame.transform.smoothscale(image, size)
        source = pygame.Rect(
            (scaled.get_width() - self.screen_width) // 2,
            (scaled.get_height() - self.screen_height) // 2,
            self.screen_width,
            self.screen_height,
        )
        return scaled.subsurface(source).copy()

    def load_ghost_images(self) -> dict[object, dict[str, pygame.Surface]]:
        images: dict[object, dict[str, pygame.Surface]] = {}
        for variant in (1, 2):
            variant_images: dict[str, pygame.Surface] = {}
            for state in ("idle", "attacked", "defeated"):
                image = self.load_scaled_image(f"slow{variant}_{state}.png", 96)
                if image is not None:
                    variant_images[state] = image
            if variant_images:
                images[variant] = variant_images
        for name in ("creep", "crease", "snarl"):
            variant_images = {}
            for state in ("idle", "attacked", "defeated"):
                image = self.load_scaled_image(f"{name}_{state}.png", 96)
                if image is not None:
                    variant_images[state] = image
            if variant_images:
                images[name] = variant_images
        return images

    def grayscale_surface(self, source: pygame.Surface) -> pygame.Surface:
        gray = source.copy()
        width, height = gray.get_size()
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = gray.get_at((x, y))
                value = round((red * 0.299 + green * 0.587 + blue * 0.114) * 0.62)
                gray.set_at((x, y), (value, value, value, alpha))
        return gray
