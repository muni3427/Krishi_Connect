// AgriConnect — Voice Assistant JS
// Handles the full mic → STT → TTS flow for the farmer dashboard

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

const micBtn = document.getElementById("micBtn");
const voiceStatus = document.getElementById("voiceStatus");
const audioPlayer = document.getElementById("audioPlayer");

// ── Helpers ──────────────────────────────────────────────────────────────────

function setStatus(message, color = "gray") {
    voiceStatus.textContent = message;
    voiceStatus.className = `text-sm mt-2 text-${color}-600`;
}

function showError(message) {
    setStatus("⚠️ " + message, "red");
    micBtn.textContent = "🎤 Ask price in your language";
    isRecording = false;
}

// ── Step 1: Start / Stop Recording ───────────────────────────────────────────

micBtn.addEventListener("click", async () => {
    if (isRecording) {
        // Stop recording
        mediaRecorder.stop();
        return;
    }

    // Request mic permission
    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        showError("Microphone permission denied. Please allow mic access.");
        return;
    }

    // Start recording
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
        // Stop all mic tracks
        stream.getTracks().forEach(track => track.stop());

        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        await sendToSTT(audioBlob);
    };

    mediaRecorder.start();
    isRecording = true;
    micBtn.textContent = "⏹ Recording... tap to stop";
    setStatus("Listening...", "green");
});

// ── Step 2: Send audio to /farmer/voice/stt ───────────────────────────────────

async function sendToSTT(audioBlob) {
    setStatus("Recognising crop name...", "yellow");
    micBtn.textContent = "🎤 Ask price in your language";
    isRecording = false;

    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");

    let crop;
    try {
        const response = await fetch("/farmer/voice/stt", {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            showError("Could not understand audio. Please try again.");
            return;
        }

        const data = await response.json();
        crop = data.crop;

        if (!crop) {
            showError("Could not detect crop name. Please try again.");
            return;
        }
    } catch (err) {
        showError("Network error while recognising. Please try again.");
        return;
    }

    await sendToTTS(crop);
}

// ── Step 3: Send crop name to /farmer/voice/prices ───────────────────────────

async function sendToTTS(crop) {
    setStatus(`Getting price for ${crop}...`, "yellow");

    let audioBytes;
    try {
        const response = await fetch("/farmer/voice/prices", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ crop: crop }),
        });

        if (!response.ok) {
            showError(`Could not fetch price for "${crop}". Please try again.`);
            return;
        }

        audioBytes = await response.blob();
    } catch (err) {
        showError("Network error while fetching price. Please try again.");
        return;
    }

    // ── Step 4: Play the audio response ──────────────────────────────────────
    const audioURL = URL.createObjectURL(audioBytes);
    audioPlayer.src = audioURL;
    audioPlayer.hidden = false;
    audioPlayer.play();

    setStatus(`Playing price for "${crop}" in your language 🔊`, "green");

    // Clean up blob URL after playback
    audioPlayer.onended = () => {
        URL.revokeObjectURL(audioURL);
        setStatus("Tap the mic to ask again", "gray");
    };
}