from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_mappings, save_mappings
from .macos import (
    MacCommandError,
    capture_one_key,
    command_exists,
    hidutil_clear_mappings,
    hidutil_get_user_key_mapping,
    hidutil_set_mappings,
    is_macos,
    keyboard_lines_from_ioreg,
    monitor_keyboard,
)
from .models import KeyMapping
from .tui import run_tui


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lenovokeyb",
        description="CLI + TUI mapping tool for Lenovo Enhanced Performance USB Keyboard on macOS",
    )
    parser.add_argument("--config", type=Path, help="Path to mapping file")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check runtime prerequisites and keyboard visibility")

    p_monitor = sub.add_parser("monitor", help="Read keyboard events via hidutil")
    p_monitor.add_argument("--raw", action="store_true", help="Print raw hidutil lines")
    p_capture = sub.add_parser("capture", help="Capture one key press and print code")
    p_capture.add_argument("--timeout", type=int, default=15, help="Seconds to wait")

    sub.add_parser("list", help="List local mappings")
    sub.add_parser("list-applied", help="List mappings currently active in hidutil")

    p_add = sub.add_parser("add", help="Add mapping to local profile")
    p_add.add_argument("--from-page", required=True, type=parse_int)
    p_add.add_argument("--from-usage", required=True, type=parse_int)
    p_add.add_argument("--to-page", required=True, type=parse_int)
    p_add.add_argument("--to-usage", required=True, type=parse_int)
    p_add.add_argument("--label", default="")

    p_remove = sub.add_parser("remove", help="Remove mapping by 1-based index")
    p_remove.add_argument("--index", required=True, type=int)

    sub.add_parser("apply", help="Apply local mappings to macOS with hidutil")
    sub.add_parser("clear", help="Clear active hidutil mappings")
    sub.add_parser("tui", help="Interactive mapping editor")

    return parser.parse_args(argv)


def cmd_doctor() -> int:
    print(f"OS: {'macOS' if is_macos() else 'non-macOS'}")
    print(f"hidutil: {'OK' if command_exists('hidutil') else 'MISSING'}")
    print(f"ioreg: {'OK' if command_exists('ioreg') else 'MISSING'}")

    if command_exists("hidutil"):
        try:
            data = hidutil_get_user_key_mapping()
            print(f"Active hidutil mappings: {len(data)}")
        except Exception as e:  # noqa: BLE001
            print(f"hidutil status error: {e}")

    if command_exists("ioreg"):
        lines = keyboard_lines_from_ioreg()
        print(f"USB lines matching keyboard/lenovo: {len(lines)}")
        for line in lines[:8]:
            print(f"  {line}")
    return 0


def cmd_monitor(raw: bool) -> int:
    if not is_macos():
        print("monitor only works on macOS", file=sys.stderr)
        return 1
    if not command_exists("hidutil"):
        print("hidutil not found", file=sys.stderr)
        return 1

    print("Press keys; Ctrl+C to stop.")
    try:
        for event in monitor_keyboard(raw=raw):
            if raw:
                print(event)
            else:
                if isinstance(event, tuple):
                    page, usage = event
                    print(f"usagePage=0x{page:X} usage=0x{usage:X}")
    except MacCommandError as e:
        print(str(e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


def cmd_capture(timeout: int) -> int:
    if not is_macos():
        print("capture only works on macOS", file=sys.stderr)
        return 1
    if not command_exists("hidutil"):
        print("hidutil not found", file=sys.stderr)
        return 1

    print("Press one key now...")
    try:
        page, usage = capture_one_key(timeout_seconds=float(timeout))
    except MacCommandError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Captured: usagePage=0x{page:X} usage=0x{usage:X}")
    print(
        "Add mapping with: "
        f"lenovokeyb add --from-page 0x{page:X} --from-usage 0x{usage:X} "
        "--to-page 0x07 --to-usage 0x68 --label \"captured\""
    )
    return 0


def cmd_list(config: Path | None) -> int:
    mappings = load_mappings(config)
    if not mappings:
        print("No local mappings.")
        return 0
    for idx, mapping in enumerate(mappings, start=1):
        print(f"{idx:02d}. {mapping.short()}")
    return 0


def cmd_list_applied() -> int:
    if not is_macos():
        print("list-applied only works on macOS", file=sys.stderr)
        return 1
    try:
        data = hidutil_get_user_key_mapping()
    except MacCommandError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(data)
    return 0


def cmd_add(args: argparse.Namespace, config: Path | None) -> int:
    mappings = load_mappings(config)
    mappings.append(
        KeyMapping(
            src_page=args.from_page,
            src_usage=args.from_usage,
            dst_page=args.to_page,
            dst_usage=args.to_usage,
            label=args.label,
        )
    )
    path = save_mappings(mappings, config)
    print(f"Saved {len(mappings)} mappings to {path}")
    return 0


def cmd_remove(index: int, config: Path | None) -> int:
    mappings = load_mappings(config)
    if index < 1 or index > len(mappings):
        print(f"Index out of range: 1..{len(mappings)}", file=sys.stderr)
        return 1
    removed = mappings.pop(index - 1)
    path = save_mappings(mappings, config)
    print(f"Removed: {removed.short()}")
    print(f"Saved: {path}")
    return 0


def cmd_apply(config: Path | None) -> int:
    if not is_macos():
        print("apply only works on macOS", file=sys.stderr)
        return 1
    mappings = load_mappings(config)
    try:
        hidutil_set_mappings(mappings)
    except MacCommandError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Applied {len(mappings)} mapping(s).")
    return 0


def cmd_clear() -> int:
    if not is_macos():
        print("clear only works on macOS", file=sys.stderr)
        return 1
    try:
        hidutil_clear_mappings()
    except MacCommandError as e:
        print(str(e), file=sys.stderr)
        return 1
    print("Cleared active hidutil mappings.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = args.config

    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "monitor":
        return cmd_monitor(raw=args.raw)
    if args.command == "capture":
        return cmd_capture(timeout=args.timeout)
    if args.command == "list":
        return cmd_list(config)
    if args.command == "list-applied":
        return cmd_list_applied()
    if args.command == "add":
        return cmd_add(args, config)
    if args.command == "remove":
        return cmd_remove(args.index, config)
    if args.command == "apply":
        return cmd_apply(config)
    if args.command == "clear":
        return cmd_clear()
    if args.command == "tui":
        run_tui(config)
        return 0

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
