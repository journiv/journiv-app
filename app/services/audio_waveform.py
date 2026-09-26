"""Waveform peak extraction for audio media.

Decodes an audio file to mono PCM with ffmpeg and reduces it to a fixed number
of amplitude buckets for the waveform player. The PCM is streamed and reduced as
it arrives, so memory stays bounded however long the recording is.

The decoded sample count is also the only reliable duration for browser
recordings: a `MediaRecorder` WebM is written as a live stream and usually
carries no container duration for ffprobe to read.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from array import array
from pathlib import Path
from typing import List, NamedTuple, Optional

from app.core.logging_config import log_error, log_warning

WAVEFORM_BUCKETS = 400
PEAK_SCALE = 100

# 8 kHz mono is plenty for an amplitude envelope and keeps decoding cheap.
_SAMPLE_RATE = 8000
# Peaks are first kept at this fine resolution (5 ms) and resampled to
# WAVEFORM_BUCKETS at the end, once the total length is finally known. One hour
# of audio is ~720k bins (~1.4 MB), so this stays bounded.
_FINE_BIN_SAMPLES = 40
_READ_CHUNK_BYTES = 64 * 1024
_BYTES_PER_SAMPLE = 2


class WaveformResult(NamedTuple):
    peaks: List[int]
    duration: float


def extract_waveform(file_path: Path, timeout: int) -> Optional[WaveformResult]:
    """Return 400 peaks (0-100) and the decoded duration, or None on failure.

    An undecodable or empty stream returns None ("not computed"). A decodable
    but silent one returns 400 zeros ("computed, silent") — the two must not be
    confused.
    """
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin",
        "-i", str(file_path),
        "-map", "0:a:0", "-ac", "1", "-ar", str(_SAMPLE_RATE),
        "-f", "s16le", "-",
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log_error(f"Failed to start ffmpeg for waveform of {file_path}: {exc}")
        return None

    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout, _kill)
    timer.start()
    fine_peaks = array("H")
    total_samples = 0
    try:
        carry = b""
        current_peak = 0
        in_bin = 0
        assert proc.stdout is not None
        while True:
            raw = proc.stdout.read(_READ_CHUNK_BYTES)
            if not raw:
                break
            # A pipe read may end mid-sample; carry the odd byte into the next.
            raw = carry + raw
            usable = len(raw) - len(raw) % _BYTES_PER_SAMPLE
            carry = raw[usable:]
            samples = array("h")
            samples.frombytes(raw[:usable])
            if sys.byteorder == "big":
                samples.byteswap()
            total_samples += len(samples)
            index = 0
            length = len(samples)
            while index < length:
                take = min(_FINE_BIN_SAMPLES - in_bin, length - index)
                # abs(-32768) is 32768, which still fits an unsigned 16-bit bin.
                peak = max(map(abs, samples[index : index + take]))
                if peak > current_peak:
                    current_peak = peak
                in_bin += take
                index += take
                if in_bin == _FINE_BIN_SAMPLES:
                    fine_peaks.append(current_peak)
                    current_peak = 0
                    in_bin = 0
        if in_bin:
            fine_peaks.append(current_peak)
        returncode = proc.wait()
    except Exception as exc:
        proc.kill()
        proc.wait()
        log_error(f"Waveform extraction failed for {file_path}: {exc}")
        return None
    finally:
        timer.cancel()
        if proc.stdout is not None:
            proc.stdout.close()

    if timed_out.is_set():
        log_warning(f"Waveform extraction timed out for {file_path}")
        return None
    if returncode != 0 or total_samples == 0:
        log_warning(
            f"Waveform extraction produced no audio for {file_path} "
            f"(exit {returncode}, {total_samples} samples)"
        )
        return None

    return WaveformResult(
        peaks=_resample_peaks(fine_peaks),
        duration=total_samples / _SAMPLE_RATE,
    )


def _resample_peaks(fine_peaks: "array[int]") -> List[int]:
    """Reduce fine-grained peaks to exactly WAVEFORM_BUCKETS ints in 0-100."""
    count = len(fine_peaks)
    loudest = max(fine_peaks) if count else 0
    if loudest == 0:
        return [0] * WAVEFORM_BUCKETS

    buckets: List[int] = []
    for i in range(WAVEFORM_BUCKETS):
        start = i * count // WAVEFORM_BUCKETS
        end = max((i + 1) * count // WAVEFORM_BUCKETS, start + 1)
        peak = max(fine_peaks[start : min(end, count)])
        buckets.append(min(PEAK_SCALE, max(0, round(peak * PEAK_SCALE / loudest))))
    return buckets
