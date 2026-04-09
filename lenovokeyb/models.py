from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KeyMapping:
    src_page: int
    src_usage: int
    dst_page: int
    dst_usage: int
    label: str = ""

    def to_dict(self) -> dict[str, int | str]:
        return {
            "src_page": self.src_page,
            "src_usage": self.src_usage,
            "dst_page": self.dst_page,
            "dst_usage": self.dst_usage,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeyMapping":
        return cls(
            src_page=int(data["src_page"]),
            src_usage=int(data["src_usage"]),
            dst_page=int(data["dst_page"]),
            dst_usage=int(data["dst_usage"]),
            label=str(data.get("label", "")),
        )

    @staticmethod
    def to_hid_usage(usage_page: int, usage: int) -> int:
        return (usage_page << 32) | usage

    def to_hidutil_record(self) -> dict[str, int]:
        return {
            "HIDKeyboardModifierMappingSrc": self.to_hid_usage(self.src_page, self.src_usage),
            "HIDKeyboardModifierMappingDst": self.to_hid_usage(self.dst_page, self.dst_usage),
        }

    def short(self) -> str:
        prefix = f"{self.label}: " if self.label else ""
        return (
            f"{prefix}0x{self.src_page:X}/0x{self.src_usage:X} -> "
            f"0x{self.dst_page:X}/0x{self.dst_usage:X}"
        )

