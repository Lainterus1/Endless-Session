"""Токены текущей темы; только чтение, с проверкой контраста."""
from pathlib import Path
import re
import subprocess
import tomllib

DEFAULT = dict(foreground="#cacccc", background="#101315", accent="#cacccc", fontFamily="monospace")


def rgb(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value): raise ValueError("color")
    return [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]


def luminance(value):
    values = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb(value)]
    return sum(c * w for c, w in zip(values, (0.2126, 0.7152, 0.0722)))


def contrast(a, b):
    x, y = sorted((luminance(a), luminance(b)))
    return (y + 0.05) / (x + 0.05)


class Theme:
    def __init__(self, home=Path.home()):
        self.path = home / ".local/state/omarchy/current/theme/colors.toml"
        self.font_path = home / ".config/fontconfig/fonts.conf"
        self.font_signature = None
        self.font = "monospace"

    def read(self):
        result = dict(DEFAULT)
        data = {}
        try:
            data = tomllib.loads(self.path.read_text())
            fg, bg = data["foreground"], data["background"]
            if contrast(fg, bg) >= 4.5: result.update(foreground=fg, background=bg)
        except (OSError, ValueError, KeyError, TypeError): pass
        result["accent"] = result["foreground"]
        try:
            accent = data.get("accent", data.get("color4", result["foreground"]))
            if contrast(accent, result["background"]) >= 4.5: result["accent"] = accent
        except (ValueError, TypeError): pass
        try:
            stat = self.font_path.stat(); signature = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        except OSError: signature = ("missing",)
        if signature != self.font_signature:
            self.font_signature = signature
            try:
                value = subprocess.run(["fc-match", "-f", "%{family[0]}", "monospace"], capture_output=True, text=True, timeout=2)
                self.font = value.stdout.strip() if value.returncode == 0 and value.stdout.strip() else "monospace"
            except (OSError, subprocess.SubprocessError): self.font = "monospace"
        result["fontFamily"] = self.font
        return result
