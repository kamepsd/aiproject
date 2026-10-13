import os
from pathlib import Path
import wave

from piper import PiperVoice

# Piper가 사용할 실제 espeak-ng 데이터 경로
site_packages = Path(__file__).parent / ".venv" / "Lib" / "site-packages"
espeak_data = site_packages / "piper" / "espeak-ng-data"

os.environ["ESPEAK_DATA_PATH"] = str(espeak_data)

model_path = Path(__file__).parent / "en_GB-alan-medium.onnx"

voice = PiperVoice.load(str(model_path))

with wave.open("nova_test.wav", "wb") as wav_file:
    voice.synthesize_wav(
        "Hello. I am NOVA. All systems are online.",
        wav_file,
    )

print("음성 생성 완료: nova_test.wav")