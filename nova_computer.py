
"""NOVA computer control: allowlisted apps, websites, and folders."""

import os
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse


APP_ALIASES = {
    "메모장": "notepad",
    "notepad": "notepad",
    "계산기": "calculator",
    "계산기 앱": "calculator",
    "calculator": "calculator",
    "calc": "calculator",
    "그림판": "paint",
    "paint": "paint",
    "탐색기": "explorer",
    "파일 탐색기": "explorer",
    "file explorer": "explorer",
}

APP_COMMANDS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "explorer": ["explorer.exe"],
}

WEBSITE_ALIASES = {
    "구글": "https://www.google.com",
    "google": "https://www.google.com",
    "유튜브": "https://www.youtube.com",
    "youtube": "https://www.youtube.com",
    "깃허브": "https://github.com",
    "github": "https://github.com",
    "네이버": "https://www.naver.com",
    "naver": "https://www.naver.com",
    "챗지피티": "https://chatgpt.com",
    "chatgpt": "https://chatgpt.com",
}

FOLDER_ALIASES = {
    "바탕화면": "Desktop",
    "desktop": "Desktop",
    "다운로드": "Downloads",
    "downloads": "Downloads",
    "문서": "Documents",
    "documents": "Documents",
    "내 문서": "Documents",
}


def _normalize(text):
    text = text.strip().lower()
    text = re.sub(r"[.!?,]+$", "", text)
    return re.sub(r"\s+", " ", text)


def _launch_app(app_key):
    command = APP_COMMANDS.get(app_key)

    if command is None:
        return "허용되지 않은 프로그램이야."

    try:
        subprocess.Popen(command, shell=False)
        return f"{app_key} 실행을 요청했어."

    except OSError as error:
        print(f"[NOVA COMPUTER] App launch error: {error}", flush=True)
        return f"프로그램 실행에 실패했어: {error}"


def _open_website(url):
    try:
        opened = webbrowser.open(url, new=2)

        if opened:
            return f"웹사이트를 열었어: {url}"

        return f"브라우저 열기를 요청했지만 성공 여부를 확인하지 못했어: {url}"

    except Exception as error:
        print(f"[NOVA COMPUTER] Browser error: {error}", flush=True)
        return f"웹사이트를 여는 중 오류가 발생했어: {error}"


def _open_folder(folder_key):
    folder_name = FOLDER_ALIASES.get(folder_key)

    if folder_name is None:
        return "허용되지 않은 폴더야."

    folder_path = Path.home() / folder_name

    if not folder_path.is_dir():
        return f"폴더를 찾을 수 없어: {folder_path}"

    try:
        os.startfile(str(folder_path))
        return f"{folder_name} 폴더를 열었어."

    except OSError as error:
        print(f"[NOVA COMPUTER] Folder error: {error}", flush=True)
        return f"폴더를 여는 중 오류가 발생했어: {error}"


def execute_computer_command(user_input):
    """Return a result for recognized commands, or None otherwise."""

    if not isinstance(user_input, str) or not user_input.strip():
        return None

    text = _normalize(user_input)

    # Match requests such as "메모장 열어줘" and "open calculator".
    open_pattern = (
        r"^(?:"
        r"열어줘|열어|열어 줘|실행해줘|실행해 줘|실행해|켜줘|켜 줘|켜|"
        r"열어주세요|실행해주세요|open|launch|start|run"
        r")\s+(.+)$"
    )
    match = re.match(open_pattern, text)

    if match:
        target = match.group(1).strip()
    else:
        # Also support "메모장 열어줘", "유튜브 켜".
        suffix_pattern = (
            r"^(.+?)\s+(?:"
            r"열어줘|열어 줘|열어|실행해줘|실행해 줘|실행해|"
            r"켜줘|켜 줘|켜|열어주세요|실행해주세요"
            r")$"
        )
        match = re.match(suffix_pattern, text)

        if match:
            target = match.group(1).strip()
        else:
            target = None

    if target:
        target = _normalize(target)

        # Allow only explicitly listed apps.
        if target in APP_ALIASES:
            return _launch_app(APP_ALIASES[target])

        # Allow only explicitly listed websites.
        if target in WEBSITE_ALIASES:
            return _open_website(WEBSITE_ALIASES[target])

        # Allow only explicitly listed folders.
        if target in FOLDER_ALIASES:
            return _open_folder(target)

    # Support explicitly requested HTTP(S) URLs only.
    url_match = re.search(r"https?://[^\s]+", text)

    if url_match and re.search(
        r"\b(open|visit|browse|열어|접속|방문)\b|열어|접속|방문",
        text,
    ):
        url = url_match.group(0).rstrip(".,!?;")
        parsed = urlparse(url)

        if (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            return _open_website(url)

        return "안전하지 않거나 올바르지 않은 웹 주소야."

    print(f"[NOVA COMPUTER] Unrecognized command: {user_input!r}", flush=True)
    return None


if __name__ == "__main__":
    # Standalone test; this does not start the NOVA GUI.
    result = execute_computer_command("메모장 열어줘")
    print(result)
