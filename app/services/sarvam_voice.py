import requests
import base64
from flask import current_app

STATE_TO_LANGUAGE = {
    "Karnataka": "kn-IN",
    "Tamil Nadu": "ta-IN",
    "Andhra Pradesh": "te-IN",
    "Telangana": "te-IN",
    "Kerala": "ml-IN",
}

def get_language(state: str) -> str:
    return STATE_TO_LANGUAGE.get(state, "hi-IN")  # fallback to Hindi


def speech_to_text(audio_bytes: bytes, state: str) -> str:
    """Send farmer's voice to Sarvam STT, get back crop name as text."""
    api_key = current_app.config.get("SARVAM_API_KEY")
    language = get_language(state)

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    response = requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": api_key},
        json={
            "audio": audio_b64,
            "language_code": language,
            "model": "saarika:v2",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("transcript", "").strip()


def text_to_speech(text: str, state: str) -> bytes:
    """Convert price text to audio, return raw audio bytes."""
    api_key = current_app.config.get("SARVAM_API_KEY")
    language = get_language(state)

    response = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": api_key},
        json={
            "text": text,
            "language_code": language,
            "model": "bulbul:v1",
            "enable_preprocessing": True,
        },
        timeout=15,
    )
    response.raise_for_status()
    audio_b64 = response.json().get("audios", [""])[0]
    return base64.b64decode(audio_b64)