const docSelect = document.getElementById('doc-select');
const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const statusLabel = document.getElementById('system-status');
const chatTitle = document.getElementById('chat-title');
let currentDocId = null;

async function loadDocs() {
    try {
        const res = await fetch('/api/documents');
        const docs = await res.json();
        docSelect.innerHTML = '<option value="" disabled selected>Select a Document</option>';
        docs.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.id;
            opt.textContent = d.name;
            docSelect.appendChild(opt);
        });
    } catch (e) { console.error(e); statusLabel.textContent = "Error loading docs"; }
}

docSelect.addEventListener('change', (e) => {
    currentDocId = e.target.value;
    chatTitle.textContent = e.target.options[e.target.selectedIndex].text;
    chatHistory.innerHTML = '';
    addMessage("System", `Document loaded. Ask a question.`);
});

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || !currentDocId) return;
    
    addMessage("User", text);
    userInput.value = '';
    userInput.disabled = true;
    sendBtn.disabled = true;
    statusLabel.textContent = "Thinking...";

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ doc_id: currentDocId, query: text })
        });
        
        // Create a placeholder message for the AI
        const aiDiv = addMessage("AI", "");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";

        // Read the stream
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            fullText += chunk;
            aiDiv.textContent = fullText; // Display raw text while streaming
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        // Apply formatting (Bold, Evidence, Newlines) after stream finishes
        if (fullText.includes("Evidence:")) {
            const parts = fullText.split("Evidence:");
            let explanation = parts[0].replace("Explanation:", "").trim();
            const evidence = parts[1].trim();
            explanation = formatText(explanation);
            aiDiv.innerHTML = `<strong>Explanation:</strong><br>${explanation}<div class="evidence-block"><strong>Evidence:</strong><br>${formatText(evidence)}</div>`;
        } else {
            aiDiv.innerHTML = formatText(fullText);
        }

    } catch (e) {
        addMessage("System", "Error connecting to server.");
    } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        statusLabel.textContent = "Ready";
        userInput.focus();
    }
}

function formatText(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br>");
}

function addMessage(role, text) {
    const div = document.createElement('div');
    div.className = `message ${role.toLowerCase()}`;
    
    if (role === "AI" && text.includes("Evidence:")) {
        const parts = text.split("Evidence:");
        let explanation = parts[0].replace("Explanation:", "").trim();
        const evidence = parts[1].trim();
        explanation = formatText(explanation);
        div.innerHTML = `<strong>Explanation:</strong><br>${explanation}<div class="evidence-block"><strong>Evidence:</strong><br>${formatText(evidence)}</div>`;
    } else {
        div.textContent = text;
    }
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return div;
}

sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => { if(e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }});
loadDocs();