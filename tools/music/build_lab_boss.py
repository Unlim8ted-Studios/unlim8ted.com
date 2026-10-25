"""Build Lab Boss with separate GM instrument tracks and a continuous ending."""
from pathlib import Path
import subprocess
import mido

ROOT = Path(__file__).resolve().parents[2]
MUSIC = ROOT / "assets/music"
# GM programs are zero-based. FL Studio plugins cannot be embedded in MIDI;
# these programs preserve each part's intended instrument family.
INSTRUMENTS = {
    "Strings": (0, 48), "Acoustic Piano": (1, 0), "Electric Bass": (2, 33),
    "Synth Strings": (3, 50), "Synth Lead": (4, 80), "Synth Pad": (5, 88),
    "Drums": (9, None),
}
FADE = 4.0
ENDING_GAIN_DB = 6.0
ENDING_EXPRESSION = 127
TICKS = 19200


def timed_tracks(source):
    """Keep original tracks while applying the shared MIDI tempo map."""
    all_events = []
    for index, track in enumerate(source.tracks):
        tick = 0
        for order, message in enumerate(track):
            tick += message.time
            all_events.append((tick, index, order, message))
    tempo, previous, elapsed = 500000, 0, 0.0
    tracks = [[] for _ in source.tracks]
    for tick, index, _, message in sorted(all_events, key=lambda e: e[:3]):
        elapsed += mido.tick2second(tick - previous, source.ticks_per_beat, tempo)
        previous = tick
        if message.type == "set_tempo":
            tempo = message.tempo
        tracks[index].append((elapsed, message))
    return tracks


def duration(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True))


def build():
    sources = [mido.MidiFile(MUSIC / f"LabBoss{name}.mid") for name in ("Intro", "Loop", "Outro")]
    tracks = [timed_tracks(source) for source in sources]
    outro_trim = min(t for track in tracks[2] for t, msg in track if msg.type == "note_on" and msg.velocity)
    intro_end, loop_end = sources[0].length, sources[1].length
    # Keep four seconds of the FL render's decay beyond the score boundary.
    # Fade only the middle section's decay; the ending enters at full gain.
    middle_end = min(duration(MUSIC / "LabBossLoop.wav"), loop_end + FADE)
    fade = min(FADE, middle_end - loop_end)
    outro_at = intro_end + middle_end - fade
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(MUSIC / "LabBossIntro.wav"), "-i", str(MUSIC / "LabBossLoop.wav"),
        "-i", str(MUSIC / "LabBossOutro.wav"), "-filter_complex",
        f"[0:a]atrim=end={intro_end},asetpts=PTS-STARTPTS[a];"
        f"[1:a]atrim=end={middle_end},asetpts=PTS-STARTPTS[b];"
        f"[2:a]atrim=start={outro_trim},asetpts=PTS-STARTPTS,volume={ENDING_GAIN_DB}dB[c];"
        f"[b][c]acrossfade=d={fade}:c1=tri:c2=nofade[bc];[a][bc]concat=n=2:v=0:a=1[out]",
        "-map", "[out]", "-c:a", "pcm_f32le", str(MUSIC / "LabBoss.wav")], check=True)
    total = duration(MUSIC / "LabBoss.wav")
    result = mido.MidiFile(type=1, ticks_per_beat=9600)
    conductor = mido.MidiTrack([mido.MetaMessage("track_name", name="Lab Boss"), mido.MetaMessage("set_tempo", tempo=500000)])
    result.tracks.append(conductor)
    # Allocate fresh melodic channels for the outro's overlapping instruments.
    # MIDI expression on these channels cannot mute the outgoing middle section.
    for section, section_tracks in enumerate(tracks):
        offset = (0, intro_end, outro_at)[section]
        trim = outro_trim if section == 2 else 0
        for original, events in zip(sources[section].tracks, section_tracks):
            if not any(msg.type == "note_on" and msg.velocity for _, msg in events):
                continue
            name = next((msg.name for msg in original if msg.type == "track_name"), "Acoustic Piano")
            channel, program = INSTRUMENTS[name]
            if section == 2:
                channel = {0: 6, 1: 7}.get(channel, channel)
            start = round(offset * TICKS)
            messages = [(start, mido.MetaMessage("track_name", name=f"{('Intro', 'Middle', 'Ending')[section]} / {name}")),
                        (start, mido.MetaMessage("instrument_name", name=name)),
                        (start, mido.Message("control_change", channel=channel, control=11, value=ENDING_EXPRESSION if section == 2 else 127))]
            if program is not None:
                messages.append((start, mido.Message("program_change", channel=channel, program=program)))
            for seconds, msg in events:
                if msg.is_meta or msg.type == "program_change" or not hasattr(msg, "channel"):
                    continue
                if msg.type == "control_change" and msg.control == 11:
                    continue
                if section == 2 and msg.type == "note_on" and msg.velocity:
                    msg = msg.copy(velocity=min(127, round(msg.velocity * 10 ** (ENDING_GAIN_DB / 40))))
                messages.append((round((offset + max(0, seconds - trim)) * TICKS), msg.copy(channel=channel)))
            if section == 1:
                for step in range(81):
                    value = round(127 * (1 - step / 80))
                    messages.append((round((outro_at + fade * step / 80) * TICKS), mido.Message("control_change", channel=channel, control=11, value=value)))
            target, previous = mido.MidiTrack(), 0
            for tick, msg in sorted(messages, key=lambda e: e[0]):
                target.append(msg.copy(time=tick - previous))
                previous = tick
            result.tracks.append(target)
    conductor.append(mido.MetaMessage("end_of_track", time=round(total * TICKS)))
    result.save(MUSIC / "LabBoss.mid")
    print(f"Built {total:.3f}s; ending enters at full gain at {outro_at:.3f}s over {fade:.1f}s of middle-section decay; {len(result.tracks)-1} instrument tracks.")


if __name__ == "__main__":
    build()
