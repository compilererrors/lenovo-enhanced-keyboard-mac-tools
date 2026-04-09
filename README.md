# lenovo-enhanced-keyboard-mac-tools

CLI + TUI for reverse engineering and remapping Lenovo Enhanced Performance USB Keyboard hotkeys on macOS.

## What this does

- Monitors key events from `hidutil` so you can identify unknown hotkeys.
- Stores mappings in a local JSON profile.
- Applies mappings to macOS (`hidutil property --set ...`).
- Lets you edit mappings either from CLI or in a small TUI.

## Install

```bash
python3 -m pip install -e .
```

## Typical workflow

1. Verify environment:

```bash
lenovokeyb doctor
```

2. Reverse engineer a hotkey:

```bash
lenovokeyb monitor --raw
# press key on keyboard, note usagePage + usage values
```

Or capture exactly one key:

```bash
lenovokeyb capture
```

If monitor exits immediately, macOS often blocks input capture for the terminal app.
Enable it in:

`System Settings -> Privacy & Security -> Input Monitoring`

3. Add mapping:

```bash
lenovokeyb add \
  --from-page 0x0C --from-usage 0xB5 \
  --to-page 0x07 --to-usage 0x3A \
  --label "Calculator to F1"
```

4. Review and apply:

```bash
lenovokeyb list
lenovokeyb apply
```

5. Edit interactively:

```bash
lenovokeyb tui
```

TUI keys:

- `c`: capture one key and optionally create mapping
- `a`: add
- `e`: edit selected mapping
- `d`: delete selected mapping
- `j` / `k`: move selection
- `s`: save profile
- `p`: apply via `hidutil`
- `q`: quit

## Config location

Default mapping file:

`~/.config/lenovokeyb/mappings.json`

Override per command with:

```bash
lenovokeyb --config /path/to/mappings.json list
```

## Notes

- `hidutil` mappings are not always persistent across reboots/logouts.
- For persistent startup behavior, run `lenovokeyb apply` at login (for example via LaunchAgent).
- Some vendor-specific keys may not be exposed through `hidutil`. If that happens, combine this with Karabiner-Elements or Hammerspoon.
