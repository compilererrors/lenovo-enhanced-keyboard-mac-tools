from __future__ import annotations

import json
import platform
import re
import selectors
import shutil
import subprocess
import time
from collections.abc import Iterator

from .models import KeyMapping


class MacCommandError(RuntimeError):
    pass


def is_macos() -> bool:
    return platform.system() == "Darwin"


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise MacCommandError(
            f"Command failed ({proc.returncode}): {' '.join(args)}\n{proc.stderr.strip()}"
        )
    return proc


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_usage_pair(line: str) -> tuple[int, int] | None:
    page_match = re.search(
        r"(?:usage\s*page|usagePage)\s*(?:[:=]\s*|\s+)(0x[0-9a-fA-F]+|\d+)",
        line,
        flags=re.IGNORECASE,
    )
    usage_match = re.search(
        r"(?:^|[\s,])usage\s*(?:[:=]\s*|\s+)(0x[0-9a-fA-F]+|\d+)",
        line,
        flags=re.IGNORECASE,
    )
    if not page_match or not usage_match:
        return None
    return (parse_int(page_match.group(1)), parse_int(usage_match.group(1)))


def monitor_keyboard(raw: bool = False) -> Iterator[str | tuple[int, int]]:
    args = ["hidutil", "eventmonitor", "--keyboard"]
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:
        raise MacCommandError("Could not open hidutil output stream")
    observed_lines: list[str] = []
    observed_any_output = False
    try:
        for line in proc.stdout:
            observed_any_output = True
            line = line.rstrip("\n")
            if raw:
                yield line
                continue
            pair = parse_usage_pair(line)
            if pair:
                yield pair
            elif line:
                observed_lines.append(line)
                if len(observed_lines) > 20:
                    observed_lines.pop(0)
        exit_code = proc.wait(timeout=0.2)
        if exit_code != 0:
            tail = "\n".join(observed_lines[-5:]) if observed_lines else "(no output)"
            raise MacCommandError(
                f"hidutil eventmonitor exited with code {exit_code}.\n{tail}"
            )
        if not observed_any_output:
            raise MacCommandError(
                "hidutil eventmonitor ended without output. "
                "Check Input Monitoring permission for your terminal and test with --raw."
            )
    finally:
        if proc.poll() is None:
            proc.terminate()


def capture_one_key(timeout_seconds: float = 15.0) -> tuple[int, int]:
    args = ["hidutil", "eventmonitor", "--keyboard"]
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:
        raise MacCommandError("Could not open hidutil output stream")

    observed_lines: list[str] = []
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MacCommandError(
                    f"Timed out after {timeout_seconds:.0f}s waiting for key press."
                )

            ready = selector.select(timeout=remaining)
            if not ready:
                continue

            line = proc.stdout.readline()
            if line == "":
                break
            line = line.rstrip("\n")
            pair = parse_usage_pair(line)
            if pair:
                return pair
            if line:
                observed_lines.append(line)
                if len(observed_lines) > 20:
                    observed_lines.pop(0)

        exit_code = proc.wait(timeout=0.2)
        if exit_code != 0:
            tail = "\n".join(observed_lines[-5:]) if observed_lines else "(no output)"
            raise MacCommandError(
                f"hidutil eventmonitor exited with code {exit_code}.\n{tail}"
            )
        raise MacCommandError("No key event captured.")
    finally:
        selector.close()
        if proc.poll() is None:
            proc.terminate()


def hidutil_get_user_key_mapping() -> list[dict]:
    proc = run_command(["hidutil", "property", "--get", "UserKeyMapping"], check=False)
    out = proc.stdout.strip()
    if not out or out == "(null)":
        return []

    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        start = out.find("{")
        end = out.rfind("}")
        if start < 0 or end <= start:
            return []
        payload = json.loads(out[start : end + 1])

    return list(payload.get("UserKeyMapping", []))


def hidutil_set_mappings(mappings: list[KeyMapping]) -> None:
    payload = {"UserKeyMapping": [m.to_hidutil_record() for m in mappings]}
    run_command(["hidutil", "property", "--set", json.dumps(payload)])


def hidutil_clear_mappings() -> None:
    run_command(["hidutil", "property", "--set", '{"UserKeyMapping":[]}'])


def keyboard_lines_from_ioreg() -> list[str]:
    proc = run_command(["ioreg", "-p", "IOUSB", "-l", "-w0"], check=False)
    lines = []
    for line in proc.stdout.splitlines():
        lower = line.lower()
        if "diagnostics" in lower:
            continue
        if "keyboard" not in lower and "lenovo" not in lower:
            continue
        if (
            '"usb product name"' in lower
            or '"kusbproductstring"' in lower
            or "+-o " in lower
        ):
            lines.append(line.strip())
    return lines
