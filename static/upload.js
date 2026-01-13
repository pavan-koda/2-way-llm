const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusMsg = document.getElementById('status-msg');
const fileList = document.getElementById('file-list');
const progressContainer = document.getElementById('progress-container');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');

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

    // Reset UI
    statusMsg.textContent = "Starting...";
    dropZone.style.opacity = "0.5";
    progressContainer.style.display = "block";
    progressBar.style.width = "0%";
    progressBar.classList.remove('ingesting');
    progressText.textContent = "0%";
    
    let ingestTimer;

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload', true);

    // Track Upload Progress
    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const percent = (e.loaded / e.total) * 100;
            progressBar.style.width = percent + "%";
            progressText.textContent = `Uploading: ${Math.round(percent)}%`;
            
            // If upload finishes, switch to Ingesting state
            if (percent >= 100) {
                statusMsg.textContent = "Ingesting (Embedding text)...";
                progressBar.classList.add('ingesting');
                let seconds = 0;
                progressText.textContent = "Processing... (0s)";
                ingestTimer = setInterval(() => {
                    seconds++;
                    progressText.textContent = `Processing... (${seconds}s)`;
                }, 1000);
            }
        }
    };

    xhr.onload = () => {
        clearInterval(ingestTimer);
        dropZone.style.opacity = "1";
        progressBar.classList.remove('ingesting');

        if (xhr.status === 200) {
            const data = JSON.parse(xhr.responseText);
            statusMsg.textContent = "✅ Success: " + data.filename;
            progressBar.style.width = "100%";
            progressText.textContent = "Complete!";
            loadFiles();
            setTimeout(() => { progressContainer.style.display = "none"; }, 3000);
        } else {
            statusMsg.textContent = "❌ Error: " + (xhr.responseText || "Upload failed");
            progressContainer.style.display = "none";
        }
    };

    xhr.onerror = () => {
        clearInterval(ingestTimer);
        dropZone.style.opacity = "1";
        statusMsg.textContent = "❌ Network Error";
        progressContainer.style.display = "none";
    };

    xhr.send(formData);
}

// Event Listeners
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => handleUpload(e.target.files[0]));

loadFiles();