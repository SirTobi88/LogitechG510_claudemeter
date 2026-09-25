# Claude usage on the Logitech G510 LCD

Shows your Claude Code session (5h) and weekly (7d) usage on the built-in
monochrome LCD of a Logitech G510 keyboard, and refreshes it every minute.

```
Claude Usage
Sess  45%  rst 2h00
Week  28%  rst 5d0h
allowed
```

Inspired by [Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter), an
ESP32 desk display for the same data. This project is independent: it shares
no code with Clawdmeter and only relies on the publicly observable
`anthropic-ratelimit-unified-*` response headers.

## How it works

1. Reads the Claude Code OAuth token from `~/.claude/.credentials.json`
   (or `$CLAUDE_CONFIG_DIR`). It never refreshes the token itself; Claude Code
   owns that. If the login has expired, run `claude login`.
2. Sends a 1-token Haiku request and reads utilization from the response headers.
3. Draws 4 text lines on the LCD through the Logitech LCD SDK
   (`LogitechLcd.dll`, part of Logitech Gaming Software).

## Requirements

- Windows, Python 3.11+
- **Logitech Gaming Software (LGS)** installed and running. G HUB does not
  support the G510.
- Claude Code with an active subscription login

## Setup

```powershell
python -m venv g510\.venv
g510\.venv\Scripts\pip install -r g510\requirements.txt
g510\.venv\Scripts\python g510\daemon.py
```

Autostart at login (per user, no admin needed; `-Remove` undoes it):

```powershell
powershell -ExecutionPolicy Bypass -File g510\autostart.ps1
```

Logs: `%LOCALAPPDATA%\ClaudeG510\g510.log`

## Layout

| File | Purpose |
| --- | --- |
| `g510/lcd_sdk.py` | ctypes bindings for `LogitechLcd.dll` (finds it under the LGS install dir; LGS does not put it on `PATH`) |
| `g510/claude_api.py` | token lookup + rate-limit polling |
| `g510/render.py` | usage payload to 4 LCD lines (pure function) |
| `g510/daemon.py` | poll loop |
| `g510/autostart.ps1` | login autostart via `HKCU\...\Run` |

## Troubleshooting

- `LogitechLcd.dll could not be loaded`: LGS is not installed, or the DLL
  bitness does not match your Python (both `x64` and `x86` builds exist under
  `C:\Program Files\Logitech Gaming Software\SDK\LCD\`; the matching one is
  picked automatically).
- LCD shows "No data / run claude login": token missing or expired.
  `claude --version` does not refresh it; run `claude login`.

## Limitations

- Not tested on enterprise/overage accounts (the headers differ; the display
  keeps its last values in that case).
- Not affiliated with Anthropic or Logitech.

## License

MIT, see [LICENSE](LICENSE).
