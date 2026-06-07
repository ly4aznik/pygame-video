# Boss Bouncing Ball Arena

Autonomous deterministic vertical Pygame simulation for a 30-second Reels video.

```powershell
python boss_bouncing_ball_arena/main.py --seed 42
python boss_bouncing_ball_arena/main.py --seed 42 --minions 16 --record
```

The game renders at 360x640 and `window_recorder.py` exports a 1080x1920,
30 FPS MP4 under `boss_bouncing_ball_arena/window_recordings`.

Controls: `R` restarts with the same seed. Close the window to stop.
