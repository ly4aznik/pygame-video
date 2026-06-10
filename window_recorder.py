import os
import queue
import shutil
import subprocess
import threading
import time
from typing import IO, List, Optional, Tuple


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
        capture_audio: bool = False,
        audio_source: str = "",
        audio_backend: str = "dshow",
        audio_volume: float = 1.0,
        pipe_video: bool = False,
        final_speed: float = 1.0,
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
        self.capture_audio_requested = capture_audio
        self.capture_audio = capture_audio
        self.audio_source = audio_source
        self.audio_backend = audio_backend.lower().strip() or "dshow"
        self.audio_volume = max(0.0, min(2.0, audio_volume))
        self.pipe_video = pipe_video
        self.final_speed = max(0.25, min(4.0, final_speed))

        self.match_index = 0
        self.process: Optional[subprocess.Popen] = None
        self.log_file: Optional[IO[str]] = None
        self.video_path = ""
        self.capture_path = ""
        self.video_with_music_path = ""
        self.log_path = ""
        self.start_pending = False
        self.finished = False
        self.next_frame_time = 0.0
        self.frame_queue: Optional[queue.Queue[Optional[bytes]]] = None
        self.frame_writer: Optional[threading.Thread] = None
        self.video_encoder = "libx264"

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
            self._stop_frame_writer()
            self.process = None
            self._close_log()
            self.finished = True
            if return_code == 0:
                self.finish_recording()
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
        if self.capture_audio:
            self.audio_source = self.resolve_audio_source(ffmpeg)
            self.capture_audio = bool(self.audio_source) and self.ffmpeg_supports_device(ffmpeg, self.audio_backend)
            if not self.capture_audio and self.audio_backend == "wasapi":
                fallback_source = self.resolve_dshow_audio_source(ffmpeg)
                if fallback_source and self.ffmpeg_supports_device(ffmpeg, "dshow"):
                    print(f"WASAPI loopback unavailable; using DirectShow audio '{fallback_source}'.")
                    self.audio_backend = "dshow"
                    self.audio_source = fallback_source
                    self.capture_audio = True
        self.video_encoder = self.select_video_encoder(ffmpeg)

        self._prepare_session()
        command = [ffmpeg, "-y", "-thread_queue_size", "512"]
        if self.pipe_video:
            command.extend(
                [
                    "-f",
                    "rawvideo",
                    "-pixel_format",
                    "rgb24",
                    "-video_size",
                    f"{self.capture_size[0]}x{self.capture_size[1]}",
                    "-framerate",
                    str(self.fps),
                    "-i",
                    "pipe:0",
                ]
            )
        else:
            command.extend(
                [
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
                ]
            )
        if self.capture_audio:
            if self.audio_backend == "wasapi":
                command.extend(
                    [
                        "-thread_queue_size",
                        "512",
                        "-f",
                        "wasapi",
                        "-loopback",
                        "1",
                        "-i",
                        self.audio_source,
                    ]
                )
            else:
                command.extend(
                    [
                        "-thread_queue_size",
                        "512",
                        "-f",
                        "dshow",
                        "-i",
                        f"audio={self.audio_source}",
                    ]
                )
            command.extend(
                [
                    "-filter_complex",
                    (
                        f"[0:v]setpts=PTS-STARTPTS,fps={self.fps},"
                        "setsar=1,format=yuv420p[v];"
                        f"[1:a]asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0,"
                        f"volume={self.audio_volume}[a]"
                    ),
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                ]
            )
        else:
            command.extend(
                [
                    "-vf",
                    f"fps={self.fps},setsar=1,format=yuv420p",
                ]
            )
        command.extend(self.encoder_args(self.video_encoder, fast=True))
        command.extend(
            [
                "-fps_mode",
                "cfr",
                "-tag:v",
                "avc1",
                "-pix_fmt",
                "yuv420p",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-colorspace",
                "bt709",
                *(
                    [
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                    ]
                    if self.capture_audio
                    else []
                ),
                "-movflags",
                "+faststart",
                *(
                    [
                        "-shortest",
                    ]
                    if self.pipe_video and self.capture_audio
                    else []
                ),
                self.capture_path,
            ]
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=self.log_file,
                stderr=self.log_file,
                creationflags=creationflags,
            )
            self.next_frame_time = time.perf_counter()
            if self.pipe_video:
                self.frame_queue = queue.Queue(maxsize=max(30, self.fps * 4))
                self.frame_writer = threading.Thread(target=self._frame_writer_loop, daemon=True)
                self.frame_writer.start()
            print(f"Window recording started: {self.capture_path}")
            print(f"Video encoder: {self.video_encoder}")
            print(
                f"Live capture {self.capture_size[0]}x{self.capture_size[1]}; "
                f"final output {self.output_size[0]}x{self.output_size[1]}"
            )
            if self.capture_audio:
                if self.audio_backend == "wasapi":
                    print(f"Live audio capture enabled: wasapi loopback '{self.audio_source}'")
                else:
                    print(f"Live audio capture enabled: dshow audio='{self.audio_source}'")
            elif self.capture_audio_requested:
                print(f"Live audio capture disabled: ffmpeg cannot open {self.audio_backend} audio '{self.audio_source}'.")
        except OSError as exc:
            print(f"Could not start ffmpeg window recording: {exc}")
            self._close_log()
            self.finished = True

    def write_video_frame(self, rgb_frame: bytes) -> None:
        if not self.needs_video_frame():
            return
        now = time.perf_counter()
        frame_interval = 1.0 / self.fps
        frames_due = max(1, int((now - self.next_frame_time) / frame_interval) + 1)
        frames_due = min(frames_due, self.fps)
        queued = 0
        if self.frame_queue:
            for _ in range(frames_due):
                try:
                    self.frame_queue.put_nowait(rgb_frame)
                    queued += 1
                except queue.Full:
                    break
        self.next_frame_time += queued * frame_interval

    def needs_video_frame(self) -> bool:
        return bool(
            self.pipe_video
            and self.process
            and self.process.poll() is None
            and time.perf_counter() >= self.next_frame_time
        )

    def _frame_writer_loop(self) -> None:
        while self.frame_queue:
            frame = self.frame_queue.get()
            if frame is None:
                return
            try:
                if self.process and self.process.stdin:
                    self.process.stdin.write(frame)
                    self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                return

    def _stop_frame_writer(self) -> None:
        if not self.frame_queue or not self.frame_writer:
            return
        while True:
            try:
                self.frame_queue.put_nowait(None)
                break
            except queue.Full:
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    break
        self.frame_writer.join(timeout=5)
        self.frame_queue = None
        self.frame_writer = None

    def resolve_audio_source(self, ffmpeg: str) -> str:
        if self.audio_source and self.audio_source.lower() != "auto":
            return self.audio_source
        if self.audio_backend == "wasapi":
            return "default"
        return self.resolve_dshow_audio_source(ffmpeg)

    def resolve_dshow_audio_source(self, ffmpeg: str) -> str:
        devices = self.list_dshow_audio_devices(ffmpeg)
        if not devices:
            return ""
        preferred = [
            "virtual-audio-capturer",
            "stereo mix",
            "what u hear",
            "cable output",
            "vb-audio",
            "voicemeeter",
            "wave out mix",
            "loopback",
            "speakers",
            "output",
        ]
        for needle in preferred:
            for device in devices:
                if needle in device.lower():
                    return device
        print("DirectShow audio devices found, but none look like system-audio loopback:")
        for device in devices:
            print(f"  {device}")
        return ""

    def list_dshow_audio_devices(self, ffmpeg: str) -> List[str]:
        command = [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            return []
        devices = []
        for line in (result.stderr + result.stdout).splitlines():
            if "(audio)" not in line:
                continue
            first = line.find('"')
            second = line.find('"', first + 1)
            if first >= 0 and second > first:
                devices.append(line[first + 1 : second])
        return devices

    def ffmpeg_supports_device(self, ffmpeg: str, device_name: str) -> bool:
        try:
            result = subprocess.run([ffmpeg, "-hide_banner", "-devices"], capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            return False
        needle = f" {device_name}"
        return any(needle in line for line in (result.stdout + result.stderr).splitlines())

    def select_video_encoder(self, ffmpeg: str) -> str:
        try:
            result = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=8)
            encoders = result.stdout + result.stderr
        except (OSError, subprocess.TimeoutExpired):
            return "libx264"
        for encoder in ("h264_nvenc", "h264_amf", "h264_qsv", "libx264"):
            if encoder in encoders:
                return encoder
        return "libx264"

    def encoder_args(self, encoder: str, *, fast: bool) -> List[str]:
        if encoder == "h264_nvenc":
            return ["-c:v", encoder, "-preset", "p1" if fast else "p4", "-rc", "vbr", "-cq", "22" if fast else "20", "-b:v", "0"]
        if encoder == "h264_amf":
            return ["-c:v", encoder, "-quality", "speed" if fast else "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"]
        if encoder == "h264_qsv":
            return ["-c:v", encoder, "-preset", "veryfast" if fast else "medium", "-global_quality", "22" if fast else "20"]
        return [
            "-c:v",
            "libx264",
            "-profile:v",
            "baseline",
            "-level:v",
            "4.0",
            "-preset",
            "ultrafast" if fast else "veryfast",
            "-crf",
            "22" if fast else "20",
        ]

    def stop(self) -> None:
        process = self.process
        if not process:
            self._stop_frame_writer()
            self._close_log()
            return

        if process.poll() is None:
            try:
                self._stop_frame_writer()
                if process.stdin:
                    if not self.pipe_video:
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
            self.finish_recording()
        else:
            print(f"Window recording stopped with ffmpeg code {return_code}. Log: {self.log_path}")

    def finish_recording(self) -> None:
        if not self.resize_recording():
            print(f"Raw window recording saved: {self.capture_path}")
            return
        print(f"Window recording saved: {self.video_path}")
        self.add_music()

    def resize_recording(self) -> bool:
        if self.capture_path == self.video_path:
            return True

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            print("ffmpeg not found. Cannot create final-size recording.")
            return False

        video_filter = (
            "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
            f"scale={self.output_size[0]}:{self.output_size[1]}:"
            "force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
            f"pad={self.output_size[0]}:{self.output_size[1]}:"
            "(ow-iw)/2:(oh-ih)/2:color=black,"
            "fps=30,setsar=1,format=yuv420p"
        )
        if self.final_speed != 1.0:
            video_filter = f"setpts=PTS/{self.final_speed}," + video_filter

        command = [
            ffmpeg,
            "-y",
            "-i",
            self.capture_path,
            "-vf",
            video_filter,
            *self.encoder_args(self.video_encoder, fast=False),
            "-tag:v",
            "avc1",
            "-pix_fmt",
            "yuv420p",
            *(
                ["-filter:a", f"atempo={self.final_speed}", "-c:a", "aac", "-b:a", "192k"]
                if self.capture_audio and self.final_speed != 1.0
                else ["-c:a", "copy"]
            ),
            "-movflags",
            "+faststart",
            self.video_path,
        ]
        print("Creating final-size recording...")
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            print("Could not create final-size recording.")
            print(result.stderr[-1200:])
            return False
        try:
            os.remove(self.capture_path)
        except OSError:
            pass
        return True

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
        capture_name = f"_live_{self.video_filename}"
        self.capture_path = (
            os.path.join(session_dir, capture_name)
            if self.capture_size != self.output_size
            else self.video_path
        )
        self.video_with_music_path = os.path.join(session_dir, self.music_filename)
        self.log_path = os.path.join(session_dir, "ffmpeg.log")
        self.log_file = open(self.log_path, "w", encoding="utf-8")

    def _close_log(self) -> None:
        if self.log_file:
            self.log_file.close()
            self.log_file = None
