# Hex Territory Reel

Autonomous hex-grid territory battle. The match runs for up to 27 seconds and
ends earlier after 1.5 seconds without any captures, then holds the winner
table for 3 seconds.

## Run

```powershell
.venv\Scripts\python.exe ai_hex_territory\main.py
```

Controls: `R` new seeded battle, `SPACE` pause, `S` screenshot, `ESC` quit.

## Record 1080x1920 MP4 with ffmpeg

```powershell
.venv\Scripts\python.exe ai_hex_territory\main.py --record-window
```

Recordings are written to `ai_hex_territory/window_recordings/`. Event sounds
are captured through the configured DirectShow loopback device. Override it
with `--record-audio-source`.

## Variations

```powershell
.venv\Scripts\python.exe ai_hex_territory\main.py `
  --seed 9 --cols 18 --rows 25 --factions 4 `
  --style directional --center-weight 2.0 --neutral-density 0.05 `
  --speeds 0.95,1.12,1.08,1.15 --starts 1:1,16:23,1:23,16:1
```

Growth styles: `flood`, `directional`, `probabilistic`.
