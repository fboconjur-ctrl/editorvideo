"""Armazenamento simples de configurações locais (ex: chave de API do
Pexels), num arquivo JSON na pasta do backend — nunca versionado no git."""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _read() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_pexels_api_key() -> str | None:
    return _read().get("pexels_api_key") or None


def set_pexels_api_key(api_key: str) -> None:
    data = _read()
    data["pexels_api_key"] = api_key
    CONFIG_PATH.write_text(json.dumps(data), encoding="utf-8")
