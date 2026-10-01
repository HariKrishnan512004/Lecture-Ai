let selectedFile = null;

document.addEventListener('DOMContentLoaded', function() {
    initMenuHandlers();
    initUploadHandlers();
    initRecordingHandlers();
    initYoutubeHandlers();
    loadUserName();
});

function loadUserName() {
    const userName = document.getElementById('userName');
    userName.textContent = sessionStorage.getItem('username') || 'User';
}

// Menu handlers
function initMenuHandlers() {
    const menuItems = document.querySelectorAll('.menu-item');
    menuItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = item.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById(tabName + '-tab').classList.add('active');

    document.querySelectorAll('.menu-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
}

// Upload handlers
function initUploadHandlers() {
    const uploadBox = document.getElementById('uploadBox');
    const fileInput = document.getElementById('fileInput');
    const processBtn = document.getElementById('processBtn');

    uploadBox.addEventListener('click', () => fileInput.click());

    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.classList.add('dragover');
    });

    uploadBox.addEventListener('dragleave', () => {
        uploadBox.classList.remove('dragover');
    });

    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.classList.remove('dragover');
        selectedFile = e.dataTransfer.files[0];
        processBtn.disabled = false;
        const p = document.createElement('p');
        p.style.color = '#00d4ff';
        p.style.marginTop = '10px';
        p.textContent = '✓ ' + selectedFile.name + ' selected';
        uploadBox.appendChild(p);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files[0]) {
            selectedFile = e.target.files[0];
            processBtn.disabled = false;
            const p = document.createElement('p');
            p.style.color = '#00d4ff';
            p.style.marginTop = '10px';
            p.textContent = '✓ ' + selectedFile.name + ' selected';
            uploadBox.appendChild(p);
        }
    });

    processBtn.addEventListener('click', () => {
        if (selectedFile) {
            handleFileUpload(selectedFile);
        }
    });
}

function handleFileUpload(file) {
    const formData = new FormData();
    formData.append('file', file);

    showLoading();
    closeResults();

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        hideLoading();
        displayResults(data);
    })
    .catch(err => {
        hideLoading();
        showError('File upload failed: ' + err.message);
    });
}

// Recording handlers
let mediaRecorder;
let audioChunks = [];
let recordingStartTime;

function initRecordingHandlers() {
    const recordBtn = document.getElementById('recordBtn');
    const stopBtn = document.getElementById('stopBtn');
    const playBtn = document.getElementById('playBtn');
    const uploadRecordBtn = document.getElementById('uploadRecordBtn');

    recordBtn.addEventListener('click', startRecording);
    stopBtn.addEventListener('click', stopRecording);
    playBtn.addEventListener('click', playRecording);
    uploadRecordBtn.addEventListener('click', uploadRecording);
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        recordingStartTime = Date.now();

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = () => {
            stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();

        document.getElementById('recordBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;
        document.getElementById('recordTimer').textContent = '00:00';

        updateTimer();
        document.getElementById('recordingInfo').innerHTML = '<p style="color:#00d4ff;">🔴 Recording...</p>';
    } catch (err) {
        showError('Microphone access denied: ' + err.message);
    }
}

function stopRecording() {
    mediaRecorder.stop();
    document.getElementById('recordBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('playBtn').disabled = false;
    document.getElementById('uploadRecordBtn').disabled = false;

    const duration = Math.round((Date.now() - recordingStartTime) / 1000);
    document.getElementById('recordingInfo').innerHTML = `
        <p style="color:#00d4ff; margin-top:10px;">✓ Recording saved (${duration}s)</p>
    `;
}

function updateTimer() {
    if (!mediaRecorder || mediaRecorder.state === 'inactive') return;

    const elapsed = Math.round((Date.now() - recordingStartTime) / 1000);
    const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const secs = String(elapsed % 60).padStart(2, '0');
    document.getElementById('recordTimer').textContent = `${mins}:${secs}`;

    setTimeout(updateTimer, 100);
}

function playRecording() {
    if (audioChunks.length === 0) return;

    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    audio.play();
}

function uploadRecording() {
    if (audioChunks.length === 0) return;

    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.wav');

    showLoading();
    closeResults();

    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        hideLoading();
        displayResults(data);
    })
    .catch(err => {
        hideLoading();
        showError('Recording upload failed: ' + err.message);
    });
}

// YouTube handlers
function initYoutubeHandlers() {
    const processBtn = document.getElementById('processYoutubeBtn');
    processBtn.addEventListener('click', processYoutube);
}

function processYoutube() {
    const url = document.getElementById('youtubeUrl').value.trim();

    if (!url) {
        showError('Please enter a YouTube URL');
        return;
    }

    const btn = document.getElementById('processYoutubeBtn');
    btn.classList.add('loading');

    showLoading();
    closeResults();

    fetch('/youtube', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url })
    })
    .then(res => res.json())
    .then(data => {
        btn.classList.remove('loading');
        hideLoading();
        displayResults(data);
    })
    .catch(err => {
        btn.classList.remove('loading');
        hideLoading();
        showError('YouTube processing failed: ' + err.message);
    });
}

// Display results
function displayResults(data) {
    document.getElementById('transcriptContent').textContent = data.transcript || 'No transcript available';
    document.getElementById('summaryContent').textContent = data.summary || 'No summary available';

    const keyPointsList = document.getElementById('keyPointsList');
    keyPointsList.innerHTML = '';
    if (data.key_points && data.key_points.length > 0) {
        data.key_points.forEach((point) => {
            const li = document.createElement('li');
            li.textContent = point;
            keyPointsList.appendChild(li);
        });
    } else {
        keyPointsList.innerHTML = '<li>No key points extracted</li>';
    }

    const assignmentsList = document.getElementById('assignmentsList');
    assignmentsList.innerHTML = '';
    if (data.assignments && data.assignments.length > 0) {
        data.assignments.forEach((assignment) => {
            const li = document.createElement('li');
            li.textContent = assignment;
            assignmentsList.appendChild(li);
        });
    } else {
        assignmentsList.innerHTML = '<li>No assignments found</li>';
    }

    const topicsContent = document.getElementById('topicsContent');
    if (data.topics && data.topics.length > 0) {
        let topicsHtml = '';
        data.topics.forEach((topic) => {
            topicsHtml += `<div style="margin:10px 0; padding:10px; background:rgba(0,212,255,0.1); border-radius:5px;">
                <strong>${topic.name}</strong> — words: ${topic.words.join(', ')} (docs: ${topic.n_docs})
            </div>`;
        });
        topicsContent.innerHTML = topicsHtml;
    } else {
        topicsContent.innerHTML = '<p>No topics detected</p>';
    }

    document.getElementById('resultsContainer').style.display = 'block';
}

function closeResults() {
    document.getElementById('resultsContainer').style.display = 'none';
}

function showLoading() {
    document.getElementById('loadingSpinner').classList.add('show');
}

function hideLoading() {
    document.getElementById('loadingSpinner').classList.remove('show');
}

function showError(message) {
    const toast = document.getElementById('errorToast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => {
        toast.classList.remove('show');
    }, 5000);
}