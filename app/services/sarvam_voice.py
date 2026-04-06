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
            "model": "Saaras v3",
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
            "model": "bulbul:v3",
            "enable_preprocessing": True,
        },
        timeout=15,
    )
    response.raise_for_status()
    audio_b64 = response.json().get("audios", [""])[0]
    return base64.b64decode(audio_b64)

def analyse_price_fairness(
    crop: str,
    offered_price: float,
    modal_price: float,
    min_price: float,
    max_price: float,
    language: str,
) -> str:
    """
    Ask Sarvam LLM if the dealer's offered price is fair.
    Returns plain text analysis in the farmer's language.
    """
    api_key = current_app.config.get("SARVAM_API_KEY")

    diff_pct = ((offered_price - modal_price) / modal_price) * 100
    verdict = "good" if diff_pct >= -5 else "bad"

    prompt = f"""
You are an agricultural price advisor helping an Indian farmer.
Today's mandi data for {crop}:
- Modal price: ₹{modal_price}/quintal
- Min price: ₹{min_price}/quintal  
- Max price: ₹{max_price}/quintal

A dealer has offered the farmer ₹{offered_price}/quintal.
The offer is {abs(diff_pct):.1f}% {'above' if diff_pct >= 0 else 'below'} today's modal mandi price.

Give a SHORT 2-3 sentence analysis:
1. Whether this is a {verdict} deal and why
2. What the farmer should do (accept / negotiate / reject)

Respond ONLY in the language code: {language}
Be simple, direct, and speak as if talking to a rural farmer.
Do not use technical jargon.
"""

    response = requests.post(
        "https://api.sarvam.ai/v1/chat/completions",
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": "sarvam-m",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def rank_dealers(
    crop: str,
    farmer_city: str,
    dealers: list,
    modal_price: float,
    language: str,
) -> str:
    """
    Ask Sarvam LLM to rank dealers and explain why.
    dealers: list of dicts with keys: name, price_per_quintal, city, rating, payment_terms
    Returns plain text ranking in farmer's language.
    """
    api_key = current_app.config.get("SARVAM_API_KEY")

    dealer_lines = "\n".join([
        f"{i+1}. {d['name']} — ₹{d['price_per_quintal']}/q, "
        f"located in {d['city']}, rating {d['rating']}/5, "
        f"payment: {d['payment_terms']}"
        for i, d in enumerate(dealers[:10])  # max 10 dealers to LLM
    ])

    prompt = f"""
You are an agricultural marketplace assistant helping an Indian farmer in {farmer_city}.
The farmer wants to sell {crop}. Today's modal mandi price is ₹{modal_price}/quintal.

Here are available dealers:
{dealer_lines}

Rank the TOP 3 dealers for this farmer and explain briefly why each is a good choice.
Consider: price offered vs mandi rate, proximity to farmer, dealer rating, payment terms.

Format your response as:
1. [Dealer name] — [1 sentence reason]
2. [Dealer name] — [1 sentence reason]  
3. [Dealer name] — [1 sentence reason]

Then add one line of overall advice.

Respond ONLY in language code: {language}
Keep it simple for a rural farmer. No jargon.
"""

    response = requests.post(
        "https://api.sarvam.ai/v1/chat/completions",
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": "sarvam-m",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

def rank_farmers(
    crop: str,
    dealer_city: str,
    farmers: list,
    modal_price: float,
) -> str:
    """
    Ask Sarvam LLM to rank farmers for a dealer.
    farmers: list of dicts with keys: name, price_per_quintal, city, quantity, quality, has_transport
    Returns plain text ranking in English (dealer side = English only).
    """
    api_key = current_app.config.get("SARVAM_API_KEY")

    farmer_lines = "\n".join([
        f"{i+1}. {f['name']} — asking ₹{f['price_per_quintal']}/q, "
        f"located in {f['city']}, quantity {f['quantity']} quintals, "
        f"quality: {f['quality']}, has transport: {'Yes' if f['has_transport'] else 'No'}"
        for i, f in enumerate(farmers[:10])
    ])

    prompt = f"""
You are an agricultural marketplace assistant helping a dealer in {dealer_city}.
The dealer wants to buy {crop}. Today's modal mandi price is ₹{modal_price}/quintal.

Here are available farmers:
{farmer_lines}

Rank the TOP 3 farmers for this dealer and explain briefly why each is a good choice.
Consider: asking price vs mandi rate, quantity available, quality grade, whether farmer has transport (saves dealer logistics cost).

Format your response as:
1. [Farmer name] — [1 sentence reason]
2. [Farmer name] — [1 sentence reason]
3. [Farmer name] — [1 sentence reason]

Then add one line of overall advice for the dealer.

Respond in English. Keep it concise and professional.
"""

    response = requests.post(
        "https://api.sarvam.ai/v1/chat/completions",
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": "sarvam-30b",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()