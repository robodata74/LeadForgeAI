let copilotInitialized = false;
let isWaiting = false;

// =========================
// SAFE ELEMENT CHECK
// =========================
function getEl(id) {
    return document.getElementById(id);
}

// =========================
// TOGGLE COPILOT PANEL (SAFE)
// =========================
function toggleCopilot() {
    const panel = getEl("copilot-panel");

    if (!panel) return;

    panel.classList.toggle("hidden");

    if (!panel.classList.contains("hidden")) {
        initCopilot();
    }
}

// =========================
// INIT COPILOT (SAFE MODE)
// =========================
function initCopilot() {
    if (copilotInitialized) return;

    const chat = getEl("copilot-chat");
    if (!chat) return;

    copilotInitialized = true;

    addMessage(
        "Hi 👋 I'm LeadForge Copilot. I can help you analyze leads and improve sales.",
        "ai"
    );

    loadChatHistory();
}

// =========================
// ADD MESSAGE (SAFE)
// =========================
function addMessage(text, sender) {
    const chat = getEl("copilot-chat");
    if (!chat) return;

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
// SEND MESSAGE (HARD SAFE)
// =========================
async function sendCopilot() {

    if (isWaiting) return;

    const input = getEl("copilot-input");
    const chat = getEl("copilot-chat");

    if (!input || !chat) return;

    const text = input.value.trim();
    if (!text) return;

    addMessage(text, "user");
    input.value = "";

    showTypingIndicator();
    isWaiting = true;

    try {
        const res = await fetch("/copilot", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ message: text })
        });

        const data = await res.json();

        removeTypingIndicator();
        addMessage(data.reply || "No response", "ai");

    } catch (err) {
        console.error(err);
        removeTypingIndicator();
        addMessage("⚠️ Copilot error (server issue).", "ai");
    }

    isWaiting = false;
}

// =========================
// ENTER KEY SAFE
// =========================
document.addEventListener("DOMContentLoaded", function () {
    const input = getEl("copilot-input");

    if (!input) return;

    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            sendCopilot();
        }
    });
});

// =========================
// TYPING INDICATOR SAFE
// =========================
function showTypingIndicator() {
    const chat = getEl("copilot-chat");
    if (!chat) return;

    const typing = document.createElement("div");
    typing.id = "typing-indicator";
    typing.className = "msg ai";
    typing.innerText = "Thinking...";

    chat.appendChild(typing);
}

function removeTypingIndicator() {
    const typing = getEl("typing-indicator");
    if (typing) typing.remove();
}

// =========================
// CHAT MEMORY SAFE
// =========================
function saveChatHistory() {
    const chat = getEl("copilot-chat");
    if (!chat) return;

    try {
        sessionStorage.setItem("copilot_chat", chat.innerHTML);
    } catch (e) {}
}

function loadChatHistory() {
    const chat = getEl("copilot-chat");
    if (!chat) return;

    try {
        const saved = sessionStorage.getItem("copilot_chat");
        if (saved) {
            chat.innerHTML = saved;
        }
    } catch (e) {}
}