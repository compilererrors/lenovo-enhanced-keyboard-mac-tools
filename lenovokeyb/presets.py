from __future__ import annotations

from dataclasses import dataclass

from .models import KeyMapping


@dataclass(frozen=True)
class MappingPreset:
    name: str
    description: str
    mappings: tuple[KeyMapping, ...]


PRESETS: dict[str, MappingPreset] = {
    "lenovo-launch-fkeys": MappingPreset(
        name="lenovo-launch-fkeys",
        description=(
            "Map common Lenovo launch/browser consumer usages to F13-F19 "
            "for flexible macOS shortcuts."
        ),
        mappings=(
            KeyMapping(0x0C, 0x192, 0x07, 0x68, "Calculator -> F13"),
            KeyMapping(0x0C, 0x194, 0x07, 0x69, "MyComputer/LocalBrowser -> F14"),
            KeyMapping(0x0C, 0x18A, 0x07, 0x6A, "Mail -> F15"),
            KeyMapping(0x0C, 0x223, 0x07, 0x6B, "Home/WWW -> F16"),
            KeyMapping(0x0C, 0x22A, 0x07, 0x6C, "Favorites -> F17"),
            KeyMapping(0x0C, 0x224, 0x07, 0x6D, "Back -> F18"),
            KeyMapping(0x0C, 0x225, 0x07, 0x6E, "Forward -> F19"),
        ),
    )
}


def list_presets() -> list[MappingPreset]:
    return [PRESETS[name] for name in sorted(PRESETS)]


def get_preset(name: str) -> MappingPreset:
    preset = PRESETS.get(name)
    if preset is None:
        known = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown preset '{name}'. Available: {known}")
    return preset
