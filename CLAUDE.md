# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env  # Edit with your credentials

# Run the application locally
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Alternative: Run with Python
python main.py
```

### Local Database Setup
For local development with PostgreSQL:
```bash
# Create local database (optional - tables will be created automatically)
createdb diet_assistant

# Set environment variables in .env:
DATABASE_URL=postgresql://username:password@localhost:5432/diet_assistant
OPENAI_API_KEY=your_openai_api_key
```

**Note**: Database tables are automatically created on first request if they don't exist.

## Architecture Overview

This is a FastAPI-based diet planning assistant with modern web architecture:

### Core Components
1. **`main.py`** - FastAPI application with WebSocket endpoints and API routes
2. **`logic.py`** - Contains `DietChatBot` class handling LLM interactions and persistence  
3. **`templates/`** - Jinja2 HTML templates for the frontend
4. **`static/`** - CSS and JavaScript assets for the web interface

### Data Flow
```
User Input → WebSocket → DietChatBot → LangChain LLM → PostgreSQL → WebSocket Stream → Frontend
```

## Key Implementation Details

### FastAPI Endpoints
- **GET /**: Serves main chat interface via Jinja2 template
- **WebSocket /ws/{session_id}**: Real-time chat streaming
- **GET /api/sessions**: List all conversation sessions
- **POST /api/sessions/new**: Create new conversation session
- **GET /api/sessions/{session_id}**: Load specific session messages

### WebSocket Streaming Pattern
Real-time communication using WebSocket protocol:
- `DietChatBot.stream_response()` yields LLM chunks
- WebSocket sends JSON messages with type indicators
- Frontend JavaScript handles streaming updates progressively
- Message types: `message_received`, `stream_chunk`, `stream_complete`, `error`

### Database Configuration
PostgreSQL database with LangChain integration:
- Uses `psycopg2-binary` for PostgreSQL adapter
- Connection string from `DATABASE_URL` environment variable
- Fallback to individual DB_* environment variables for development
- Uses LangChain's `SQLChatMessageHistory` with PostgreSQL backend
- **Auto-initialization**: Tables and indexes created automatically on first request
- Graceful handling of database initialization in serverless environments

### Frontend Architecture
Modern web interface with vanilla JavaScript:
- **Templates**: Jinja2 with template inheritance (`base.html`, `chat.html`)
- **Styling**: Tailwind CSS with custom CSS for chat components
- **JavaScript**: `ChatManager` class handling WebSocket and UI state
- **Real-time Updates**: WebSocket client with connection management

## Environment Setup

Required environment variables:

### Database Configuration
```bash
DATABASE_URL=postgresql://user:password@host:port/database
# OR individual components:
DB_HOST=localhost
DB_PORT=5432
DB_NAME=diet_assistant
DB_USER=postgres
DB_PASSWORD=password
```

### LLM Configuration
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

## Session Management

### Session Lifecycle
1. Sessions created with timestamp: `"Diet Chat - YYYY-MM-DD HH:MM:SS"`
2. PostgreSQL persistence across application restarts
3. WebSocket connections per session for real-time chat
4. System message from `prompt.md` automatically added to new sessions

### Frontend Session Management
- Dropdown populated via `/api/sessions` endpoint
- New chat button creates session via `/api/sessions/new`
- Session switching loads messages via `/api/sessions/{session_id}`
- WebSocket reconnection when switching sessions

## Vercel Deployment

### Configuration (`vercel.json`)
- Python 3.9 runtime with pipEnv
- Static file routing for `/static/*` assets
- Environment variables: `DATABASE_URL`, `OPENAI_API_KEY`
- All other routes handled by FastAPI application

### PostgreSQL Setup
For production deployment, use managed PostgreSQL service:
- Vercel Postgres
- Supabase
- Neon
- Amazon RDS

Set `DATABASE_URL` in Vercel environment variables.

**Database Schema**: The application automatically creates the following table structure:
```sql
CREATE TABLE message_store (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    message JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_message_store_session_id ON message_store(session_id);
CREATE INDEX idx_message_store_created_at ON message_store(created_at);
```

## File Structure
```
/
├── main.py              # FastAPI application
├── logic.py             # DietChatBot with PostgreSQL
├── prompt.md            # System prompt for LLM
├── requirements.txt     # Python dependencies
├── vercel.json          # Vercel deployment config
├── templates/
│   ├── base.html        # Base template
│   └── chat.html        # Chat interface
└── static/
    ├── css/style.css    # Custom styles
    └── js/chat.js       # WebSocket chat client
```