import math
import os
import tempfile
import threading
import time
import librosa

import pygame
import soundfile as sf
from PySide6.QtCore import QThread, Signal


class NOVATTSWorker(QThread):
    """Generate and play English speech using Pocket TTS only."""

    completed = Signal()
    failed = Signal(str)
    speaking_changed = Signal(bool)
    audio_level = Signal(float)

    # Pocket TTS settings
    POCKET_VOICE = os.path.join(
    os.path.dirname(__file__),
    "voice_samples",
    "stuart_bell.wav",
)

    # Shared model and voice state are loaded once per Python process.
    _pocket_model = None
    _pocket_voice_state = None
    _pocket_load_lock = threading.Lock()
    _pocket_generation_lock = threading.Lock()

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = str(text).strip()
        self._stop_event = threading.Event()

    def stop(self):
        """Request cancellation. Generation itself may finish before stopping."""
        self._stop_event.set()

    @staticmethod
    def _remove_file(path):
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _create_temp_file(suffix=".wav"):
        fd, path = tempfile.mkstemp(prefix="nova_tts_", suffix=suffix)
        os.close(fd)
        return path

    @staticmethod
    def _validate_audio(path):
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError("Pocket TTS produced an empty audio file.")

    @classmethod
    def _get_pocket_model(cls):
        """Load and cache the Pocket TTS model and selected voice state."""
        if cls._pocket_model is None:
            with cls._pocket_load_lock:
                if cls._pocket_model is None:
                    print("[NOVA TTS] Loading Pocket TTS model", flush=True)
                    from pocket_tts import TTSModel

                    model = TTSModel.load_model()
                    voice_state = model.get_state_for_audio_prompt(
                        cls.POCKET_VOICE
                    )
                    cls._pocket_model = model
                    cls._pocket_voice_state = voice_state
                    print("[NOVA TTS] Pocket TTS model ready", flush=True)

        return cls._pocket_model, cls._pocket_voice_state

    def _generate_pocket_audio(self, text, output_file):
        """Generate speech with Pocket TTS and save it as a WAV file."""
        model, voice_state = self._get_pocket_model()

        if self._stop_event.is_set():
            return

        started = time.monotonic()
        print(
            f"[NOVA TTS] Pocket inference started ({len(text)} characters)",
            flush=True,
        )

        # Serialize inference in case multiple TTS workers overlap.
        with self._pocket_generation_lock:
            if self._stop_event.is_set():
                return
            audio = model.generate_audio(voice_state, text)

        if self._stop_event.is_set():
            return

        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()

        # Lower the pitch by 2 semitones while keeping duration similar.

        sf.write(
            output_file,
            audio,
            model.sample_rate,
            format="WAV",
            subtype="PCM_16",
        )

        sf.write(
            output_file,
            audio,
            model.sample_rate,
            format="WAV",
            subtype="PCM_16",
        )
        self._validate_audio(output_file)

        print(
            f"[NOVA TTS] Pocket generation time: "
            f"{time.monotonic() - started:.2f}s",
            flush=True,
        )
        print(
            f"[NOVA TTS] Saved WAV: {os.path.getsize(output_file):,} bytes",
            flush=True,
        )

    def run(self):
        pygame_ready = False
        current_file = None
        completed_normally = False

        try:
            if not self.text or self._stop_event.is_set():
                completed_normally = True
                return

            print("[NOVA TTS] Preparing Pocket TTS speech", flush=True)

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame_ready = True

            current_file = self._create_temp_file(".wav")
            self._generate_pocket_audio(self.text, current_file)

            if self._stop_event.is_set():
                completed_normally = True
                return

            self._validate_audio(current_file)
            pygame.mixer.music.load(current_file)
            pygame.mixer.music.play()
            self.speaking_changed.emit(True)

            print(
                f"[NOVA TTS] Playing {len(self.text)} characters with Pocket TTS",
                flush=True,
            )

            started_at = time.monotonic()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    break

                elapsed = time.monotonic() - started_at
                level = (
                    0.35
                    + 0.25 * abs(math.sin(elapsed * 13.0))
                    + 0.15 * abs(math.sin(elapsed * 21.0))
                )
                self.audio_level.emit(min(level, 1.0))
                time.sleep(0.035)

            completed_normally = True

        except Exception as error:
            print(f"[NOVA TTS ERROR] {error!r}", flush=True)
            self.failed.emit(str(error))

        finally:
            try:
                if pygame_ready:
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
            except Exception:
                pass

            self._remove_file(current_file)
            self.speaking_changed.emit(False)
            self.audio_level.emit(0.0)

            if completed_normally:
                self.completed.emit()

            print("[NOVA TTS] TTS thread stopped", flush=True)
