let copilotInitialized = false;
let isWaiting = false;

// =========================
// TOGGLE COPILOT PANEL
// =========================
function toggleCopilot() {
    const panel = document.getElementById("copilot-panel");
    panel.classList.toggle("hidden");

    if (!panel.classList.contains("hidden")) {
        initCopilot();
    }
}

// =========================
// INITIALIZE COPILOT
// =========================
function initCopilot() {
    if (copilotInitialized) return;

    copilotInitialized = true;

    addMessage(
        "Hi 👋 I'm LeadForge Copilot. I can analyze your leads, suggest actions, and guide your sales strategy.",
        "ai"
    );

    loadChatHistory();
}

// =========================
// ADD MESSAGE TO CHAT
// =========================
function addMessage(text, sender) {
    const chat = document.getElementById("copilot-chat");

    const msg = document.createElement("div");
    msg.className = sender === "user" ? "msg user" : "msg ai";

    const time = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
    });

    msg.innerHTML = `
        <div class="msg-text">${text}</div>
        <div class="msg-time">${time}</div>
    `;

    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;

    saveChatHistory();
}

// =========================
// SEND MESSAGE
// =========================
async function sendCopilot() {

    if (isWaiting) return;

    const input = document.getElementById("copilot-input");
    const text = input.value.trim();

    if (!text) return;

    addMessage(text, "user");
    input.value = "";

    showTypingIndicator();
    isWaiting = true;

    try {
        const res = await fetch("/copilot", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ message: text })
        });

        if (!res.ok) {
            throw new Error("Server error: " + res.status);
        }

        const data = await res.json();

        removeTypingIndicator();
        addMessage(data.reply, "ai");

    } catch (err) {
        removeTypingIndicator();
        addMessage(
            "⚠️ Copilot error. Please check your connection or server.",
            "ai"
        );
        console.error(err);
    }

    isWaiting = false;
}

// =========================
// ENTER KEY SUPPORT
// =========================
document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("copilot-input");

    if (input) {
        input.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                sendCopilot();
            }
        });
    }
});

// =========================
// TYPING INDICATOR
// =========================
function showTypingIndicator() {
    const chat = document.getElementById("copilot-chat");

    const typing = document.createElement("div");
    typing.id = "typing-indicator";
    typing.className = "msg ai";
    typing.innerText = "Copilot is thinking...";

    chat.appendChild(typing);
    chat.scrollTop = chat.scrollHeight;
}

function removeTypingIndicator() {
    const typing = document.getElementById("typing-indicator");
    if (typing) typing.remove();
}

// =========================
// CHAT MEMORY (SESSION STORAGE)
// =========================
function saveChatHistory() {
    const chat = document.getElementById("copilot-chat");

    sessionStorage.setItem("copilot_chat", chat.innerHTML);
}

function loadChatHistory() {
    const chat = document.getElementById("copilot-chat");

    const saved = sessionStorage.getItem("copilot_chat");

    if (saved) {
        chat.innerHTML = saved;
    }
}