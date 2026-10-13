
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from nova_computer import execute_computer_command
from nova_planner import build_computer_plan
from nova_tts import NOVATTSWorker
from nova_ui import NOVAWindow, OrbWidget
from nova_voice import NOVAVoiceWorker


# ============================================================
# Configuration
# ============================================================

load_dotenv(Path(__file__).with_name(".env"))

MODEL = "gemini-3.5-flash-lite"
MEMORY_FILE = Path(__file__).with_name("memory.json")


# ============================================================
# Response formatting
# ============================================================

def clean_nova_response(text: str) -> str:
    """Remove Markdown formatting before displaying or speaking."""

    if not text:
        return ""

    text = re.sub(r"```[a-zA-Z0-9_+-]*\s*", "", text)
    text = text.replace("```", "")

    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)

    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.*?)__", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)
    text = re.sub(r"~~(.*?)~~", r"\1", text, flags=re.DOTALL)

    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# Memory
# ============================================================

def empty_memory():
    return {
        "user_name": "",
        "facts": [],
        "conversation": [],
        "long_term": {
            "identity": {},
            "preferences": {},
            "projects": {},
            "goals": {},
            "notes": {},
        },
    }


def load_memory():
    if not MEMORY_FILE.exists():
        return empty_memory()

    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return empty_memory()

        defaults = empty_memory()

        for key, value in defaults.items():
            if key not in data:
                data[key] = value

        if not isinstance(data["user_name"], str):
            data["user_name"] = ""

        if not isinstance(data["facts"], list):
            data["facts"] = []

        if not isinstance(data["conversation"], list):
            data["conversation"] = []

        if not isinstance(data["long_term"], dict):
            data["long_term"] = {}

        for category, default in defaults["long_term"].items():
            if not isinstance(data["long_term"].get(category), dict):
                data["long_term"][category] = default

        return data

    except (OSError, json.JSONDecodeError) as error:
        print(
            "[NOVA MEMORY] Could not load memory:",
            error,
            flush=True,
        )
        return empty_memory()


def save_memory(memory):
    temporary_file = MEMORY_FILE.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(memory, file, ensure_ascii=False, indent=4)

    os.replace(temporary_file, MEMORY_FILE)


LONG_TERM_CATEGORIES = {
    "identity",
    "preferences",
    "projects",
    "goals",
    "notes",
}


def update_long_term_memory(memory, category, key, value):
    if category not in LONG_TERM_CATEGORIES:
        raise ValueError(f"Invalid memory category: {category}")

    if not isinstance(key, str) or not key.strip():
        raise ValueError("Memory key must not be empty.")

    if not isinstance(value, str) or not value.strip():
        raise ValueError("Memory value must not be empty.")

    memory.setdefault("long_term", {})

    for name in LONG_TERM_CATEGORIES:
        if not isinstance(memory["long_term"].get(name), dict):
            memory["long_term"][name] = {}

    key = key.strip()
    value = value.strip()

    if memory["long_term"][category].get(key) == value:
        return False

    memory["long_term"][category][key] = value
    save_memory(memory)

    return True


def search_long_term_memory(memory, query, limit=5):
    long_term = memory.get("long_term", {})

    if not isinstance(long_term, dict):
        return []

    if not isinstance(query, str) or not query.strip():
        return []

    stop_words = {
        "what", "was", "is", "are", "the", "a", "an",
        "my", "your", "about", "tell", "me", "please",
        "do", "did", "have", "has", "i", "you", "we",
        "it", "this", "that", "how", "can", "could",
        "would", "remember", "검색", "해줘", "찾아",
        "찾아줘", "최신",
    }

    words = [
        word.strip(".,!?;:'\"()[]{}").lower()
        for word in query.split()
    ]

    words = [
        word for word in words
        if word and word not in stop_words
    ]

    results = []

    for category, entries in long_term.items():
        if not isinstance(entries, dict):
            continue

        for key, value in entries.items():
            if not isinstance(value, str):
                continue

            searchable = f"{category} {key} {value}".lower()

            score = sum(
                1 for word in words if word in searchable
            )

            if score:
                results.append({
                    "category": category,
                    "key": key,
                    "value": value,
                    "score": score,
                })

    results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return results[:max(0, limit)]


def extract_memories(client, user_input):
    prompt = f'''Extract useful memories for NOVA. Return ONLY valid JSON:
{{"user_name":"", "facts":[], "long_term":[{{"category":"projects","key":"NOVA","value":"Description"}}]}}
Rules: save only explicitly stated or strongly supported stable facts; never invent information; never save passwords, API keys, or secrets; user_name empty unless explicitly given; allowed categories identity, preferences, projects, goals, notes; do not treat questions or hypotheticals as facts; no Markdown.
User's latest message:
{user_input}'''

    empty = {
        "user_name": "",
        "facts": [],
        "long_term": [],
    }

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )

        response_text = (response.text or "").strip()

        if response_text.startswith("```"):
            lines = response_text.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            response_text = "\n".join(lines).strip()

        data = json.loads(response_text)

        if not isinstance(data, dict):
            return empty

        name = data.get("user_name", "")
        facts = data.get("facts", [])
        candidates = data.get("long_term", [])

        if not isinstance(name, str):
            name = ""

        if not isinstance(facts, list):
            facts = []

        if not isinstance(candidates, list):
            candidates = []

        valid_facts = [
            item.strip()
            for item in facts
            if isinstance(item, str) and item.strip()
        ]

        valid_memories = []

        for item in candidates:
            if not isinstance(item, dict):
                continue

            category = item.get("category")
            key = item.get("key")
            value = item.get("value")

            if category not in LONG_TERM_CATEGORIES:
                continue

            if not all(
                isinstance(entry, str) and entry.strip()
                for entry in (key, value)
            ):
                continue

            if len(key) <= 100 and len(value) <= 1000:
                valid_memories.append({
                    "category": category,
                    "key": key.strip(),
                    "value": value.strip(),
                })

        return {
            "user_name": name.strip(),
            "facts": valid_facts,
            "long_term": valid_memories,
        }

    except Exception as error:
        print(
            "[NOVA MEMORY] Extraction failed:",
            error,
            flush=True,
        )
        return empty


# ============================================================
# Gemini worker
# ============================================================

class AIWorker(QThread):
    finished_response = Signal(str, str, object, bool)
    failed = Signal(str)

    def __init__(
        self,
        client,
        chat,
        user_input,
        memory_snapshot,
        web_search=False,
    ):
        super().__init__()

        self.client = client
        self.chat = chat
        self.user_input = user_input
        self.memory_snapshot = memory_snapshot
        self.web_search = web_search

    def run(self):
        try:
            print("[DEBUG] AIWorker started", flush=True)

            memory = self.memory_snapshot
            recent_history = memory.get("conversation", [])[-10:]

            relevant = search_long_term_memory(
                memory,
                self.user_input,
                limit=5,
            )

            history_lines = []

            for item in recent_history:
                if not isinstance(item, dict):
                    continue

                role = str(item.get("role", "Unknown"))
                text = str(item.get("text", "")).strip()

                if text:
                    history_lines.append(f"{role}: {text}")

            memory_lines = []

            user_name = memory.get("user_name", "")

            if isinstance(user_name, str) and user_name.strip():
                memory_lines.append(
                    f"User's name: {user_name.strip()}"
                )

            facts = memory.get("facts", [])

            if isinstance(facts, list):
                for fact in facts[-20:]:
                    if isinstance(fact, str) and fact.strip():
                        memory_lines.append(f"- {fact.strip()}")

            for item in relevant:
                memory_lines.append(
                    f"- [{item['category']}] "
                    f"{item['key']}: {item['value']}"
                )

            context = f"""
You are NOVA, the user's personal AI assistant.

RESPONSE STYLE:
- Be concise, direct, and natural.
- Answer simple questions in one sentence whenever possible.
- Usually answer in 1–3 sentences.
- Give details only when the user asks or when necessary.
- Avoid unnecessary introductions, repetition, and long lists.
- Answer the user's actual question first.
- Use a casual, intelligent, and respectful tone.
- For simple commands, briefly confirm the action.
- Never sacrifice accuracy for brevity.

MEMORY AND CONVERSATION:
- Use saved memory and conversation history when relevant.
- Answer questions about the user's own projects and previously
  shared information normally.
- Never invent facts.
- If information is unavailable, say so briefly.
- Ask follow-up questions only when essential information is missing.

SAVED MEMORY:
{chr(10).join(memory_lines) if memory_lines else "No relevant saved memory found."}

RECENT CONVERSATION:
{chr(10).join(history_lines) if history_lines else "No recent conversation available."}
""".strip()

            prompt = (
                context
                + "\n\nUser request:\n"
                + self.user_input
            )

            print("[DEBUG] Sending request to Gemini", flush=True)
            start_time = time.perf_counter()

            if self.web_search:
                search_tool = types.Tool(
                    google_search=[types.GoogleSearch()]
                )

                config = types.GenerateContentConfig(
                    tools=[search_tool]
                )

                response = self.client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=config,
                )
            else:
                response = self.chat.send_message(prompt)

            elapsed = time.perf_counter() - start_time

            print(
                f"[DEBUG] Gemini response received in {elapsed:.2f} seconds",
                flush=True,
            )

            answer = (
                (response.text or "").strip()
                or "답변을 생성하지 못했어. 다시 말해 줘."
            )

            memory_keywords = [
                "기억해",
                "기억해줘",
                "저장해",
                "저장해줘",
                "앞으로는",
                "내 이름은",
                "remember this",
                "remember that",
                "save this",
                "my name is",
            ]

            should_extract = any(
                keyword in self.user_input.lower()
                for keyword in memory_keywords
            )

            if not self.web_search and should_extract:
                print(
                    "[NOVA MEMORY] Extracting memory...",
                    flush=True,
                )

                extracted = extract_memories(
                    self.client,
                    self.user_input,
                )
            else:
                extracted = {
                    "user_name": "",
                    "facts": [],
                    "long_term": [],
                }

            self.finished_response.emit(
                self.user_input,
                answer,
                extracted,
                self.web_search,
            )

        except Exception as error:
            print(
                f"[NOVA WORKER ERROR] {error!r}",
                flush=True,
            )
            self.failed.emit(str(error))


# ============================================================
# Main NOVA controller
# ============================================================

class NOVAApp(QObject):
    def __init__(self, app):
        super().__init__()

        self.app = app
        self.memory = load_memory()

        self.client = None
        self.chat = None

        self.worker = None
        self.tts_worker = None
        self.voice_worker = None

        self.busy = False
        self.shutting_down = False
        self.awaiting_followup = False

        self.window = NOVAWindow()
        self.orb = OrbWidget(large=False)

        # Connect the existing memory data to the archive viewer.
        self.window.set_memory_archive(
            memory_file=MEMORY_FILE,
            memory_provider=lambda: self.memory,
        )

        self.position_small_orb()

        self.orb.clicked.connect(self.open_window)
        self.window.minimized_to_orb.connect(self.show_small_orb)
        self.window.search_requested.connect(self.search_web)
        self.window.text_submitted.connect(self.handle_text_command)

        try:
            api_key = os.getenv("GEMINI_API_KEY")

            if not api_key:
                raise RuntimeError(
                    ".env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다."
                )

            self.client = genai.Client(api_key=api_key)
            self.chat = self.client.chats.create(model=MODEL)

            self.window.set_status("WAITING FOR NOVA")

        except Exception as error:
            print(
                "[NOVA] Gemini initialization failed:",
                error,
                flush=True,
            )
            self.window.set_status("GEMINI OFFLINE")

        self.window.hide()
        self.orb.show()
        self.orb.raise_()

        self.start_voice_worker()

    # --------------------------------------------------------
    # Voice input
    # --------------------------------------------------------

    def start_voice_worker(self):
        if self.shutting_down:
            return

        self.voice_worker = NOVAVoiceWorker()

        self.voice_worker.status_changed.connect(
            self.on_voice_status
        )

        self.voice_worker.transcript_ready.connect(
            self.handle_voice_command
        )

        self.voice_worker.error.connect(
            self.on_voice_error
        )

        self.voice_worker.start()

        print("[NOVA VOICE] Voice worker started", flush=True)

    def set_status(self, text):
        """Synchronize the status of the main window and orb."""
        if self.shutting_down:
            return

        if hasattr(self, "window") and self.window is not None:
            self.window.set_status(text)

        if hasattr(self, "orb") and self.orb is not None:
            self.orb.set_status(text)

    def on_voice_status(self, status):
        print(f"[NOVA VOICE] Status: {status}", flush=True)
        self.set_status(status)

    def on_voice_error(self, message):
        print(f"[NOVA VOICE] {message}", flush=True)

        if not self.shutting_down:
            self.set_status("VOICE ERROR")

    def set_voice_listening(self, enabled):
        if self.shutting_down:
            return

        if self.voice_worker is not None:
            try:
                self.voice_worker.set_listening_enabled(enabled)
            except RuntimeError as error:
                print(
                    "[NOVA VOICE] Listening state error:",
                    error,
                    flush=True,
                )

    def handle_voice_command(self, text):
        query, is_search = self.parse_search_command(text)
        self.process_request(query, is_search=is_search)

    def handle_text_command(self, text):
        query, is_search = self.parse_search_command(text)
        self.process_request(query, is_search=is_search)

    @staticmethod
    def parse_search_command(text):
        original = text.strip()

        patterns = [
            r"^(?:검색해 ?줘|검색해|검색|찾아 ?줘|찾아봐|인터넷에서 찾아 ?줘)\s*(.*)$",
            r"^(?:search(?: the web)? for|search for|google)\s*(.*)$",
        ]

        for pattern in patterns:
            match = re.match(
                pattern,
                original,
                flags=re.IGNORECASE,
            )

            if match:
                query = match.group(1).strip(" \t:,.!?")
                return (query or original), True

        return original, False

    # --------------------------------------------------------
    # Window management
    # --------------------------------------------------------

    def open_memory_hologram(self):
        if self.shutting_down:
            return

        self.open_window()
        self.window.show_memory_archive()

    def position_small_orb(self):
        """Keep the small hologram at the right-center of the screen."""
        if self.shutting_down or self.orb is None:
            return

        screen = self.orb.screen() or QGuiApplication.primaryScreen()

        if screen is None:
            return

        available = screen.availableGeometry()

        x = available.right() - self.orb.width() - 24
        y = available.top() + (
            available.height() - self.orb.height()
        ) // 2

        self.orb.move(x, y)
        self.orb.raise_()

    def open_window(self):
        if self.shutting_down:
            return

        self.position_small_orb()

        # Keep the small hologram visible.
        self.orb.show()
        self.orb.raise_()

        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def show_small_orb(self):
        if self.shutting_down:
            return

        self.window.hide()

        self.position_small_orb()
        self.orb.show()
        self.orb.raise_()

    def search_web(self, query):
        self.process_request(
            query.strip(),
            is_search=True,
        )

    # --------------------------------------------------------
    # Request processing
    # --------------------------------------------------------

    def process_request(self, user_input, is_search=False):
        if self.busy or self.shutting_down:
            return

        user_input = user_input.strip()

        if not user_input:
            self.set_voice_listening(True)
            return

        # 1. Open the memory archive for supported English commands.
        normalized = user_input.lower().strip().rstrip(".!? ")

        memory_commands = {
            "show me your memory",
            "show me your memories",
            "show me my memory",
            "show your memory",
            "open memory",
            "open memory archive",
            "show memory",
            "memory hologram",
        }

        if not is_search and normalized in memory_commands:
            self.awaiting_followup = False
            self.open_memory_hologram()
            self.start_speech("Opening the memory archive.")
            return

        # 2. Plan and execute supported multi-step computer tasks.
        plan = build_computer_plan(user_input)

        if plan is not None:
            results = []

            for command in plan:
                result = execute_computer_command(command)

                if result is None:
                    result = f"명령을 인식하지 못했어: {command}"

                results.append(result)

            report = "\n".join(results)

            print(
                f"[NOVA PLANNER]\n{report}",
                flush=True,
            )

            self.awaiting_followup = False
            self.start_speech(report)
            return

        # 3. Execute a supported single computer command.
        computer_result = execute_computer_command(user_input)

        if computer_result is not None:
            print(
                f"[NOVA COMPUTER] {computer_result}",
                flush=True,
            )

            self.awaiting_followup = False
            self.start_speech(computer_result)
            return

        # 4. Handle local memory commands.
        if user_input.lower() == "/memory":
            summary = (
                f"Saved name: {self.memory.get('user_name') or 'Unknown'}. "
                f"Saved facts: {len(self.memory.get('facts', []))}."
            )

            self.awaiting_followup = False
            self.start_speech(summary)
            return

        if user_input.lower().startswith("/remember "):
            fact = user_input[len("/remember "):].strip()

            if not fact:
                self.awaiting_followup = False
                self.start_speech(
                    "Tell me what you want me to remember."
                )
                return

            facts = self.memory.setdefault("facts", [])

            if fact not in facts:
                facts.append(fact)

            try:
                save_memory(self.memory)
                self.awaiting_followup = False
                self.start_speech("Got it. I'll remember that.")
            except OSError as error:
                print(
                    "[NOVA MEMORY] Save failed:",
                    error,
                    flush=True,
                )
                self.awaiting_followup = False
                self.start_speech(
                    "I couldn't save that memory to disk."
                )

            return

        # 5. Send remaining requests to Gemini.
        if self.client is None or self.chat is None:
            self.set_status("GEMINI OFFLINE - CHECK API KEY")
            self.set_voice_listening(True)
            return

        self.set_voice_listening(False)
        self.busy = True

        self.window.search_button.setEnabled(False)
        self.window.set_input_enabled(False)
        self.set_status(
            "SEARCHING THE WEB" if is_search else "THINKING"
        )

        self.orb.set_active(True)

        try:
            snapshot = json.loads(
                json.dumps(self.memory, ensure_ascii=False)
            )

            worker = AIWorker(
                self.client,
                self.chat,
                user_input,
                snapshot,
                web_search=is_search,
            )

            self.worker = worker

            worker.finished_response.connect(self.on_response)
            worker.failed.connect(self.on_error)

            worker.finished.connect(
                lambda w=worker: self.on_ai_thread_finished(w)
            )

            worker.finished.connect(worker.deleteLater)

            print("[DEBUG] Starting AIWorker", flush=True)
            worker.start()

        except Exception as error:
            self.on_error(str(error))

    # --------------------------------------------------------
    # Gemini response and memory updates
    # --------------------------------------------------------

    def on_ai_thread_finished(self, worker):
        print("[DEBUG] AIWorker thread stopped", flush=True)

        if worker is self.worker:
            self.worker = None

    def on_response(self, user_input, answer, extracted, is_search):
        if self.shutting_down:
            return

        answer = clean_nova_response(answer)

        if not answer:
            answer = "I couldn't generate a response. Please try again."

        if isinstance(extracted, dict):
            name = extracted.get("user_name", "")

            if isinstance(name, str) and name.strip():
                self.memory["user_name"] = name.strip()

            facts = extracted.get("facts", [])

            if isinstance(facts, list):
                saved = self.memory.setdefault("facts", [])

                for fact in facts:
                    if (
                        isinstance(fact, str)
                        and fact.strip()
                        and fact.strip() not in saved
                    ):
                        saved.append(fact.strip())

            for item in extracted.get("long_term", []):
                if not isinstance(item, dict):
                    continue

                try:
                    update_long_term_memory(
                        self.memory,
                        item.get("category"),
                        item.get("key"),
                        item.get("value"),
                    )

                except (ValueError, OSError) as error:
                    print(
                        "[NOVA MEMORY] Save failed:",
                        error,
                        flush=True,
                    )

        history = self.memory.setdefault("conversation", [])

        history.extend([
            {
                "role": "User",
                "text": ("Search: " if is_search else "") + user_input,
            },
            {
                "role": "NOVA",
                "text": answer,
            },
        ])

        self.memory["conversation"] = history[-100:]

        try:
            save_memory(self.memory)
        except OSError as error:
            print(
                "[NOVA MEMORY] Conversation save failed:",
                error,
                flush=True,
            )

        self.awaiting_followup = answer.rstrip().endswith("?")

        self.start_speech(answer)

    # --------------------------------------------------------
    # Text-to-speech
    # --------------------------------------------------------

    def start_speech(self, text, keep_busy=True):
        if self.shutting_down:
            return

        if self.tts_worker is not None:
            try:
                if self.tts_worker.isRunning():
                    print(
                        "[NOVA TTS] Duplicate speech request ignored",
                        flush=True,
                    )
                    return
            except RuntimeError:
                self.tts_worker = None

        self.set_voice_listening(False)
        self.busy = True

        self.window.search_button.setEnabled(False)
        self.window.set_input_enabled(False)
        self.set_status("SPEAKING")

        self.tts_worker = NOVATTSWorker(text)
        worker = self.tts_worker

        worker.speaking_changed.connect(
            self.on_speaking_changed
        )

        worker.audio_level.connect(
            self.on_audio_level
        )

        worker.completed.connect(
            self.on_tts_completed
        )

        worker.failed.connect(
            self.on_tts_failed
        )

        worker.finished.connect(
            lambda w=worker: self.on_tts_thread_finished(w)
        )

        worker.finished.connect(worker.deleteLater)

        worker.start()

    def on_tts_thread_finished(self, worker):
        print("[NOVA TTS] TTS thread stopped", flush=True)

        if worker is self.tts_worker:
            self.tts_worker = None

    def on_speaking_changed(self, speaking):
        if self.shutting_down:
            return

        self.window.set_speaking(speaking)
        self.orb.set_speaking(speaking)

        if speaking:
            self.set_status("SPEAKING")

    def on_audio_level(self, level):
        if self.shutting_down:
            return

        self.window.set_audio_level(level)
        self.orb.set_audio_level(level)

    def on_tts_completed(self):
        self.finish_request()

    def on_tts_failed(self, message):
        print("[NOVA TTS] Failed:", message, flush=True)
        self.finish_request()

    # --------------------------------------------------------
    # Error and request completion
    # --------------------------------------------------------

    def on_error(self, message):
        print("[NOVA ERROR]", message, flush=True)

        if self.shutting_down:
            return

        self.set_status("REQUEST FAILED")

        self.busy = False

        self.window.search_button.setEnabled(True)
        self.window.set_input_enabled(True)

        self.window.set_speaking(False)
        self.orb.set_speaking(False)
        self.orb.set_active(False)

        self.awaiting_followup = False
        self.set_voice_listening(True)

    def finish_request(self):
        if self.shutting_down:
            return

        self.busy = False

        self.window.search_button.setEnabled(True)
        self.window.set_input_enabled(True)

        self.window.set_speaking(False)
        self.orb.set_speaking(False)
        self.orb.set_active(False)

        if self.awaiting_followup:
            self.awaiting_followup = False

            self.set_status("LISTENING FOR ANSWER")

            if self.voice_worker is not None:
                self.voice_worker.start_followup_listening()
                return

        self.set_status("WAITING FOR NOVA")
        self.set_voice_listening(True)

    # --------------------------------------------------------
    # Shutdown
    # --------------------------------------------------------

    def shutdown(self):
        if self.shutting_down:
            return

        self.shutting_down = True
        print("[NOVA] Shutdown requested", flush=True)

        # Stop voice recognition first.
        voice_worker = self.voice_worker

        if voice_worker is not None:
            try:
                voice_worker.stop()

                if voice_worker.isRunning():
                    voice_worker.wait()

                self.voice_worker = None

            except RuntimeError as error:
                print(
                    "[NOVA] Voice shutdown warning:",
                    error,
                    flush=True,
                )

        # Wait for active AI and TTS workers.
        for attribute in ("worker", "tts_worker"):
            worker = getattr(self, attribute, None)

            if worker is None:
                continue

            try:
                if worker.isRunning():
                    worker.wait()

                setattr(self, attribute, None)

            except RuntimeError as error:
                print(
                    f"[NOVA] {attribute} cleanup warning: {error}",
                    flush=True,
                )
                setattr(self, attribute, None)

        print("[NOVA] Shutdown complete", flush=True)


# ============================================================
# Application entry point
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NOVA")

    nova = NOVAApp(app)
    app.nova_controller = nova

    app.aboutToQuit.connect(nova.shutdown)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
