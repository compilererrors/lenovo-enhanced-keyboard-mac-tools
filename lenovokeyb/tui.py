from __future__ import annotations

import curses
from pathlib import Path

from .config import load_mappings, save_mappings
from .macos import (
    MacCommandError,
    capture_one_key,
    command_exists,
    hidutil_set_mappings,
    is_macos,
)
from .models import KeyMapping


DEST_PRESETS: list[tuple[str, int, int]] = [
    ("F13", 0x07, 0x68),
    ("F14", 0x07, 0x69),
    ("F15", 0x07, 0x6A),
    ("F16", 0x07, 0x6B),
    ("F17", 0x07, 0x6C),
    ("F18", 0x07, 0x6D),
    ("F19", 0x07, 0x6E),
]


class MappingTUI:
    def __init__(self, config_path: Path | None) -> None:
        self.config_path = config_path
        self.mappings = load_mappings(config_path)
        self.selected = 0
        self.status = ""
        self.status_level = "info"
        self.dirty = False

    def _clip(self, text: str, width: int) -> str:
        if width <= 0:
            return ""
        if len(text) <= width:
            return text
        if width <= 3:
            return text[:width]
        return text[: width - 3] + "..."

    def _safe_addstr(self, stdscr: curses.window, row: int, col: int, text: str, attr: int = 0) -> None:
        height, width = stdscr.getmaxyx()
        if row < 0 or row >= height or col >= width:
            return
        clipped = self._clip(text, width - col - 1)
        if not clipped:
            return
        stdscr.addstr(row, col, clipped, attr)

    def _set_status(self, text: str, level: str = "info") -> None:
        self.status = text
        self.status_level = level

    def _usage_str(self, usage_page: int, usage: int) -> str:
        return f"0x{usage_page:X}/0x{usage:X}"

    def _mapping_line(self, index: int, mapping: KeyMapping, width: int) -> str:
        src = self._usage_str(mapping.src_page, mapping.src_usage)
        dst = self._usage_str(mapping.dst_page, mapping.dst_usage)
        label_width = max(0, width - 4 - 16 - 16 - 4)
        label = self._clip(mapping.label, label_width)
        return f"{index:>2}  {src:<16} {dst:<16} {label}"

    def _status_attr(self) -> int:
        if not curses.has_colors():
            return curses.A_DIM
        if self.status_level == "ok":
            return curses.color_pair(4) | curses.A_BOLD
        if self.status_level == "error":
            return curses.color_pair(5) | curses.A_BOLD
        return curses.color_pair(3)

    def _init_colors(self) -> None:
        if not curses.has_colors():
            return
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)   # header
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)  # selected row
        curses.init_pair(3, curses.COLOR_WHITE, -1)  # info
        curses.init_pair(4, curses.COLOR_GREEN, -1)  # success
        curses.init_pair(5, curses.COLOR_RED, -1)    # error

    def _draw(self, stdscr: curses.window) -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()

        if height < 12 or width < 72:
            self._safe_addstr(stdscr, 0, 0, "Terminal too small for TUI. Increase window size.", curses.A_BOLD)
            self._safe_addstr(stdscr, 1, 0, "Minimum ~72x12.")
            self._safe_addstr(stdscr, height - 1, 0, "q:quit")
            stdscr.refresh()
            return

        header_attr = curses.color_pair(1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD
        dirty_suffix = " *unsaved" if self.dirty else ""
        self._safe_addstr(
            stdscr,
            0,
            0,
            f"Lenovo Enhanced Keyboard Mapper{dirty_suffix}",
            header_attr,
        )
        self._safe_addstr(stdscr, 1, 0, f"Config: {self.config_path or '(default)'}")
        self._safe_addstr(
            stdscr,
            2,
            0,
            "c:capture  a:add  e:edit  d:delete  s:save  p:apply  j/k:move  q:quit",
            curses.A_DIM,
        )

        sidebar = width >= 110
        left_width = width if not sidebar else int(width * 0.66)

        self._safe_addstr(stdscr, 4, 0, "#   Source           Destination      Label", curses.A_BOLD)
        self._safe_addstr(stdscr, 5, 0, "-" * max(10, left_width - 1), curses.A_DIM)
        list_top = 6
        list_bottom = height - 3
        visible_rows = max(0, list_bottom - list_top)
        start = 0
        if self.selected >= visible_rows and visible_rows > 0:
            start = self.selected - visible_rows + 1

        for view_idx, mapping_idx in enumerate(range(start, min(start + visible_rows, len(self.mappings)))):
            mapping = self.mappings[mapping_idx]
            row = list_top + view_idx
            line = self._mapping_line(mapping_idx + 1, mapping, left_width)
            if mapping_idx == self.selected:
                attr = curses.color_pair(2) | curses.A_BOLD if curses.has_colors() else curses.A_REVERSE
            else:
                attr = curses.A_NORMAL
            self._safe_addstr(stdscr, row, 0, line, attr)

        if not self.mappings:
            self._safe_addstr(stdscr, list_top, 0, "No mappings yet. Press 'c' to capture first key.")

        if sidebar:
            divider_x = left_width
            for row in range(4, height - 2):
                self._safe_addstr(stdscr, row, divider_x, "|", curses.A_DIM)
            panel_x = divider_x + 2
            panel_width = width - panel_x - 1
            self._safe_addstr(stdscr, 4, panel_x, "Selected", curses.A_BOLD)
            self._safe_addstr(stdscr, 5, panel_x, "-" * max(8, panel_width - 1), curses.A_DIM)

            row = 6
            if self.mappings:
                selected = self.mappings[self.selected]
                details = [
                    f"Index: {self.selected + 1}/{len(self.mappings)}",
                    f"Source: {self._usage_str(selected.src_page, selected.src_usage)}",
                    f"Dest:   {self._usage_str(selected.dst_page, selected.dst_usage)}",
                    f"Label:  {selected.label or '(none)'}",
                ]
                for line in details:
                    self._safe_addstr(stdscr, row, panel_x, line)
                    row += 1
            else:
                self._safe_addstr(stdscr, row, panel_x, "No row selected")
                row += 1

            row += 1
            self._safe_addstr(stdscr, row, panel_x, "Destination presets", curses.A_BOLD)
            row += 1
            for idx, (name, page, usage) in enumerate(DEST_PRESETS, start=1):
                self._safe_addstr(
                    stdscr,
                    row,
                    panel_x,
                    f"{idx}. {name:<3} -> {self._usage_str(page, usage)}",
                    curses.A_DIM,
                )
                row += 1

            row += 1
            self._safe_addstr(stdscr, row, panel_x, "Flow", curses.A_BOLD)
            row += 1
            self._safe_addstr(stdscr, row, panel_x, "1) c  capture source key", curses.A_DIM)
            row += 1
            self._safe_addstr(stdscr, row, panel_x, "2) choose destination", curses.A_DIM)
            row += 1
            self._safe_addstr(stdscr, row, panel_x, "3) s save, p apply", curses.A_DIM)

        self._safe_addstr(stdscr, height - 1, 0, self.status, self._status_attr())
        stdscr.refresh()

    def _prompt(self, stdscr: curses.window, prompt: str) -> str:
        height, width = stdscr.getmaxyx()
        curses.echo()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        try:
            stdscr.move(height - 1, 0)
            stdscr.clrtoeol()
            self._safe_addstr(stdscr, height - 1, 0, prompt, curses.A_BOLD)
            stdscr.refresh()
            value = stdscr.getstr(height - 1, min(len(prompt), max(0, width - 1))).decode("utf-8")
            return value.strip()
        finally:
            curses.noecho()
            try:
                curses.curs_set(0)
            except curses.error:
                pass

    def _prompt_int(self, stdscr: curses.window, prompt: str, default: int | None = None) -> int:
        default_text = f" [{hex(default)}]" if default is not None else ""
        raw = self._prompt(stdscr, f"{prompt}{default_text}: ")
        if raw == "" and default is not None:
            return default
        return int(raw, 0)

    def _confirm(self, stdscr: curses.window, prompt: str, default_yes: bool = False) -> bool:
        suffix = "[Y/n]" if default_yes else "[y/N]"
        raw = self._prompt(stdscr, f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default_yes
        return raw in {"y", "yes"}

    def _pick_destination(self, stdscr: curses.window) -> tuple[int, int, str] | None:
        choice = self._prompt(
            stdscr,
            "Destination 1:F13 2:F14 3:F15 4:F16 5:F17 6:F18 7:F19 c:custom q:cancel",
        ).strip().lower()
        if choice in {"q", "quit", "cancel"}:
            return None
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(DEST_PRESETS):
                name, page, usage = DEST_PRESETS[index]
                return page, usage, name
        if choice in {"c", "custom"}:
            try:
                page = self._prompt_int(stdscr, "dst page", default=0x07)
                usage = self._prompt_int(stdscr, "dst usage")
            except ValueError:
                self._set_status("Invalid destination value; use decimal or 0xHEX.", "error")
                return None
            return page, usage, ""
        self._set_status("Unknown destination option.", "error")
        return None

    def _create_mapping_from_source(self, stdscr: curses.window, src_page: int, src_usage: int) -> None:
        picked = self._pick_destination(stdscr)
        if not picked:
            self._set_status("Mapping canceled.")
            return
        dst_page, dst_usage, preset_label = picked
        label_hint = f"{preset_label}" if preset_label else ""
        label = self._prompt(stdscr, f"label (optional) [{label_hint}]")
        if not label:
            label = label_hint

        self.mappings.append(KeyMapping(src_page, src_usage, dst_page, dst_usage, label))
        self.selected = max(0, len(self.mappings) - 1)
        self.dirty = True
        self._set_status("Mapping added.", "ok")

    def _add_mapping(self, stdscr: curses.window) -> None:
        try:
            src_page = self._prompt_int(stdscr, "src page", default=0x0C)
            src_usage = self._prompt_int(stdscr, "src usage")
        except ValueError:
            self._set_status("Invalid source value; use decimal or 0xHEX.", "error")
            return

        self._create_mapping_from_source(stdscr, src_page, src_usage)

    def _capture_and_add(self, stdscr: curses.window) -> None:
        if not is_macos():
            self._set_status("Capture works only on macOS.", "error")
            return
        if not command_exists("hidutil"):
            self._set_status("hidutil not found.", "error")
            return

        self._set_status("Capture active: press one key now...")
        self._draw(stdscr)
        try:
            src_page, src_usage = capture_one_key(timeout_seconds=15.0)
        except MacCommandError as e:
            self._set_status(str(e).splitlines()[0], "error")
            return

        self._set_status(f"Captured {self._usage_str(src_page, src_usage)}", "ok")
        if not self._confirm(stdscr, "Create mapping from captured key?", default_yes=True):
            self._set_status("Capture completed (no mapping created).")
            return

        self._create_mapping_from_source(stdscr, src_page, src_usage)

    def _edit_selected(self, stdscr: curses.window) -> None:
        if not self.mappings:
            self._set_status("No mapping selected.", "error")
            return
        current = self.mappings[self.selected]
        try:
            src_page = self._prompt_int(stdscr, "src page", default=current.src_page)
            src_usage = self._prompt_int(stdscr, "src usage", default=current.src_usage)
        except ValueError:
            self._set_status("Invalid source value; use decimal or 0xHEX.", "error")
            return

        use_picker = self._confirm(stdscr, "Pick destination from presets/custom?", default_yes=True)
        if use_picker:
            picked = self._pick_destination(stdscr)
            if not picked:
                self._set_status("Edit canceled.")
                return
            dst_page, dst_usage, preset_label = picked
            default_label = current.label or preset_label
        else:
            try:
                dst_page = self._prompt_int(stdscr, "dst page", default=current.dst_page)
                dst_usage = self._prompt_int(stdscr, "dst usage", default=current.dst_usage)
            except ValueError:
                self._set_status("Invalid destination value; use decimal or 0xHEX.", "error")
                return
            default_label = current.label

        label = self._prompt(stdscr, f"label [{default_label}]")
        if not label:
            label = default_label

        self.mappings[self.selected] = KeyMapping(src_page, src_usage, dst_page, dst_usage, label)
        self.dirty = True
        self._set_status("Mapping updated.", "ok")

    def _delete_selected(self) -> None:
        if not self.mappings:
            self._set_status("Nothing to delete.", "error")
            return
        self.mappings.pop(self.selected)
        if self.selected >= len(self.mappings):
            self.selected = max(0, len(self.mappings) - 1)
        self.dirty = True
        self._set_status("Mapping removed.", "ok")

    def _save(self) -> None:
        path = save_mappings(self.mappings, self.config_path)
        self.dirty = False
        self._set_status(f"Saved: {path}", "ok")

    def _apply(self) -> None:
        if not is_macos():
            self._set_status("Apply works only on macOS.", "error")
            return
        try:
            hidutil_set_mappings(self.mappings)
            self._set_status("Mappings applied via hidutil.", "ok")
        except MacCommandError as e:
            self._set_status(str(e).splitlines()[0], "error")

    def run(self, stdscr: curses.window) -> None:
        self._init_colors()
        curses.curs_set(0)
        stdscr.nodelay(False)
        while True:
            self._draw(stdscr)
            key = stdscr.getch()
            if key in (ord("q"), 27):
                if self.dirty and not self._confirm(stdscr, "Unsaved changes. Quit anyway?"):
                    self._set_status("Quit canceled.")
                    continue
                break
            if key in (curses.KEY_UP, ord("k")) and self.selected > 0:
                self.selected -= 1
            elif key in (curses.KEY_DOWN, ord("j")) and self.selected < len(self.mappings) - 1:
                self.selected += 1
            elif key == ord("c"):
                self._capture_and_add(stdscr)
            elif key == ord("a"):
                self._add_mapping(stdscr)
            elif key == ord("e"):
                self._edit_selected(stdscr)
            elif key == ord("d"):
                if self._confirm(stdscr, "Delete selected mapping?"):
                    self._delete_selected()
                else:
                    self._set_status("Delete canceled.")
            elif key == ord("s"):
                self._save()
            elif key == ord("p"):
                self._apply()


def run_tui(config_path: Path | None) -> None:
    app = MappingTUI(config_path=config_path)
    curses.wrapper(app.run)
