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

def get_language(state_or_lang: str) -> str:
    valid_langs = ["hi-IN", "kn-IN", "ta-IN", "te-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "or-IN", "pa-IN", "en-IN"]
    if state_or_lang in valid_langs:
        return state_or_lang
    
    # Handle two-letter selections from profile
    short_map = {"hi": "hi-IN", "kn": "kn-IN", "ta": "ta-IN", "te": "te-IN", "ml": "ml-IN", "en": "en-IN"}
    if state_or_lang in short_map:
        return short_map[state_or_lang]

    return STATE_TO_LANGUAGE.get(state_or_lang, "hi-IN")  # fallback to state mapping


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
            "model": "bulbul:v2",
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
            "model": "meta-llama-3-8b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        },
        timeout=20,
    )
    response.raise_for_status()
    message = response.json().get("choices", [{}])[0].get("message", {})
    content = message.get("content")
    if not content: return "AI analysis could not be generated at this time."
    return content.strip()


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
        f"{i+1}. {d['name']} — Phone: {d['phone']}, Address: {d['city']}"
        for i, d in enumerate(dealers[:10])  # max 10 dealers to LLM
    ])

    prompt = f"""
You are an agricultural marketplace assistant helping an Indian farmer in {farmer_city}.
The farmer wants to sell {crop}. Today's modal mandi price is ₹{modal_price}/quintal.

Here are available dealers:
{dealer_lines}

List the TOP 3 dealers. Provide EXACTLY one line per dealer. Stop.

Format YOUR ENTIRE RESPONSE EXACTLY like this (NO introductory text, NO extra reasons):
1. [Dealer name], Phone: [phone], Address: [city]
2. [Dealer name], Phone: [phone], Address: [city]
3. [Dealer name], Phone: [phone], Address: [city]

Respond ONLY in language code: {language}.
"""

    response = requests.post(
        "https://api.sarvam.ai/v1/chat/completions",
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": "meta-llama-3-8b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        },
        timeout=20,
    )
    response.raise_for_status()
    message = response.json().get("choices", [{}])[0].get("message", {})
    content = message.get("content")
    if not content: return "AI analysis could not be generated at this time."
    return content.strip()

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
            "model": "meta-llama-3-8b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        },
        timeout=20,
    )
    response.raise_for_status()
    message = response.json().get("choices", [{}])[0].get("message", {})
    content = message.get("content")
    if not content:
        return "AI analysis could not be generated at this time."
    return content.strip()