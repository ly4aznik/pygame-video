from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys

import pygame


class RecordingUnavailable(RuntimeError):
    pass


def find_ffmpeg() -> str:
    candidates = [
        os.environ.get("FFMPEG_PATH"),
        shutil.which("ffmpeg"),
        Path("ffmpeg.exe"),
        Path("tools") / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RecordingUnavailable(
        "ffmpeg.exe not found. Install FFmpeg, add it to PATH, or set FFMPEG_PATH."
    )


def windows_process_options() -> dict:
    if sys.platform != "win32":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


def detect_hardware_encoder(ffmpeg: str, size: tuple[int, int], fps: int) -> tuple[str, list[str]]:
    candidates = [
        (
            "h264_nvenc",
            ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "20", "-b:v", "0"],
        ),
        (
            "h264_amf",
            ["-c:v", "h264_amf", "-quality", "balanced", "-usage", "transcoding", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"],
        ),
    ]
    for name, arguments in candidates:
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=s={size[0]}x{size[1]}:r={fps}:d=0.2",
            *arguments, "-f", "null", "-",
        ]
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **windows_process_options(),
        )
        if result.returncode == 0:
            return name, arguments
    raise RecordingUnavailable("No working NVIDIA NVENC or AMD AMF encoder found.")


class FrameRecorder:
    def __init__(self, size: tuple[int, int], fps: int, audio, output_dir: str | Path) -> None:
        self.size = size
        self.fps = fps
        self.audio = audio
        self.frames_written = 0
        self.sound_events: list[tuple[int, str]] = []
        self.music_offset = audio.music_position()
        self.ffmpeg = find_ffmpeg()
        self.encoder_name, encoder_arguments = detect_hardware_encoder(self.ffmpeg, size, fps)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        stem = output_dir / f"light-snakes_{timestamp}"
        self.output_path = stem.with_suffix(".mp4")
        self.video_path = stem.with_suffix(".video.mp4")
        self.audio_path = stem.with_suffix(".audio.wav")
        self.log_path = stem.with_suffix(".ffmpeg.log")
        self._log = self.log_path.open("w", encoding="utf-8")

        width, height = size
        command = [
            self.ffmpeg, "-y", "-hide_banner",
            "-f", "rawvideo", "-pixel_format", "rgb24",
            "-video_size", f"{width}x{height}", "-framerate", str(fps),
            "-i", "pipe:0", "-an",
            "-vf", "scale=1080:1920:flags=lanczos",
            *encoder_arguments,
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(self.video_path),
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._log,
                **windows_process_options(),
            )
        except OSError as error:
            self._log.close()
            raise RecordingUnavailable(f"Could not start FFmpeg: {error}") from error

    def write_frame(self, surface: pygame.Surface) -> None:
        if self._process.stdin is None:
            return
        try:
            self._process.stdin.write(pygame.image.tobytes(surface, "RGB"))
        except (BrokenPipeError, OSError) as error:
            raise RecordingUnavailable(
                f"FFmpeg stopped while encoding with {self.encoder_name}. See {self.log_path}."
            ) from error
        self.frames_written += 1

    def record_sound(self, name: str) -> None:
        self.sound_events.append((self.frames_written, name))

    def close(self) -> Path:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            self._process.stdin = None
        return_code = self._process.wait()
        self._log.close()
        if return_code:
            raise RecordingUnavailable(
                f"FFmpeg could not encode with {self.encoder_name}. See {self.log_path}."
            )

        self.audio.write_recording_audio(
            self.audio_path,
            self.frames_written,
            self.fps,
            self.music_offset,
            self.sound_events,
        )
        command = [
            self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(self.video_path), "-i", str(self.audio_path),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-shortest", str(self.output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, **windows_process_options())
        if result.returncode:
            raise RecordingUnavailable(f"FFmpeg could not mux recording: {result.stderr.strip()}")
        self.video_path.unlink(missing_ok=True)
        self.audio_path.unlink(missing_ok=True)
        self.log_path.unlink(missing_ok=True)
        return self.output_path

    def abort(self) -> None:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            self._process.stdin = None
        self._process.wait()
        if not self._log.closed:
            self._log.close()
