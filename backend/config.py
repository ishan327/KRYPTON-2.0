"""Paths and persistent settings for the Krypton backend."""
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("KRYPTON_DATA") or ROOT / "data")  # override only for testing
BOOKS_DIR = ROOT / "data" / "books"
INDEX_DIR = ROOT / "data" / "index"
CATALOG_FILE = DATA / "catalog.json"
SETTINGS_FILE = DATA / "settings.json"
EXTENSION_DIR = ROOT / "extension"

HOST = os.environ.get("KRYPTON_HOST", "127.0.0.1")   # the cloud version listens on 0.0.0.0
PORT = int(os.environ.get("KRYPTON_PORT") or os.environ.get("PORT") or 8765)  # Render sets PORT
VERSION = "1.0.0"

MODES = ("groq", "local", "offline")

DEFAULTS = {
    "mode": "groq",               # groq | local | offline
    "groq_api_key": "",
    "groq_model": "openai/gpt-oss-120b",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen2.5:7b",
    "unlock_pass": 2,             # correct answers (out of 3) needed to unlock scrolling
    "agent_workspace": str(ROOT / "workspace"),  # folder the AI agent may read/edit
}


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        if SETTINGS_FILE.exists():
            try:
                self._data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig")))
            except (OSError, ValueError):
                pass
        env_key = os.environ.get("GROQ_API_KEY")
        if env_key and not self._data.get("groq_api_key"):
            self._data["groq_api_key"] = env_key

    def get(self, key):
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key))

    def update(self, changes: dict):
        with self._lock:
            for k, v in changes.items():
                if k in DEFAULTS and v is not None:
                    self._data[k] = v
            DATA.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def public(self) -> dict:
        """Settings safe to send to the extension (API key masked)."""
        with self._lock:
            d = dict(self._data)
        key = d.pop("groq_api_key", "")
        d["groq_key_set"] = bool(key)
        d["groq_key_hint"] = f"{key[:4]}…{key[-4:]}" if len(key) > 10 else ""
        return d


settings = Settings()
