const API_BASE_URL = window.location.origin;

let sessionId = generateSessionId();

function generateSessionId() {
    return 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

function getApiKey() {
    return localStorage.getItem('ragApiKey') || '';
}

function setApiKey(key) {
    localStorage.setItem('ragApiKey', key);
}

function getManualFilter() {
    return localStorage.getItem('ragManualFilter') || '';
}

function setManualFilter(filter) {
    localStorage.setItem('ragManualFilter', filter);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatAnswer(answer) {
    let formatted = escapeHtml(answer);
    formatted = formatted.replace(/\[Source\s*(\d+)\]/gi, '<strong class="source-ref">[Source $1]</strong>');
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
}

function createMessageElement(type, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = content;
    
    messageDiv.appendChild(contentDiv);
    return messageDiv;
}

function createLoadingElement() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.id = 'loadingMessage';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content loading';
    contentDiv.innerHTML = `
        <div class="loading-dots">
            <span></span>
            <span></span>
            <span></span>
        </div>
        <span>Searching manuals...</span>
    `;
    
    messageDiv.appendChild(contentDiv);
    return messageDiv;
}

function createResponseElement(response) {
    let content = `<p>${formatAnswer(response.answer)}</p>`;
    
    if (response.citations && response.citations.length > 0) {
        content += `
            <div class="citations">
                <div class="citations-title">Sources</div>
                ${response.citations.map((citation, index) => `
                    <div class="citation-item">
                        <div class="citation-source">${escapeHtml(citation.manual_name)} - Page ${citation.page}</div>
                        <div class="citation-quote">"${escapeHtml(citation.quote)}"</div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    const confidenceClass = `confidence-${response.confidence}`;
    content += `<span class="confidence-badge ${confidenceClass}">${response.confidence} confidence</span>`;
    
    if (response.request_id) {
        content += `<div class="request-id">Request ID: ${escapeHtml(response.request_id)}</div>`;
    }
    
    if (response.follow_up_question) {
        content += `<p style="margin-top: 12px; font-style: italic; color: var(--text-secondary);">${escapeHtml(response.follow_up_question)}</p>`;
    }
    
    return createMessageElement('assistant', content);
}

function createErrorElement(message) {
    return createMessageElement('assistant', `<div class="error-message">${escapeHtml(message)}</div>`);
}

async function sendMessage(question) {
    const chatMessages = document.getElementById('chatMessages');
    const sendButton = document.getElementById('sendButton');
    const questionInput = document.getElementById('questionInput');
    
    const userMessage = createMessageElement('user', `<p>${escapeHtml(question)}</p>`);
    chatMessages.appendChild(userMessage);
    
    const loadingMessage = createLoadingElement();
    chatMessages.appendChild(loadingMessage);
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    sendButton.disabled = true;
    questionInput.disabled = true;
    
    try {
        const apiKey = getApiKey();
        if (!apiKey) {
            throw new Error('Please configure your API key in settings.');
        }
        
        const requestBody = {
            question: question,
            session_id: sessionId,
        };
        
        const manualFilter = getManualFilter();
        if (manualFilter) {
            requestBody.manual_filter = manualFilter;
        }
        
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-KEY': apiKey,
            },
            body: JSON.stringify(requestBody),
        });
        
        loadingMessage.remove();
        
        if (!response.ok) {
            let errorMessage = 'An error occurred while processing your request.';
            
            if (response.status === 401) {
                errorMessage = 'Authentication failed. Please check your API key in settings.';
            } else if (response.status === 422) {
                errorMessage = 'Invalid request. Please check your question and try again.';
            } else if (response.status === 429) {
                errorMessage = 'Rate limit exceeded. Please wait a moment and try again.';
            } else if (response.status >= 500) {
                errorMessage = 'Server error. Please try again later.';
            }
            
            try {
                const errorData = await response.json();
                if (errorData.detail) {
                    errorMessage = typeof errorData.detail === 'string' 
                        ? errorData.detail 
                        : 'Validation error. Please check your input.';
                }
            } catch (e) {
            }
            
            throw new Error(errorMessage);
        }
        
        const data = await response.json();
        const responseElement = createResponseElement(data);
        chatMessages.appendChild(responseElement);
        
    } catch (error) {
        const existingLoading = document.getElementById('loadingMessage');
        if (existingLoading) {
            existingLoading.remove();
        }
        
        const errorElement = createErrorElement(error.message);
        chatMessages.appendChild(errorElement);
    } finally {
        sendButton.disabled = false;
        questionInput.disabled = false;
        questionInput.focus();
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function initializeApp() {
    const questionInput = document.getElementById('questionInput');
    const sendButton = document.getElementById('sendButton');
    const charCount = document.getElementById('charCount');
    const settingsToggle = document.getElementById('settingsToggle');
    const settingsPanel = document.getElementById('settingsPanel');
    const apiKeyInput = document.getElementById('apiKeyInput');
    const manualFilterInput = document.getElementById('manualFilter');
    const saveSettingsButton = document.getElementById('saveSettings');
    
    apiKeyInput.value = getApiKey();
    manualFilterInput.value = getManualFilter();
    
    questionInput.addEventListener('input', function() {
        charCount.textContent = this.value.length;
        
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });
    
    questionInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (this.value.trim() && !sendButton.disabled) {
                sendMessage(this.value.trim());
                this.value = '';
                charCount.textContent = '0';
                this.style.height = 'auto';
            }
        }
    });
    
    sendButton.addEventListener('click', function() {
        const question = questionInput.value.trim();
        if (question && !this.disabled) {
            sendMessage(question);
            questionInput.value = '';
            charCount.textContent = '0';
            questionInput.style.height = 'auto';
        }
    });
    
    settingsToggle.addEventListener('click', function() {
        settingsPanel.classList.toggle('visible');
    });
    
    document.addEventListener('click', function(e) {
        if (!settingsPanel.contains(e.target) && !settingsToggle.contains(e.target)) {
            settingsPanel.classList.remove('visible');
        }
    });
    
    saveSettingsButton.addEventListener('click', function() {
        setApiKey(apiKeyInput.value);
        setManualFilter(manualFilterInput.value);
        settingsPanel.classList.remove('visible');
        
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            bottom: 80px;
            left: 50%;
            transform: translateX(-50%);
            background-color: var(--success-color);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 14px;
            z-index: 1000;
            animation: fadeIn 0.3s ease;
        `;
        notification.textContent = 'Settings saved!';
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 2000);
    });
    
    questionInput.focus();
}

document.addEventListener('DOMContentLoaded', initializeApp);
