
import json
import queue
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from PySide6.QtCore import QThread, Signal



SAMPLE_RATE = 16000
BLOCK_SIZE = 1600
WAKE_WORD = "nova"



class NOVAVoiceWorker(QThread):
    status_changed = Signal(str)
    wake_detected = Signal()
    transcript_ready = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        model_path="models/vosk-model-small-en-us-0.15",
        whisper_model="base",
        parent=None,
    ):
        super().__init__(parent)

        self.model_path = Path(model_path)
        self.whisper_model_name = whisper_model

        self._running = False
        self._listening_enabled = True
        self._audio_queue = queue.Queue(maxsize=30)

        # Thread-safe request to listen for a follow-up answer.
        self._followup_requested = threading.Event()

    def stop(self):
        self._running = False

    def set_listening_enabled(self, enabled):
        self._listening_enabled = bool(enabled)

        if not enabled:
            self._clear_audio_queue()

    def start_followup_listening(self):
        """Listen for an answer without requiring the wake word."""
        if not self._running:
            print(
                "[VOICE] Cannot start follow-up: worker is not running",
                flush=True,
            )
            return

        self._clear_audio_queue()
        self._listening_enabled = True
        self._followup_requested.set()

        print(
            "[VOICE] Follow-up listening requested",
            flush=True,
        )

    def _audio_callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ):
        if not self._running:
            return

        try:
            self._audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(bytes(indata))
            except (queue.Empty, queue.Full):
                pass

    def _clear_audio_queue(self):
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    @staticmethod
    def _rms(audio_bytes):
        samples = np.frombuffer(audio_bytes, dtype=np.int16)

        if samples.size == 0:
            return 0.0

        samples = samples.astype(np.float32)
        return float(np.sqrt(np.mean(samples * samples)))

    def _record_command(self, prompt_status="SAY YOUR COMMAND"):
        self.status_changed.emit(prompt_status)

        audio_chunks = []
        speech_started = False
        speech_start_time = None
        last_voice_time = None

        start_wait = time.monotonic()

        max_duration = 12.0
        silence_duration = 0.65
        start_timeout = 8.0
        volume_threshold = 350

        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.25)
            except queue.Empty:
                if (
                    not speech_started
                    and time.monotonic() - start_wait > start_timeout
                ):
                    print(
                        "[VOICE] No speech detected before timeout",
                        flush=True,
                    )
                    return b""

                if (
                    speech_started
                    and last_voice_time is not None
                    and time.monotonic() - last_voice_time >= silence_duration
                ):
                    break

                continue

            now = time.monotonic()
            volume = self._rms(chunk)

            if volume >= volume_threshold:
                if not speech_started:
                    speech_started = True
                    speech_start_time = now

                last_voice_time = now

            if speech_started:
                audio_chunks.append(chunk)

                if now - speech_start_time >= max_duration:
                    break

                if (
                    last_voice_time is not None
                    and now - last_voice_time >= silence_duration
                ):
                    break

        return b"".join(audio_chunks)

    def _transcribe_command(self, command_audio, stt_model, recognizer):
        if not command_audio:
            recognizer.Reset()
            self._clear_audio_queue()
            return False

        self.status_changed.emit("PROCESSING SPEECH")

        samples = (
            np.frombuffer(command_audio, dtype=np.int16).astype(np.float32)
            / 32768.0
        )

        segments, _ = stt_model.transcribe(
            samples,
            beam_size=1,
            vad_filter=True,
        )

        transcript = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

        recognizer.Reset()
        self._clear_audio_queue()

        if not transcript:
            print("[VOICE] No transcript produced", flush=True)
            return False

        self.set_listening_enabled(False)
        self.status_changed.emit("PROCESSING REQUEST")

        print(
            f"[VOICE] Transcript: {transcript}",
            flush=True,
        )

        self.transcript_ready.emit(transcript)
        return True

    def run(self):
        self._running = True

        print("[VOICE] Worker entered run()", flush=True)

        try:
            print("[VOICE] Importing Vosk...", flush=True)
            from vosk import Model, KaldiRecognizer

            print("[VOICE] Importing Whisper...", flush=True)
            from faster_whisper import WhisperModel

            if not self.model_path.exists():
                raise FileNotFoundError(
                    "Vosk model folder not found: "
                    f"{self.model_path.resolve()}"
                )

            self.status_changed.emit("LOADING MODELS")

            print("[VOICE] Loading Vosk model...", flush=True)
            wake_model = Model(str(self.model_path))

            recognizer = KaldiRecognizer(
                wake_model,
                SAMPLE_RATE,
                json.dumps([WAKE_WORD, "[unk]"]),
            )

            print("[VOICE] Loading Whisper model...", flush=True)
            stt_model = WhisperModel(
                self.whisper_model_name,
                device="cpu",
                compute_type="int8",
            )

            self._clear_audio_queue()

            print("[VOICE] Opening microphone...", flush=True)
            self.status_changed.emit("WAITING FOR NOVA")

            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype="int16",
                channels=1,
                callback=self._audio_callback,
            ):
                while self._running:

                    # Handle follow-up requests BEFORE wake-word detection.
                    if self._followup_requested.is_set():
                        self._followup_requested.clear()
                        self._clear_audio_queue()

                        print(
                            "[VOICE] Entering follow-up recording mode",
                            flush=True,
                        )

                        command_audio = self._record_command(
                            prompt_status="WAITING FOR COMMAND"
                        )

                        if not self._running:
                            break

                        if not self._transcribe_command(
                            command_audio,
                            stt_model,
                            recognizer,
                        ):
                            self.status_changed.emit("WAITING FOR NOVA")

                        continue

                    # Pause all listening while NOVA is thinking or speaking.
                    if not self._listening_enabled:
                        self._clear_audio_queue()
                        time.sleep(0.05)
                        continue

                    try:
                        audio_chunk = self._audio_queue.get(timeout=0.25)
                    except queue.Empty:
                        continue

                    if not recognizer.AcceptWaveform(audio_chunk):
                        continue

                    result = json.loads(recognizer.Result())
                    recognized_text = result.get("text", "").lower()

                    if WAKE_WORD not in recognized_text.split():
                        continue

                    print("[VOICE] Wake word detected", flush=True)

                    self._clear_audio_queue()
                    self.wake_detected.emit()

                    self.status_changed.emit("WAITING FOR COMMAND")
                    command_audio = self._record_command(
                        prompt_status="WAITING FOR COMMAND"
                    )       

                    if not self._running:
                        break

                    if not self._transcribe_command(
                        command_audio,
                        stt_model,
                        recognizer,
                    ):
                        self.status_changed.emit("WAITING FOR NOVA")

        except Exception as exc:
            print(f"[VOICE ERROR] {exc!r}", flush=True)

            self.error.emit(f"{type(exc).__name__}: {exc}")
            self.status_changed.emit("VOICE ERROR")

        finally:
            self._running = False
            print("[VOICE] Worker stopped", flush=True)


if __name__ == "__main__":
    import sys
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication(sys.argv)
    voice = NOVAVoiceWorker()

    voice.status_changed.connect(
        lambda message: print(f"[STATUS] {message}", flush=True)
    )
    voice.wake_detected.connect(
        lambda: print("[WAKE] NOVA activated!", flush=True)
    )
    voice.transcript_ready.connect(
        lambda text: print(f"[HEARD] {text}", flush=True)
    )
    voice.error.connect(
        lambda message: print(f"[ERROR] {message}", flush=True)
    )
    voice.finished.connect(
        lambda: print("[END] Voice worker stopped", flush=True)
    )

    print("[VOICE] Starting standalone test", flush=True)
    voice.start()

    sys.exit(app.exec())
