
import pyttsx3

engine = pyttsx3.init("sapi5")

for voice in engine.getProperty("voices"):
    print(f"Name: {voice.name}")
    print(f"ID: {voice.id}")
    print(f"Languages: {voice.languages}")
    print("-" * 40)
