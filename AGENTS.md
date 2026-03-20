# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Single-file Python 3 Tkinter desktop application (`main.py`) — a CAN-bus air conditioner controller GUI. No build step; no test suite; no linter config.

### Dependencies

- **System**: `python3-tk` (apt) — required for the Tkinter GUI.
- **Python**: `python-can`, `PyYAML`, `pyserial` — all imported with graceful fallback, but needed for full functionality.

### Running the application

```
python3 main.py
```

- Requires a display server (X11). On headless environments, use `Xvfb` or similar.
- The app expects a `can_messages.yaml` config file (not committed to the repo). A sample is provided at the repo root for development with a `virtual` CAN interface.
- To run without real CAN hardware, set `iface` to `virtual` in the YAML config or select it from the GUI dropdown.

### Key caveats

- **No tests or linter**: The repo has no test files, no `requirements.txt`, and no linting configuration. There is nothing to run for `lint` or `test`.
- **Hardware-dependent CAN**: Full end-to-end operation requires a physical CAN adapter (slcan/socketcan). For development, use the `virtual` interface provided by `python-can`.
- **Missing `can_messages.yaml`**: The app loads CAN message definitions from this YAML file on connect. It is not in the repo; you must supply one. The sample `can_messages.yaml` in the repo root works with the virtual interface.
