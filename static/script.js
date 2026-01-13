const docSelect = document.getElementById('doc-select');
const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const statusLabel = document.getElementById('system-status');
const chatTitle = document.getElementById('chat-title');
const fileInput = document.getElementById('file-upload');
const uploadBtn = document.getElementById('upload-trigger-btn');
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
        const data = await res.json();
        addMessage("AI", data.answer);
    } catch (e) {
        addMessage("System", "Error connecting to server.");
    } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        statusLabel.textContent = "Ready";
        userInput.focus();
    }
}

function addMessage(role, text) {
    const div = document.createElement('div');
    div.className = `message ${role.toLowerCase()}`;
    
    if (role === "AI" && text.includes("Evidence:")) {
        const parts = text.split("Evidence:");
        const explanation = parts[0].replace("Explanation:", "").trim();
        const evidence = parts[1].trim();
        div.innerHTML = `<strong>Explanation:</strong><br>${explanation}<div class="evidence-block"><strong>Evidence:</strong><br>${evidence.replace(/\n/g, '<br>')}</div>`;
    } else {
        div.textContent = text;
    }
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

// Upload Logic
uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
    statusLabel.textContent = "Ingesting...";

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!res.ok) throw new Error(await res.text());
        
        const data = await res.json();
        addMessage("System", `Uploaded & Ingested: ${data.filename}`);
        await loadDocs(); // Refresh list
        
        // Auto-select the new file
        docSelect.value = data.doc_id;
        docSelect.dispatchEvent(new Event('change'));
        
    } catch (err) {
        console.error(err);
        addMessage("System", `Error uploading: ${err.message}`);
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = "+ Upload PDF";
        statusLabel.textContent = "Ready";
        fileInput.value = ''; // Reset
    }
});

sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => { if(e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }});
loadDocs();