// Chat functionality for Diet Planning Assistant

class ChatManager {
    constructor() {
        this.eventSource = null;
        this.currentSessionId = null;
        this.isStreaming = false;
        this.currentStreamingMessage = null;
        
        this.initializeElements();
        this.attachEventListeners();
        this.loadSessions();
        this.createNewSession();
    }
    
    initializeElements() {
        this.sessionSelect = document.getElementById('sessionSelect');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.chatMessages = document.getElementById('chatMessages');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.messageTemplate = document.getElementById('messageTemplate');
    }
    
    attachEventListeners() {
        this.newChatBtn.addEventListener('click', () => this.createNewSession());
        this.sessionSelect.addEventListener('change', (e) => this.loadSession(e.target.value));
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }
    
    updateConnectionStatus(status, message) {
        this.connectionStatus.className = `connection-status ${status}`;
        this.connectionStatus.textContent = message;
        
        // Enable/disable input based on connection
        const isConnected = status === 'connected';
        this.messageInput.disabled = !isConnected || this.isStreaming;
        this.sendBtn.disabled = !isConnected || this.isStreaming;
    }
    
    async loadSessions() {
        try {
            const response = await fetch('/api/sessions');
            const data = await response.json();
            
            this.sessionSelect.innerHTML = '<option value="">Select a conversation...</option>';
            data.sessions.forEach(sessionId => {
                const option = document.createElement('option');
                option.value = sessionId;
                option.textContent = sessionId;
                this.sessionSelect.appendChild(option);
            });
        } catch (error) {
            console.error('Error loading sessions:', error);
        }
    }
    
    async createNewSession() {
        try {
            const response = await fetch('/api/sessions/new', { method: 'POST' });
            const data = await response.json();
            
            this.currentSessionId = data.session_id;
            this.sessionSelect.value = this.currentSessionId;
            this.chatMessages.innerHTML = '';
            
            // Add new session to dropdown
            const option = document.createElement('option');
            option.value = this.currentSessionId;
            option.textContent = this.currentSessionId;
            option.selected = true;
            this.sessionSelect.insertBefore(option, this.sessionSelect.children[1]);
            
            this.updateConnectionStatus('connected', 'Ready');
        } catch (error) {
            console.error('Error creating new session:', error);
            this.updateConnectionStatus('disconnected', 'Error creating session');
        }
    }
    
    async loadSession(sessionId) {
        if (!sessionId) return;
        
        this.currentSessionId = sessionId;
        this.chatMessages.innerHTML = '';
        
        try {
            // Load session messages
            const response = await fetch(`/api/sessions/${sessionId}`);
            const data = await response.json();
            
            // Display messages
            data.messages.forEach(message => {
                this.addMessage(message.role, message.content, false);
            });
            
            this.updateConnectionStatus('connected', 'Ready');
        } catch (error) {
            console.error('Error loading session:', error);
            this.updateConnectionStatus('disconnected', 'Error loading session');
        }
    }
    
    closeEventSource() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
    
    handleServerSentEvent(data) {
        switch (data.type) {
            case 'message_received':
                // Message was received by server
                break;
                
            case 'stream_chunk':
                if (this.currentStreamingMessage) {
                    const messageText = this.currentStreamingMessage.querySelector('.message-text');
                    messageText.textContent = data.full_content;
                    this.scrollToBottom();
                }
                break;
                
            case 'stream_complete':
                if (this.currentStreamingMessage) {
                    this.currentStreamingMessage.classList.remove('streaming');
                    this.currentStreamingMessage = null;
                }
                this.isStreaming = false;
                this.updateConnectionStatus('connected', 'Ready');
                break;
                
            case 'error':
                console.error('Chat error:', data.content);
                if (this.currentStreamingMessage) {
                    const messageText = this.currentStreamingMessage.querySelector('.message-text');
                    messageText.textContent = `Error: ${data.content}`;
                    this.currentStreamingMessage.classList.remove('streaming');
                    this.currentStreamingMessage = null;
                }
                this.isStreaming = false;
                this.updateConnectionStatus('connected', 'Ready');
                break;
        }
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || !this.currentSessionId || this.isStreaming) {
            return;
        }
        
        // Add user message to UI
        this.addMessage('user', message, false);
        
        // Clear input
        this.messageInput.value = '';
        
        // Add streaming assistant message
        this.currentStreamingMessage = this.addMessage('assistant', '', true);
        
        this.isStreaming = true;
        this.updateConnectionStatus('connected', 'Thinking...');
        
        try {
            // Send message via fetch POST to SSE endpoint
            const response = await fetch(`/api/chat/${this.currentSessionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            // Create EventSource for the streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            this.handleServerSentEvent(data);
                        } catch (e) {
                            // Ignore malformed JSON
                        }
                    }
                }
            }
            
        } catch (error) {
            console.error('Error sending message:', error);
            if (this.currentStreamingMessage) {
                const messageText = this.currentStreamingMessage.querySelector('.message-text');
                messageText.textContent = `Error: ${error.message}`;
                this.currentStreamingMessage.classList.remove('streaming');
                this.currentStreamingMessage = null;
            }
            this.isStreaming = false;
            this.updateConnectionStatus('connected', 'Ready');
        }
    }
    
    addMessage(role, content, streaming = false) {
        const template = this.messageTemplate.content.cloneNode(true);
        const messageElement = template.querySelector('.message');
        
        messageElement.classList.add(role);
        if (streaming) {
            messageElement.classList.add('streaming');
        }
        
        const avatar = template.querySelector('.avatar');
        const roleLabel = template.querySelector('.role-label');
        const messageText = template.querySelector('.message-text');
        
        roleLabel.textContent = role === 'user' ? 'You' : 'Assistant';
        
        if (streaming && !content) {
            // Add typing indicator
            messageText.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
        } else {
            messageText.textContent = content;
        }
        
        this.chatMessages.appendChild(messageElement);
        this.scrollToBottom();
        
        return messageElement;
    }
    
    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
}

// Initialize chat functionality
function initializeChat() {
    window.chatManager = new ChatManager();
}

// Global function for backwards compatibility
window.initializeChat = initializeChat;