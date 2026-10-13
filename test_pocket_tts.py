
import time
import scipy.io.wavfile
from pocket_tts import TTSModel

text = "Hello. I am NOVA, your personal AI assistant."

start = time.perf_counter()
print("Loading Pocket TTS...")

model = TTSModel.load_model()
voice_state = model.get_state_for_audio_prompt("alba")

print(f"Model ready: {time.perf_counter() - start:.2f}s")

start = time.perf_counter()
audio = model.generate_audio(voice_state, text)

scipy.io.wavfile.write(
    "pocket_test.wav",
    model.sample_rate,
    audio.numpy()
)

print(f"Generation time: {time.perf_counter() - start:.2f}s")
print("Saved: pocket_test.wav")
