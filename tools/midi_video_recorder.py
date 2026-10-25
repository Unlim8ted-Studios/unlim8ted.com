"""GUI/offline exporter for the music page's MIDI and audio-reactive visuals.

Setup: python -m pip install -r tools/midi_video_requirements.txt
Run:   python tools/midi_video_recorder.py
Requires ffmpeg and ffprobe on PATH. See docs/midi_video_recorder.md.
"""
import argparse
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
COLORS = ["#ff00c1", "#9600ff", "#4900ff", "#00b8ff", "#00fff9",
          "#ff7400", "#ffcc00", "#9cff00", "#00ff6b", "#ff003c",
          "#00ffcc", "#3c00ff", "#eaff00", "#ff0074", "#00ff96"]
FORMATS = {"Landscape": (1920, 1080), "Vertical": (1080, 1920)}
HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def dependencies():
    try:
        import mido
        import numpy
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Install dependencies: python -m pip install -r tools/midi_video_requirements.txt") from exc
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            raise RuntimeError(f"{name} was not found. Install FFmpeg and add its bin folder to PATH.")


def local_asset(url):
    # Windows drive letters are parsed as URL schemes; handle local paths first.
    if Path(url).is_absolute():
        return Path(url)
    parsed = urlparse(url)
    if parsed.netloc == "assets.unlim8ted.com":
        path = (ROOT / "assets" / unquote(parsed.path).lstrip("/")).resolve()
        if ROOT / "assets" not in path.parents:
            raise ValueError("Asset path is outside the assets folder.")
        return path
    if parsed.scheme:
        raise ValueError(f"Select a local file for {url}")
    path = Path(url)
    return path if path.is_absolute() else ROOT / path


def read_notes(path):
    """Convert tick times using the global tempo map, retaining track colors."""
    import mido
    midi = mido.MidiFile(path)
    if midi.type == 2:
        raise ValueError("Asynchronous type-2 MIDI files are not supported.")
    events = []
    # Tone.js exposes tracks containing notes; skip conductor/meta-only tracks.
    color_index = 0
    for track in midi.tracks:
        tick = 0
        has_notes = any(m.type == "note_on" and m.velocity for m in track)
        for order, msg in enumerate(track):
            tick += msg.time
            events.append((tick, color_index, order, msg))
        if has_notes:
            color_index += 1
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    tempo, previous, seconds = 500000, 0, 0.0
    active = defaultdict(deque)
    notes = []
    for tick, track, _, msg in events:
        seconds += mido.tick2second(tick - previous, midi.ticks_per_beat, tempo)
        previous = tick
        if msg.type == "set_tempo":
            tempo = msg.tempo
        elif msg.type in ("note_on", "note_off"):
            key = (track, msg.channel, msg.note)
            if msg.type == "note_on" and msg.velocity:
                active[key].append(seconds)
            elif active[key]:
                start = active[key].popleft()
                notes.append((start, seconds, msg.note, track))
    for (track, _, pitch), starts in active.items():
        notes.extend((start, seconds, pitch, track) for start in starts)
    if not notes:
        raise ValueError("The MIDI file contains no notes.")
    return sorted(notes)


def audio_duration(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "json", str(path)], capture_output=True, text=True,
                            check=True, **HIDDEN)
    duration = float(json.loads(result.stdout)["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Audio has no valid duration.")
    return duration


class Cancelled(Exception):
    pass


def apply_optics(image, glow=False, lens=False, strength=1.0):
    """Resolve-inspired multiscale bloom and reflected lens ghosts.

    Blur only a small light buffer; keep the original notes/waveform sharp.
    All heavy pixel operations run in Pillow's native code.
    """
    if not glow and not lens:
        return image
    from PIL import Image, ImageChops, ImageFilter, ImageOps
    w, h = image.size
    ratio = min(1, 320 / max(w, h))
    small = image.resize((max(1, round(w * ratio)), max(1, round(h * ratio))), Image.Resampling.BILINEAR)
    lights = small.point([max(0, min(255, round((i - 30) * 1.4))) for i in range(256)] * 3)
    result = Image.new("RGB", small.size)
    if glow:
        for radius, gain in ((2, .55), (9, .40), (24, .25)):
            bloom = lights.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, round(v * gain * strength)))
            result = ImageChops.screen(result, bloom)
    if lens:
        reflected = ImageOps.flip(ImageOps.mirror(lights))
        for scale, gain, shift in ((.65, .32, -.12), (.35, .24, .20), (.17, .20, -.30)):
            ghost = reflected.resize((max(1, round(small.width * scale)), max(1, round(small.height * scale))), Image.Resampling.BILINEAR)
            ghost = ghost.filter(ImageFilter.GaussianBlur(2)).point(lambda v: min(255, round(v * gain * strength)))
            layer = Image.new("RGB", small.size)
            layer.paste(ghost, (round((small.width - ghost.width) / 2 + small.width * shift), round((small.height - ghost.height) / 2)))
            result = ImageChops.screen(result, layer)
        # Anamorphic horizontal flare from the same bright sources.
        streak = lights.resize((max(1, small.width // 16), small.height), Image.Resampling.BILINEAR)
        streak = streak.filter(ImageFilter.GaussianBlur(2)).resize(small.size, Image.Resampling.BILINEAR)
        result = ImageChops.screen(result, streak.point(lambda v: min(255, round(v * .35 * strength))))
    light = result.resize(image.size, Image.Resampling.BILINEAR)
    return ImageChops.screen(image, light)


@lru_cache(maxsize=1)
def available_encoder():
    """Check actual NVENC availability once; installed encoders may lack a GPU."""
    try:
        check = subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x144:d=0.04",
            "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, **HIDDEN)
        if check.returncode == 0:
            return "NVIDIA"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "CPU"


def encoder_options(encoder):
    encoder = available_encoder() if encoder == "Auto" else encoder
    if encoder == "NVIDIA":
        return ["-c:v", "h264_nvenc", "-preset", "p2", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "2"]


def render_frame(notes, size, time, glow=False, lens=False, strength=1.0):
    """Rasterize moving edges with pixel coverage, without integer snapping."""
    from PIL import Image, ImageDraw
    width, height = size
    speed = 100 * height / 1080
    image = Image.new("RGB", size, (10, 8, 20))
    rectangles = []
    for start, end, pitch, track in notes:
        x = pitch * width / 128
        top = height - (end - time) * speed
        bottom = max(top + 1, height - (start - time) * speed)
        top, bottom = max(0.0, top), min(float(height), bottom)
        if bottom <= top:
            continue
        left = int(x)
        right = int(x + max(1, width / 128 - 2)) - 1
        color = COLORS[track % len(COLORS)]
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        rectangles.append((left, right, top, bottom, rgb))

    # Composite sharp, original-color notes last: glow never washes out their fill.
    draw = ImageDraw.Draw(image, "RGBA")
    for left, right, top, bottom, rgb in rectangles:
        first, last = math.floor(top), math.ceil(bottom) - 1
        if first == last:
            draw.line((left, first, right, first), fill=rgb + (round(255 * (bottom - top)),))
        else:
            draw.line((left, first, right, first), fill=rgb + (round(255 * (first + 1 - top)),))
            if last > first + 1:
                draw.rectangle((left, first + 1, right, last - 1), fill=rgb + (255,))
            draw.line((left, last, right, last), fill=rgb + (round(255 * (bottom - last)),))
    return apply_optics(image, glow, lens, strength)


class AudioVisualizer:
    """Offline equivalent of drawAudioViz and its 2048-sample WebAudio analyser."""
    rate = 44100

    def __init__(self, path, size, fps):
        import numpy as np
        from PIL import Image
        self.samples = np.memmap(path, dtype="<f4", mode="r")
        self.size, self.fps = size, fps
        self.image = Image.new("RGB", size)
        self.spectrum = np.zeros(1024)
        n = np.arange(2048)
        self.window = .42 - .5 * np.cos(2 * np.pi * n / 2048) + .08 * np.cos(4 * np.pi * n / 2048)

    def close(self):
        self.samples._mmap.close()

    def frame(self, time, glow=False, lens=False, strength=1.0):
        import numpy as np
        from PIL import Image, ImageDraw, ImageChops, ImageFilter
        w, h = self.size
        # The analyser sees the audio immediately preceding the playback position.
        end = min(len(self.samples), round(time * self.rate))
        chunk = np.zeros(2048)
        available = self.samples[max(0, end - 2048):end]
        if len(available):
            chunk[-len(available):] = available
        magnitude = np.abs(np.fft.rfft(chunk * self.window)[:1024]) / 2048
        smoothing = .85 ** (60 / self.fps)
        self.spectrum = smoothing * self.spectrum + (1 - smoothing) * magnitude
        db = 20 * np.log10(np.maximum(self.spectrum, 1e-12))
        frequency = np.clip((db + 100) / 70, 0, 1)
        energy = min(1, float(np.mean(frequency)) * 1.8)
        # Match the website's fade at 60Hz, independent of export frame rate.
        self.image = self.image.point(lambda v: round(v * .82 ** (60 / self.fps)))
        layer = Image.new("RGB", self.size)
        draw = ImageDraw.Draw(layer, "RGBA")
        cx, cy = w * .5, h * .5
        scale = min(w, h) / 260
        base = min(w, h) * (.10 + energy * .14)
        for r in range(5):
            t = time + r * .35
            wobble = (math.sin(t * 1.7) + math.cos(t * 1.1)) * .5
            radius = max(6 * scale, base + (r * (18 + energy * 22) + wobble * (8 + energy * 10)) * scale)
            box = (cx - radius, cy - radius, cx + radius, cy + radius)
            draw.ellipse(box, outline=(255, 255, 255, round(255 * (.05 + energy * .10))), width=max(1, round(1 + energy * 2)))
            color = COLORS[r * 3 % len(COLORS)]
            rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
            draw.ellipse(box, outline=rgb + (round(255 * (.05 + energy * .18)),), width=max(1, round(1 + energy * 2)))
        bar_w = w / 96
        for i in range(96):
            v = float(frequency[i])
            if v <= 0:
                continue
            color = COLORS[i % len(COLORS)]
            rgb = tuple(int(color[j:j+2], 16) for j in (1, 3, 5))
            x = i * bar_w
            draw.rectangle((x + 1, h - v * h * .45, x + 1 + max(1, bar_w - 3), h), fill=rgb + (round(255 * (.25 + v * .65)),))
        waveform = np.clip(np.floor((chunk + 1) * 128), 0, 255)
        points = [(i / 2047 * w, cy + (float(v) - 128) / 128 * (h * .16 + energy * h * .08)) for i, v in enumerate(waveform)]
        draw.line(points, fill=(233, 231, 255, round(255 * (.35 + energy * .45))), width=2)
        self.image = ImageChops.add(self.image, layer)
        return apply_optics(self.image, glow, lens, strength)


def decode_audio(audio, destination, cancel):
    """Decode to disk so long songs do not consume their full PCM size in RAM."""
    command = ["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-vn",
               "-ac", "1", "-ar", "44100", "-f", "f32le", str(destination)]
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, **HIDDEN)
        try:
            while proc.poll() is None:
                if cancel.wait(.1):
                    raise Cancelled()
            if cancel.is_set():
                raise Cancelled()
            if proc.returncode:
                log.seek(0)
                raise RuntimeError(log.read().decode(errors="replace")[-4000:])
            if not destination.stat().st_size:
                raise ValueError("Audio contains no samples.")
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()


def publish_video(partial, output):
    """Publish on the same volume without duplicating the video or overwriting."""
    if os.name == "nt":
        # Windows rename fails if the destination already exists.
        os.rename(partial, output)
    else:
        # POSIX rename can overwrite, whereas linking preserves exclusivity.
        os.link(partial, output)
        partial.unlink()


def audio_video_rate(size):
    # Audio-reactive trails are expensive under unrestricted constant quality.
    # A bounded VBR keeps full songs practical on nearly full drives.
    maximum = max(1_000_000, round(4_000_000 * size[0] * size[1] / (1920 * 1080)))
    return ["-b:v", str(round(maximum * .75)), "-maxrate", str(maximum), "-bufsize", str(maximum * 2)]


def export_video(notes, audio, output, size, fps, duration, cancel, progress, glow=False, lens=False, strength=1.0, encoder="Auto"):
    width, height = size
    frames = math.ceil(duration * fps)
    # Match drawMidiNotes(): 128 pitch columns, 100 pixels/second,
    # scaled from a 1080px canvas for consistent motion at every resolution.
    speed = 100 * height / 1080
    lookahead = height / speed
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="midi-render-", dir=output.parent) as tmp:
        if notes is None:
            decode_audio(audio, Path(tmp) / "audio.f32", cancel)
        partial = Path(tmp) / "render.mp4"
        with (Path(tmp) / "ffmpeg.log").open("w+b") as log:
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                       "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
                       "-r", str(fps), "-i", "pipe:0", "-i", str(audio),
                       "-map", "0:v:0", "-map", "1:a:0", *encoder_options(encoder),
                       *(audio_video_rate(size) if notes is None else []),
                       "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "320k", "-t", str(duration),
                       "-movflags", "+faststart", str(partial)]
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=log, **HIDDEN)
            # Interrupt even when the worker is blocked writing a frame to FFmpeg.
            stopped = threading.Event()

            def watch_cancel():
                while not stopped.wait(0.1):
                    if cancel.is_set():
                        if proc.poll() is None:
                            proc.terminate()
                        return

            watcher = threading.Thread(target=watch_cancel, daemon=True)
            watcher.start()
            visualizer = None
            try:
                if notes is None:
                    visualizer = AudioVisualizer(Path(tmp) / "audio.f32", size, fps)
                visible, cursor = [], 0
                for frame in range(frames):
                    if cancel.is_set():
                        raise Cancelled()
                    time = frame / fps
                    if visualizer is not None:
                        image = visualizer.frame(time, glow=glow, lens=lens, strength=strength)
                    else:
                        while cursor < len(notes) and notes[cursor][0] <= time + lookahead:
                            visible.append(notes[cursor])
                            cursor += 1
                        visible = [n for n in visible if n[1] >= time]
                        image = render_frame(visible, size, time, glow=glow, lens=lens, strength=strength)
                    proc.stdin.write(image.tobytes())
                    if frame % max(1, fps // 4) == 0:
                        progress((frame + 1) / frames)
                proc.stdin.close()
                code = proc.wait()
                if cancel.is_set():
                    raise Cancelled()
                if code:
                    log.seek(0)
                    raise RuntimeError(log.read().decode(errors="replace")[-4000:])
            except BrokenPipeError as exc:
                if cancel.is_set():
                    raise Cancelled() from exc
                proc.wait()
                log.seek(0)
                raise RuntimeError(log.read().decode(errors="replace")[-4000:]) from exc
            finally:
                if visualizer is not None:
                    visualizer.close()
                stopped.set()
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait()
                if not proc.stdin.closed:
                    try:
                        proc.stdin.close()
                    except BrokenPipeError:
                        pass
                watcher.join()
        # Never replace an existing export, including one created during rendering.
        publish_video(partial, output)
    progress(1.0)


@dataclass
class ExportJob:
    number: int
    midi: Optional[Path]
    audio: Path
    output: Path
    format: str
    size: tuple
    fps: int
    glow: bool = False
    lens: bool = False
    strength: float = 1.0
    encoder: str = "Auto"
    cancel: threading.Event = field(default_factory=threading.Event)
    state: str = "Queued"
    progress: float = 0.0
    error: str = ""
    thread: object = None


class Recorder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Unlim8ted Music Video Recorder")
        self.geometry("1000x820")
        self.minsize(880, 720)
        self.events = queue.Queue()
        self.jobs = {}
        self.next_number = 1
        self.closing = False
        self.midi = tk.StringVar()
        self.audio = tk.StringVar()
        self.output = tk.StringVar(value=str(ROOT / "tools/generated/midi-videos"))
        self.fps = tk.StringVar(value="60")
        self.glow = tk.BooleanVar(value=True)
        self.lens = tk.BooleanVar(value=True)
        self.strength = tk.DoubleVar(value=1.0)
        self.encoder = tk.StringVar(value="Auto")
        self.previews = []
        self.resolution = tk.StringVar(value="1080p")
        self.status = tk.StringVar(value="Select songs (Ctrl/Shift for multiple), then add them to the export queue.")
        self.formats = {name: tk.BooleanVar(value=True) for name in FORMATS}
        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(10, weight=1)
        ttk.Label(body, text="Music Video Recorder", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self.products = []
        try:
            self.products = [p for p in json.loads((ROOT / "assets/data/products.json").read_text(encoding="utf-8"))
                             if p.get("product-type") == "music" and p.get("file")]
        except (OSError, ValueError) as exc:
            self.status.set(f"Catalog unavailable; select local files. {exc}")
        ttk.Label(body, text="Songs\nCtrl/Shift to select").grid(row=1, column=0, sticky="nw", padx=(0, 12))
        song_frame = ttk.Frame(body)
        song_frame.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        self.songs = tk.Listbox(song_frame, selectmode="extended", exportselection=False, height=5)
        self.songs.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(song_frame, orient="vertical", command=self.songs.yview)
        scrollbar.pack(side="right", fill="y")
        self.songs.configure(yscrollcommand=scrollbar.set)
        for product in self.products:
            self.songs.insert("end", product["name"] + (" [audio-reactive]" if not product.get("midi") else ""))
        self.songs.bind("<<ListboxSelect>>", self.select_song)
        self.file_entries = []
        for row, label, variable, kind in [(2, "MIDI file (optional)", self.midi, "midi"), (3, "Audio file", self.audio, "audio"), (4, "Save to", self.output, "folder")]:
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12))
            entry = ttk.Entry(body, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if kind != "folder":
                self.file_entries.append(entry)
            ttk.Button(body, text="Browse...", command=lambda v=variable, k=kind: self.browse(v, k)).grid(row=row, column=2, padx=(8, 0))
        options = ttk.Frame(body)
        options.grid(row=5, column=0, columnspan=3, sticky="w", pady=10)
        for name, value in self.formats.items():
            ttk.Checkbutton(options, text=name + (" (16:9)" if name == "Landscape" else " (9:16)"), variable=value).pack(side="left", padx=(0, 12))
        ttk.Combobox(options, textvariable=self.resolution, values=["1080p", "720p"], width=8, state="readonly").pack(side="left", padx=8)
        ttk.Combobox(options, textvariable=self.fps, values=["24", "30", "60"], width=4, state="readonly").pack(side="left")
        ttk.Label(options, text=" fps").pack(side="left")
        ttk.Checkbutton(options, text="Bloom", variable=self.glow).pack(side="left", padx=8)
        ttk.Checkbutton(options, text="Lens reflections", variable=self.lens).pack(side="left")
        extra = ttk.Frame(body)
        extra.grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Label(extra, text="Light intensity").pack(side="left")
        ttk.Scale(extra, from_=0, to=2.5, variable=self.strength, length=140).pack(side="left", padx=8)
        ttk.Label(extra, text="Encoder").pack(side="left")
        ttk.Combobox(extra, textvariable=self.encoder, values=["Auto", "NVIDIA", "CPU"], width=9, state="readonly").pack(side="left", padx=8)
        ttk.Button(extra, text="Preview", command=self.open_preview).pack(side="left", padx=12)
        self.bar = ttk.Progressbar(body, maximum=100)
        self.bar.grid(row=7, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(body, textvariable=self.status, wraplength=900).grid(row=8, column=0, columnspan=3, sticky="w", pady=5)
        actions = ttk.Frame(body)
        actions.grid(row=9, column=0, columnspan=3, sticky="w", pady=8)
        self.export_button = ttk.Button(actions, text="Export / add selected songs", command=self.start)
        self.export_button.pack(side="left")
        ttk.Button(actions, text="Select all songs", command=lambda: (self.songs.select_set(0, "end"), self.select_song())).pack(side="left", padx=8)
        ttk.Button(actions, text="Cancel selected", command=self.cancel_selected).pack(side="left", padx=8)
        ttk.Button(actions, text="Cancel all", command=self.cancel_all).pack(side="left", padx=8)
        ttk.Button(actions, text="Clear finished", command=self.clear_finished).pack(side="left", padx=8)
        table_frame = ttk.Frame(body)
        table_frame.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=5)
        self.table = ttk.Treeview(table_frame, columns=("song", "format", "settings", "state", "progress"), show="headings", selectmode="extended", height=7)
        for column, title, width in [("song", "Song", 230), ("format", "Format", 90), ("settings", "Video", 210), ("state", "Status", 110), ("progress", "Progress", 80)]:
            self.table.heading(column, text=title)
            self.table.column(column, width=width, stretch=column == "song")
        self.table.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self.show_job)
        self.detail = tk.StringVar(value="Select an export to see its file path or error.")
        ttk.Label(body, textvariable=self.detail, wraplength=900).grid(row=11, column=0, columnspan=3, sticky="w", pady=5)
        if self.products:
            self.songs.selection_set(0)
            self.select_song()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_timer = self.after(100, self.poll)

    def open_preview(self):
        if len(self.songs.curselection()) > 1:
            messagebox.showinfo("Preview", "Select one song to preview.")
            return
        try:
            dependencies()
            audio = Path(self.audio.get())
            midi = Path(self.midi.get()) if self.midi.get().strip() else None
            if not audio.is_file() or (midi is not None and not midi.is_file()):
                raise ValueError("Select an audio file and an optional MIDI file.")
            preview = Preview(self, midi, audio)
            self.previews.append(preview)
        except Exception as exc:
            messagebox.showerror("Cannot preview", str(exc))

    def select_song(self, event=None):
        selection = self.songs.curselection()
        if not selection:
            return
        multiple = len(selection) > 1
        for entry in self.file_entries:
            entry.configure(state="disabled" if multiple else "normal")
        if multiple:
            self.midi.set(f"{len(selection)} catalog songs selected")
            self.audio.set("Each song uses its matching catalog audio")
            return
        try:
            product = self.products[selection[0]]
            self.midi.set(str(local_asset(product["midi"])) if product.get("midi") else "")
            self.audio.set(str(local_asset(product["file"])))
        except ValueError as exc:
            messagebox.showerror("Song unavailable", str(exc))

    def browse(self, variable, kind):
        value = filedialog.askdirectory() if kind == "folder" else filedialog.askopenfilename(
            filetypes=[("MIDI", "*.mid *.midi"), ("All files", "*.*")] if kind == "midi" else [("Audio", "*.mp3 *.wav *.flac *.m4a *.ogg"), ("All files", "*.*")])
        if value:
            if kind != "folder":
                if len(self.songs.curselection()) > 1:
                    self.midi.set("")
                    self.audio.set("")
                self.songs.selection_clear(0, "end")
                for entry in self.file_entries:
                    entry.configure(state="normal")
            variable.set(value)

    def start(self):
        if self.closing:
            return
        try:
            dependencies()
            selection = self.songs.curselection()
            if len(selection) > 1:
                sources = [(local_asset(self.products[i]["midi"]) if self.products[i].get("midi") else None, local_asset(self.products[i]["file"])) for i in selection]
            else:
                sources = [(Path(self.midi.get().strip()) if self.midi.get().strip() else None, Path(self.audio.get()))]
            formats = [name for name, enabled in self.formats.items() if enabled.get()]
            if not formats:
                raise ValueError("Select at least one video format.")
            if not self.output.get().strip():
                raise ValueError("Choose an output folder.")
            folder = Path(self.output.get()).resolve()
            fps = int(self.fps.get())
            scale = 2 / 3 if self.resolution.get() == "720p" else 1
            reserved = {job.output for job in self.jobs.values() if job.state in ("Queued", "Rendering", "Cancelling")}
            planned = []
            for midi, audio in sources:
                if (midi is not None and not midi.is_file()) or not audio.is_file():
                    raise ValueError("Select an existing audio file and, optionally, an existing MIDI file.")
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (midi or audio).stem).strip(" .") or "song"
                for fmt in formats:
                    output = folder / f"{name}_{fmt.lower()}.mp4"
                    # Re-exporting after changing quality gets a fresh filename.
                    suffix = 2
                    while output.exists() or output in reserved:
                        output = folder / f"{name}_{fmt.lower()}_{suffix}.mp4"
                        suffix += 1
                    size = tuple(round(v * scale) for v in FORMATS[fmt])
                    planned.append((midi.resolve() if midi else None, audio.resolve(), output, fmt, size, fps, self.glow.get(), self.lens.get(), float(self.strength.get()), self.encoder.get()))
                    reserved.add(output)
        except Exception as exc:
            messagebox.showerror("Cannot export", str(exc))
            return
        for settings in planned:
            job = ExportJob(self.next_number, *settings)
            self.next_number += 1
            self.jobs[job.number] = job
            self.table.insert("", "end", iid=str(job.number), values=self.job_values(job))
        self.dispatch()
        self.update_summary()

    @staticmethod
    def job_values(job):
        return ((job.midi or job.audio).stem, job.format, f"{job.size[0]}x{job.size[1]} / {job.fps} fps" + (" / Audio" if job.midi is None else "") + (" / Glow" if job.glow else ""), job.state, f"{job.progress:.0%}")

    def run_job(self, job):
        try:
            if job.cancel.is_set():
                raise Cancelled()
            notes = read_notes(job.midi) if job.midi else None
            duration = audio_duration(job.audio)
            export_video(notes, job.audio, job.output, job.size, job.fps, duration, job.cancel,
                         lambda fraction: self.events.put((job.number, "progress", fraction)), glow=job.glow, lens=job.lens, strength=job.strength, encoder=job.encoder)
            self.events.put((job.number, "Completed", ""))
        except Cancelled:
            self.events.put((job.number, "Cancelled", ""))
        except Exception as exc:
            self.events.put((job.number, "Failed", str(exc)))

    def dispatch(self):
        if self.closing:
            return
        active = sum(j.thread is not None and j.thread.is_alive() for j in self.jobs.values())
        for job in self.jobs.values():
            if active >= 2:
                break
            if job.state == "Queued":
                active += 1
                job.state = "Rendering"
                self.table.item(str(job.number), values=self.job_values(job))
                job.thread = threading.Thread(target=self.run_job, args=(job,), name=f"render-{job.number}", daemon=True)
                job.thread.start()

    def cancel_jobs(self, numbers):
        for number in numbers:
            job = self.jobs[number]
            if job.state in ("Queued", "Rendering"):
                job.cancel.set()
                job.state = "Cancelled" if job.state == "Queued" else "Cancelling"
                self.table.item(str(number), values=self.job_values(job))
        self.update_summary()

    def cancel_selected(self):
        self.cancel_jobs([int(number) for number in self.table.selection()])

    def cancel_all(self):
        self.cancel_jobs(list(self.jobs))

    def clear_finished(self):
        for number, job in list(self.jobs.items()):
            if job.state in ("Completed", "Cancelled", "Failed") and not (job.thread and job.thread.is_alive()):
                self.table.delete(str(number))
                del self.jobs[number]
        self.update_summary()

    def show_job(self, event=None):
        selection = self.table.selection()
        if selection:
            job = self.jobs[int(selection[0])]
            self.detail.set(f"{job.state}: {job.output}" + (f"\n{job.error}" if job.error else ""))

    def update_summary(self):
        if not self.jobs:
            self.bar["value"] = 0
            self.status.set("Select songs, then add them to the export queue.")
            return
        counts = {state: sum(j.state == state for j in self.jobs.values()) for state in ("Queued", "Rendering", "Cancelling", "Completed", "Cancelled", "Failed")}
        self.bar["value"] = 100 * sum(j.progress if j.state in ("Queued", "Rendering", "Cancelling") else 1 for j in self.jobs.values()) / len(self.jobs)
        self.status.set(" | ".join(f"{state}: {count}" for state, count in counts.items() if count))

    def poll(self):
        try:
            while True:
                number, kind, value = self.events.get_nowait()
                job = self.jobs[number]
                if kind == "progress":
                    job.progress = value
                else:
                    job.state, job.error = kind, value
                    if kind == "Completed":
                        job.progress = 1
                self.table.item(str(number), values=self.job_values(job))
                self.show_job()
        except queue.Empty:
            pass
        self.dispatch()
        if self.jobs:
            self.update_summary()
        if self.closing and not any(j.thread and j.thread.is_alive() for j in self.jobs.values()) and not any(p.winfo_exists() for p in self.previews):
            self.destroy()
            return
        self.poll_timer = self.after(100, self.poll)

    def destroy(self):
        self.after_cancel(self.poll_timer)
        super().destroy()

    def close(self):
        self.closing = True
        for preview in self.previews:
            if preview.winfo_exists():
                preview.close()
        self.export_button.configure(state="disabled")
        self.cancel_all()


class Preview(tk.Toplevel):
    """Scrubbable preview using the same renderer/settings as the exporter."""
    def __init__(self, owner, midi, audio):
        super().__init__(owner)
        self.owner, self.audio = owner, audio
        self.title("Music video preview")
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.temp = tempfile.TemporaryDirectory(prefix="music-preview-")
        self.notes = self.visualizer = None
        self.ready = self.playing = self.closed = False
        self.player = None
        self.duration = self.position = self.anchor = 0
        self.last_frame = -1
        self.last_options = None
        self.orientation = tk.StringVar(value="Landscape")
        self.message = tk.StringVar(value="Preparing preview...")
        self.status_label = ttk.Label(self, textvariable=self.message)
        self.status_label.pack(padx=12, pady=8)
        self.canvas = tk.Label(self, background="#080814")
        self.canvas.pack(padx=12, pady=8)
        self.slider = ttk.Scale(self, from_=0, to=1, command=self.seek)
        self.slider.pack(fill="x", padx=12)
        controls = ttk.Frame(self)
        controls.pack(padx=12, pady=12)
        self.play_button = ttk.Button(controls, text="Play", command=self.toggle, state="disabled")
        self.play_button.pack(side="left", padx=6)
        orientation = ttk.Combobox(controls, textvariable=self.orientation, values=list(FORMATS), state="readonly", width=12)
        orientation.pack(side="left", padx=6)
        orientation.bind("<<ComboboxSelected>>", lambda _: self.resize_preview())
        ttk.Checkbutton(controls, text="Bloom", variable=owner.glow).pack(side="left")
        ttk.Checkbutton(controls, text="Lens reflections", variable=owner.lens).pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.worker = threading.Thread(target=self.prepare, args=(midi,), daemon=True)
        self.worker.start()
        self.timer = self.after(30, self.tick)

    def prepare(self, midi):
        try:
            duration = audio_duration(self.audio)
            notes = read_notes(midi) if midi else None
            if notes is None:
                decode_audio(self.audio, Path(self.temp.name) / "audio.f32", self.cancel)
            if not self.cancel.is_set():
                self.events.put((duration, notes, None))
        except Cancelled:
            pass
        except Exception as exc:
            self.events.put((0, None, str(exc)))

    def resize_preview(self):
        w, h = FORMATS[self.orientation.get()]
        scale = min(720 / w, max(180, self.winfo_screenheight() - 300) / h)
        self.size = (max(2, round(w * scale)), max(2, round(h * scale)))
        if self.visualizer is not None:
            self.visualizer.close()
            self.visualizer = None
        if self.notes is None and self.ready:
            self.visualizer = AudioVisualizer(Path(self.temp.name) / "audio.f32", self.size, 30)
        self.last_frame = -1
        self.draw()

    def stop_audio(self):
        if self.player is not None:
            if self.player.poll() is None:
                self.player.terminate()
                self.player.wait()
            self.player = None

    def toggle(self):
        if not self.ready:
            return
        self.playing = not self.playing
        self.stop_audio()
        if self.playing:
            if self.position >= self.duration:
                self.position = 0
            self.anchor = time.perf_counter() - self.position
            if shutil.which("ffplay"):
                self.player = subprocess.Popen([
                    "ffplay", "-v", "error", "-nodisp", "-autoexit", "-ss", str(self.position),
                    "-i", str(self.audio)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, **HIDDEN)
        self.play_button.configure(text="Pause" if self.playing else "Play")

    def seek(self, value):
        if not self.ready or getattr(self, "updating_slider", False):
            return
        if self.playing:
            self.toggle()
        self.position = float(value)
        if self.visualizer is not None:
            from PIL import Image
            self.visualizer.image = Image.new("RGB", self.size)
            self.visualizer.spectrum.fill(0)
            # Rebuild a short history so a seek has settled spectrum and trails.
            for step in range(8):
                self.visualizer.frame(max(0, self.position - (8 - step) / 30))
        self.last_frame = -1

    def draw(self):
        if not self.ready:
            return
        from PIL import ImageTk
        options = (self.owner.glow.get(), self.owner.lens.get(), float(self.owner.strength.get()))
        frame = round(self.position * 30)
        if frame == self.last_frame and options == self.last_options:
            return
        self.last_frame, self.last_options = frame, options
        if self.visualizer is None:
            image = render_frame(self.notes, self.size, self.position, *options)
        else:
            image = self.visualizer.frame(self.position, *options)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.configure(image=self.photo)
        suffix = "" if shutil.which("ffplay") else " | Silent preview (install ffplay for audio)"
        self.message.set(f"{self.position:.1f} / {self.duration:.1f}s" + suffix)

    def tick(self):
        if self.closed:
            if self.worker.is_alive():
                self.timer = self.after(50, self.tick)
            else:
                self.temp.cleanup()
                self.destroy()
            return
        try:
            duration, notes, error = self.events.get_nowait()
            if error:
                self.message.set(error)
            else:
                self.duration, self.notes, self.ready = duration, notes, True
                self.slider.configure(to=duration)
                self.play_button.configure(state="normal")
                self.resize_preview()
        except queue.Empty:
            pass
        if self.playing:
            self.position = min(self.duration, time.perf_counter() - self.anchor)
            self.updating_slider = True
            self.slider.set(self.position)
            self.updating_slider = False
            if self.position >= self.duration:
                self.toggle()
        self.draw()
        self.timer = self.after(33, self.tick)

    def close(self):
        self.closed = True
        self.cancel.set()
        self.playing = False
        self.stop_audio()
        if self.visualizer is not None:
            self.visualizer.close()
            self.visualizer = None
        self.withdraw()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", type=Path, metavar="OUTPUT_DIR", help="Export a two-second sample in both orientations without opening the GUI")
    args = parser.parse_args()
    if args.smoke_test:
        dependencies()
        products = json.loads((ROOT / "assets/data/products.json").read_text(encoding="utf-8"))
        song = next(p for p in products if p.get("id") == "unlim8ted-stinger")
        notes = read_notes(local_asset(song["midi"]))
        def sample(name, size):
            path = args.smoke_test / (name + ".mp4")
            export_video(notes, local_asset(song["file"]), path, size, 60, 2, threading.Event(), lambda _: None, glow=True)
            print(path)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(sample, name, size) for name, size in {"landscape": (640, 360), "vertical": (360, 640)}.items()]
            for future in futures:
                future.result()
    else:
        Recorder().mainloop()


if __name__ == "__main__":
    main()
