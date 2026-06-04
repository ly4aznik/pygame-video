import os
import shutil
import subprocess
import time
from typing import IO, Optional, Tuple


# Set this before pygame is imported by game modules. It avoids Windows DPI
# scaling captures where the game surface appears in only part of the video.
os.environ.setdefault("SDL_VIDEO_HIGHDPI_DISABLED", "1")


Size = Tuple[int, int]


class WindowRecorder:
    """External ffmpeg window recorder reusable by pygame mini-games."""

    def __init__(
        self,
        *,
        enabled: bool,
        window_title: str,
        output_root: str,
        session_prefix: str,
        video_filename: str,
        music_filename: str,
        fps: int = 30,
        capture_size: Size = (360, 640),
        output_size: Size = (1080, 1920),
        end_delay_seconds: float = 1.0,
        music_path: str = "",
        music_volume: float = 0.25,
        draw_mouse: bool = False,
    ) -> None:
        self.enabled = enabled
        self.window_title = window_title
        self.output_root = os.path.abspath(output_root)
        self.session_prefix = session_prefix
        self.video_filename = video_filename
        self.music_filename = music_filename
        self.fps = max(1, min(60, fps))
        self.capture_size = capture_size
        self.output_size = output_size
        self.end_delay_seconds = max(0.0, end_delay_seconds)
        self.music_path = os.path.abspath(music_path) if music_path else ""
        self.music_volume = max(0.0, min(1.0, music_volume))
        self.draw_mouse = draw_mouse

        self.match_index = 0
        self.process: Optional[subprocess.Popen] = None
        self.log_file: Optional[IO[str]] = None
        self.video_path = ""
        self.video_with_music_path = ""
        self.log_path = ""
        self.start_pending = False
        self.finished = False

    def new_match(self) -> None:
        self.stop()
        self.start_pending = self.enabled
        self.finished = False

    def start_if_pending(self) -> None:
        if not self.start_pending:
            return
        self.start_pending = False
        self.start()

    def monitor(self) -> None:
        if self.process and self.process.poll() is not None:
            return_code = self.process.returncode
            self.process = None
            self._close_log()
            self.finished = True
            if return_code == 0:
                print(f"Window recording saved: {self.video_path}")
                self.add_music()
            else:
                print(f"Window recording process ended with code {return_code}. Log: {self.log_path}")

    def stop_after_game_over(self, elapsed_after_game_over: float) -> None:
        if self.enabled and not self.finished and elapsed_after_game_over >= self.end_delay_seconds:
            self.stop()

    def start(self) -> None:
        if not self.enabled or self.process:
            return
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            print("ffmpeg not found. Window recording is disabled.")
            self.finished = True
            return

        self._prepare_session()
        command = [
            ffmpeg,
            "-y",
            "-f",
            "gdigrab",
            "-draw_mouse",
            "1" if self.draw_mouse else "0",
            "-framerate",
            str(self.fps),
            "-video_size",
            f"{self.capture_size[0]}x{self.capture_size[1]}",
            "-i",
            f"title={self.window_title}",
            "-vf",
            f"scale={self.output_size[0]}:{self.output_size[1]}:flags=lanczos,setsar=1,format=yuv420p",
            "-c:v",
            "libx264",
            "-profile:v",
            "baseline",
            "-level:v",
            "4.0",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-tag:v",
            "avc1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            self.video_path,
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=self.log_file,
                stderr=self.log_file,
                creationflags=creationflags,
            )
            print(f"Window recording started: {self.video_path}")
            print(
                "Capture "
                f"{self.capture_size[0]}x{self.capture_size[1]} -> "
                f"{self.output_size[0]}x{self.output_size[1]}"
            )
        except OSError as exc:
            print(f"Could not start ffmpeg window recording: {exc}")
            self._close_log()
            self.finished = True

    def stop(self) -> None:
        process = self.process
        if not process:
            self._close_log()
            return

        if process.poll() is None:
            try:
                if process.stdin:
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                    process.stdin.close()
                process.wait(timeout=8)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        return_code = process.returncode
        self.process = None
        self._close_log()
        self.finished = True
        if return_code == 0:
            print(f"Window recording saved: {self.video_path}")
            self.add_music()
        else:
            print(f"Window recording stopped with ffmpeg code {return_code}. Log: {self.log_path}")

    def add_music(self) -> None:
        if not self.music_path:
            return
        if not os.path.exists(self.music_path):
            print(f"Music file not found: {self.music_path}")
            return

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            print("ffmpeg not found. Cannot add music.")
            return

        command = [
            ffmpeg,
            "-y",
            "-i",
            self.video_path,
            "-stream_loop",
            "-1",
            "-i",
            self.music_path,
            "-filter:a",
            f"volume={self.music_volume}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            self.video_with_music_path,
        ]
        print("Adding background music...")
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Video with music saved: {self.video_with_music_path}")
        else:
            print("Could not add music. Original video is still saved.")
            print(result.stderr[-1200:])

    def _prepare_session(self) -> None:
        self.match_index += 1
        stamp = time.strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(self.output_root, f"{self.session_prefix}_{stamp}_{self.match_index:02d}")
        os.makedirs(session_dir, exist_ok=True)
        self.video_path = os.path.join(session_dir, self.video_filename)
        self.video_with_music_path = os.path.join(session_dir, self.music_filename)
        self.log_path = os.path.join(session_dir, "ffmpeg.log")
        self.log_file = open(self.log_path, "w", encoding="utf-8")

    def _close_log(self) -> None:
        if self.log_file:
            self.log_file.close()
            self.log_file = None
