# The Gap Is Too Small

Autonomous vertical physics simulation for short-form video.

```powershell
python too_small_gap/main.py
python too_small_gap/main.py --record --seed 17
python too_small_gap/main.py --gap 25 --rotation 0.8 --rings 5 --gravity 130 --bounce 0.92
```

The `--record` option records through the shared `window_recorder.py` and writes a
1080x1920 MP4 under `too_small_gap/window_recordings`.

Controls: `R` restarts with the same seed. Close the window to stop.
