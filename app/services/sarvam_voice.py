import base64
import os
import io
from flask import current_app
import google.generativeai as genai
from gtts import gTTS

STATE_TO_LANGUAGE = {
    "Karnataka": "kn",
    "Tamil Nadu": "ta",
    "Andhra Pradesh": "te",
    "Telangana": "te",
    "Kerala": "ml",
}

def get_language(state_or_lang: str) -> str:
    valid_langs = ["hi", "kn", "ta", "te", "ml", "mr", "bn", "gu", "or", "pa", "en"]
    if state_or_lang in valid_langs:
        return state_or_lang
    if state_or_lang and '-' in state_or_lang:
        short = state_or_lang.split('-')[0]
        if short in valid_langs:
            return short
    return STATE_TO_LANGUAGE.get(state_or_lang, "hi")

def _get_model():
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-3.0-flash")

def speech_to_text(audio_bytes: bytes, state: str) -> str:
    """Send farmer's voice to Gemini STT, get back crop name as text."""
    model = _get_model()
    prompt = "Transcribe this audio. Output ONLY the transcribed text in the language it is spoken in. Do not include any extra words."
    response = model.generate_content([
        {"mime_type": "audio/wav", "data": audio_bytes},
        prompt
    ])
    return response.text.strip() if response.text else ""

def text_to_speech(text: str, state: str) -> bytes:
    """Convert price text to audio, return raw audio bytes."""
    language = get_language(state)
    try:
        tts = gTTS(text=text, lang=language)
    except ValueError:
        tts = gTTS(text=text, lang="hi")
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()

def analyse_price_fairness(
    crop: str,
    offered_price: float,
    modal_price: float,
    min_price: float,
    max_price: float,
    language: str,
) -> str:
    model = _get_model()
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
    response = model.generate_content(prompt)
    if not response.text:
        return "AI analysis could not be generated at this time."
    return response.text.strip()

def rank_dealers(
    crop: str,
    farmer_city: str,
    dealers: list,
    modal_price: float,
    language: str,
) -> str:
    model = _get_model()
    dealer_lines = "\n".join([
        f"{i+1}. {d['name']} — Phone: {d['phone']}, Address: {d['city']}"
        for i, d in enumerate(dealers[:10])
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
    response = model.generate_content(prompt)
    if not response.text:
        return "AI analysis could not be generated at this time."
    return response.text.strip()

def rank_farmers(
    crop: str,
    dealer_city: str,
    farmers: list,
    modal_price: float,
) -> str:
    model = _get_model()
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
    response = model.generate_content(prompt)
    if not response.text:
        return "AI analysis could not be generated at this time."
    return response.text.strip()