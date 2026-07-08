document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const promptInput = document.getElementById('prompt-input');
    const chatHistory = document.getElementById('chat-history');
    const sendButton = document.getElementById('send-button');
    const loginOverlay = document.getElementById('login-overlay');
    const appContainer = document.getElementById('app-container');
    const userProfile = document.getElementById('user-profile');
    const logoutBtn = document.getElementById('logout-btn');
    const sidebarHistory = document.getElementById('sidebar-history');
    const newChatBtn = document.getElementById('new-chat-btn');
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');

    const authError = document.getElementById('auth-error');
    const usernameDisplay = document.getElementById('username-display');

    let currentToken = localStorage.getItem('animatrix_token');
    let currentUsername = localStorage.getItem('animatrix_username');

    // --- Mobile Menu ---
    if(mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }

    // --- Authentication ---
    function updateUIBasedOnAuth() {
        if (currentToken) {
            loginOverlay.style.display = 'none';
            appContainer.style.display = 'flex';
            usernameDisplay.textContent = currentUsername || 'User';
            fetchHistory();
        } else {
            loginOverlay.style.display = 'flex';
            appContainer.style.display = 'none';
            resetChatView();
        }
    }

    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('animatrix_token');
        localStorage.removeItem('animatrix_username');
        currentToken = null;
        updateUIBasedOnAuth();
    });

    function showAuthError(message) {
        authError.textContent = message;
        authError.style.display = 'block';
    }

    window.handleGoogleCredentialResponse = async (response) => {
        try {
            authError.style.display = 'none';
            const res = await fetch('http://localhost:8000/api/google-login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ credential: response.credential })
            });

            if (res.ok) {
                const resData = await res.json();
                currentToken = resData.access_token;
                currentUsername = resData.username;
                localStorage.setItem('animatrix_token', currentToken);
                localStorage.setItem('animatrix_username', currentUsername);
                updateUIBasedOnAuth();
            } else {
                const errData = await res.json();
                showAuthError(errData.detail || "Google Authentication failed.");
            }
        } catch (error) {
            showAuthError("Could not connect to backend.");
        }
    };

    // --- History Loading ---
    async function fetchHistory() {
        try {
            const response = await fetch('http://localhost:8000/api/history', {
                headers: { 'Authorization': `Bearer ${currentToken}` }
            });
            if (response.ok) {
                const tasks = await response.json();
                sidebarHistory.innerHTML = ''; // Clear current list
                tasks.forEach(task => {
                    const btn = document.createElement('button');
                    btn.className = 'history-item';
                    btn.textContent = task.prompt;
                    btn.onclick = () => loadPastChat(task, btn);
                    sidebarHistory.appendChild(btn);
                });
            }
        } catch (error) {
            console.error("Could not fetch history", error);
        }
    }

    function resetChatView() {
        chatHistory.innerHTML = `
            <div class="message assistant-message" id="welcome-message">
                <div class="avatar">A</div>
                <div class="content">
                    <p>Hi! I'm Animatrix. Tell me what kind of animation you'd like to create today.</p>
                </div>
            </div>
        `;
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
    }

    newChatBtn.addEventListener('click', () => {
        resetChatView();
        if(window.innerWidth <= 768) sidebar.classList.remove('open');
    });

    function loadPastChat(task, buttonElement) {
        // Clear active states
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
        if(buttonElement) buttonElement.classList.add('active');

        // Render chat
        chatHistory.innerHTML = '';
        appendMessage('user', task.prompt);
        if (task.status === 'completed') {
            appendVideoMessage('assistant', `Here is your past animation:`, "http://localhost:8000" + task.video_url, task.code);
        } else if (task.status === 'failed') {
            appendMessage('assistant', `Error: ${task.error || 'Task failed.'}`);
        } else {
            appendMessage('assistant', `Status: ${task.status}...`);
        }

        if(window.innerWidth <= 768) sidebar.classList.remove('open');
    }

    updateUIBasedOnAuth(); // Initial check

    // --- Chat Input ---
    promptInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value.trim() === '') {
            sendButton.disabled = true;
        } else {
            sendButton.disabled = false;
        }
    });

    promptInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (this.value.trim() !== '') {
                chatForm.dispatchEvent(new Event('submit'));
            }
        }
    });

    // --- Task Polling ---
    async function pollTaskStatus(taskId, loadingId) {
        const intervalId = setInterval(async () => {
            try {
                const response = await fetch(`http://localhost:8000/api/tasks/${taskId}`);
                if (response.ok) {
                    const task = await response.json();
                    if (task.status === "completed") {
                        clearInterval(intervalId);
                        removeLoading(loadingId);
                        appendVideoMessage('assistant', `Here is the animation you requested:`, "http://localhost:8000" + task.video_url, task.code);
                        fetchHistory(); // Refresh sidebar history
                    } else if (task.status === "failed") {
                        clearInterval(intervalId);
                        removeLoading(loadingId);
                        appendMessage('assistant', `Error: ${task.error}`);
                        fetchHistory(); // Refresh sidebar history
                    }
                }
            } catch (error) {
                console.error("Polling error", error);
            }
        }, 2000); // Check every 2 seconds
    }

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const prompt = promptInput.value.trim();
        if (!prompt) return;

        // If we are looking at an old chat and send a new prompt, clear the screen first!
        const hasWelcome = document.getElementById('welcome-message');
        const activeHistory = document.querySelector('.history-item.active');
        if(!hasWelcome && activeHistory) {
            resetChatView(); // start fresh
        }
        
        // Remove welcome message if it's there
        const welcomeMessage = document.getElementById('welcome-message');
        if(welcomeMessage) welcomeMessage.remove();

        appendMessage('user', prompt);
        
        promptInput.value = '';
        promptInput.style.height = 'auto';
        sendButton.disabled = true;
        promptInput.disabled = true;

        const loadingId = appendLoading();

        try {
            const response = await fetch('http://localhost:8000/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${currentToken}`
                },
                body: JSON.stringify({ prompt: prompt }),
            });

            const data = await response.json();
            
            if (response.ok && data.status === 'success') {
                // Instantly update sidebar history with 'pending' state
                fetchHistory();
                pollTaskStatus(data.task_id, loadingId);
            } else {
                removeLoading(loadingId);
                if (response.status === 401) {
                    localStorage.removeItem('animatrix_token');
                    currentToken = null;
                    updateUIBasedOnAuth();
                    alert("Session expired. Please log in again.");
                } else {
                    appendMessage('assistant', `Error: ${data.detail || 'Failed to start task.'}`);
                }
            }

        } catch (error) {
            removeLoading(loadingId);
            appendMessage('assistant', `Connection Error: Make sure the FastAPI server is running.`);
        } finally {
            promptInput.disabled = false;
            promptInput.focus();
        }
    });

    // --- UI Helpers ---
    function appendMessage(role, text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message`;
        
        const avatar = role === 'user' ? 'U' : 'A';
        
        messageDiv.innerHTML = `
            <div class="avatar">${avatar}</div>
            <div class="content">
                <p>${escapeHTML(text)}</p>
            </div>
        `;
        
        chatHistory.appendChild(messageDiv);
        scrollToBottom();
    }

    function appendVideoMessage(role, text, videoUrl, code) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message`;
        
        const avatar = role === 'user' ? 'U' : 'A';
        
        let codeHtml = '';
        if (code) {
            codeHtml = `
                <div class="code-container">
                    <pre><code>${escapeHTML(code)}</code></pre>
                </div>
            `;
        }
        
        messageDiv.innerHTML = `
            <div class="avatar">${avatar}</div>
            <div class="content">
                <p>${escapeHTML(text)}</p>
                <video controls autoplay loop>
                    <source src="${videoUrl}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
                <a href="${videoUrl}" download class="download-btn">
                    <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    Download Animation
                </a>
                ${codeHtml}
            </div>
        `;
        
        chatHistory.appendChild(messageDiv);
        scrollToBottom();
    }

    function appendLoading() {
        const id = 'loading-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = `message assistant-message`;
        messageDiv.id = id;
        
        messageDiv.innerHTML = `
            <div class="avatar">A</div>
            <div class="content">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        
        chatHistory.appendChild(messageDiv);
        scrollToBottom();
        return id;
    }

    function removeLoading(id) {
        const element = document.getElementById(id);
        if (element) {
            element.remove();
        }
    }

    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    }
    
    sendButton.disabled = true;
});
