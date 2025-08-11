// Chat functionality for Diet Planning Assistant

class ChatManager {
    constructor() {
        this.websocket = null;
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
            
            this.connectWebSocket();
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
            
            this.connectWebSocket();
        } catch (error) {
            console.error('Error loading session:', error);
            this.updateConnectionStatus('disconnected', 'Error loading session');
        }
    }
    
    connectWebSocket() {
        if (this.websocket) {
            this.websocket.close();
        }
        
        if (!this.currentSessionId) return;
        
        this.updateConnectionStatus('connecting', 'Connecting...');
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${this.currentSessionId}`;
        
        this.websocket = new WebSocket(wsUrl);
        
        this.websocket.onopen = () => {
            this.updateConnectionStatus('connected', 'Connected');
        };
        
        this.websocket.onmessage = (event) => {
            this.handleWebSocketMessage(JSON.parse(event.data));
        };
        
        this.websocket.onclose = () => {
            this.updateConnectionStatus('disconnected', 'Disconnected');
        };
        
        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateConnectionStatus('disconnected', 'Connection error');
        };
    }
    
    handleWebSocketMessage(data) {
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
                this.updateConnectionStatus('connected', 'Connected');
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
                this.updateConnectionStatus('connected', 'Connected');
                break;
        }
    }
    
    sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || !this.websocket || this.websocket.readyState !== WebSocket.OPEN || this.isStreaming) {
            return;
        }
        
        // Add user message to UI
        this.addMessage('user', message, false);
        
        // Clear input
        this.messageInput.value = '';
        
        // Add streaming assistant message
        this.currentStreamingMessage = this.addMessage('assistant', '', true);
        
        // Send message via WebSocket
        this.websocket.send(JSON.stringify({
            message: message
        }));
        
        this.isStreaming = true;
        this.updateConnectionStatus('connected', 'Thinking...');
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