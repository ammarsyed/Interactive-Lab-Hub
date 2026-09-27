#!/usr/bin/env python3
"""Ask out loud for a number, listen for the answer, and record it.

Numbers are a stress test for speech recognition: whisper may hear the same
zip code as "14850", "1-4-8-5-0", "one four eight five zero" or "fourteen
eight fifty". This prints the raw transcript next to the digits pulled out of
it, reads the digits back, and appends both to answers.csv so the errors can
be compared later.

    python ask_number.py
    python ask_number.py --question "How many pets do you have?"
    python ask_number.py --model small.en --min-silence 1.5
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd
from faster_whisper import WhisperModel

from echo_bot import DEFAULT_VAD, DEFAULT_VOICE, SAMPLE_RATE, Speaker

LOG = Path(__file__).resolve().parent / "answers.csv"
DIGIT_WORDS = {"zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3",
               "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
               "nine": "9"}


def extract_digits(text: str) -> str:
    """Keeps numerals and spelled-out single digits, in order. Anything else
    ("fourteen", "fifty") is dropped, which is exactly the kind of error to note."""
    tokens = re.findall(r"\d+|[a-z]+", text.lower())
    return "".join(t if t.isdigit() else DIGIT_WORDS.get(t, "") for t in tokens)


def listen_once(vad: sherpa_onnx.VoiceActivityDetector, window: int) -> np.ndarray:
    """Blocks until the VAD finds one complete utterance, then returns it."""
    buffer = np.empty(0, dtype=np.float32)
    with sd.InputStream(channels=1, dtype="float32", samplerate=SAMPLE_RATE) as stream:
        while True:
            chunk, _ = stream.read(int(0.1 * SAMPLE_RATE))
            buffer = np.concatenate([buffer, chunk.reshape(-1)])
            while len(buffer) > window:
                vad.accept_waveform(buffer[:window])
                buffer = buffer[window:]
            if not vad.empty():
                utterance = np.array(vad.front.samples, dtype=np.float32)
                vad.pop()
                return utterance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question", default="What is your zip code?")
    parser.add_argument("--model", default="base.en",
                        help="whisper model size (default: base.en)")
    parser.add_argument("--min-silence", type=float, default=1.0,
                        help="seconds of silence that end the answer; people pause "
                             "between digit groups, so this is longer than echo_bot's")
    args = parser.parse_args()

    for path, what in [(DEFAULT_VAD, "VAD model"), (DEFAULT_VOICE, "Piper voice")]:
        if not path.is_file():
            sys.exit(f"{what} not found at {path}. Run ./setup.sh first.")

    print("Loading models...", flush=True)
    recognizer = WhisperModel(args.model, device="cpu", compute_type="int8")
    speaker = Speaker(DEFAULT_VOICE)

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(DEFAULT_VAD)
    config.silero_vad.min_silence_duration = args.min_silence
    config.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)

    speaker.say(args.question)
    print(f"Asked: {args.question}\nListening...", flush=True)

    heard = ""
    while not heard:  # skip noise that transcribes to nothing
        utterance = listen_once(vad, config.silero_vad.window_size)
        t0 = time.perf_counter()
        segments, _ = recognizer.transcribe(utterance, beam_size=1)
        heard = " ".join(s.text.strip() for s in segments)
    asr_time = time.perf_counter() - t0

    digits = extract_digits(heard)
    print(f"  heard:  {heard}")
    print(f"  digits: {digits or '(none)'}   [asr {asr_time:.2f}s, {args.model}]")

    if digits:
        speaker.say("I heard " + " ".join(digits) + ".")
    else:
        speaker.say("Sorry, I didn't catch a number.")

    new_file = not LOG.exists()
    with LOG.open("a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["time", "model", "question", "heard", "digits"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), args.model,
                         args.question, heard, digits])
    print(f"  saved to {LOG.name}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
