const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusMsg = document.getElementById('status-msg');
const fileList = document.getElementById('file-list');

// Load existing documents
async function loadFiles() {
    try {
        const res = await fetch('/api/documents');
        const docs = await res.json();
        fileList.innerHTML = docs.length ? '' : '<div style="padding:10px; color:#666;">No documents found.</div>';
        docs.forEach(d => {
            const div = document.createElement('div');
            div.className = 'file-item';
            div.textContent = "📄 " + d.name;
            fileList.appendChild(div);
        });
    } catch (e) { console.error(e); }
}

// Handle Upload
async function handleUpload(file) {
    if (!file || file.type !== 'application/pdf') {
        statusMsg.textContent = "Error: Only PDF files are allowed.";
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    statusMsg.textContent = "Uploading & Ingesting...";
    dropZone.style.opacity = "0.5";

    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        if (!res.ok) throw new Error(await res.text());
        
        const data = await res.json();
        statusMsg.textContent = "✅ Success: " + data.filename;
        loadFiles();
    } catch (err) {
        statusMsg.textContent = "❌ Error: " + err.message;
    } finally {
        dropZone.style.opacity = "1";
    }
}

// Event Listeners
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => handleUpload(e.target.files[0]));

loadFiles();