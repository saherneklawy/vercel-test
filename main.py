import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from logic import DietChatBot, initialize_database
import json
import asyncio

app = FastAPI(title="Diet Planning Assistant")

@app.on_event("startup")
async def startup_event():
    """Initialize database tables on application startup."""
    try:
        initialize_database()
        print("Application startup: Database initialization completed")
    except Exception as e:
        print(f"Application startup: Database initialization failed: {e}")
        # Don't raise here to allow app to start even if DB is temporarily unavailable

# Mount static files - now flattened to root directory
app.mount("/static", StaticFiles(directory="."), name="static")
templates = Jinja2Templates(directory=".")


@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    """Serve the main chat interface."""
    return templates.TemplateResponse("chat.html", {"request": request})

@app.get("/api/sessions")
async def get_sessions():
    """Get list of all conversation sessions."""
    try:
        sessions = DietChatBot.get_previous_conversations()
        return JSONResponse(content={"sessions": sessions})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/new")
async def create_new_session():
    """Create a new conversation session."""
    try:
        chatbot = DietChatBot()
        return JSONResponse(content={"session_id": chatbot.session_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}")
async def get_session_messages(session_id: str):
    """Get messages for a specific session."""
    try:
        chatbot = DietChatBot(session_id=session_id)
        messages = chatbot.get_messages()
        
        # Format messages for frontend (skip system message)
        formatted_messages = []
        for msg in messages[1:]:  # Skip system message
            if hasattr(msg, 'type'):
                role = "user" if msg.type == "human" else "assistant"
            else:
                role = "user" if msg.__class__.__name__ == "HumanMessage" else "assistant"
            
            formatted_messages.append({
                "role": role,
                "content": msg.content
            })
        
        return JSONResponse(content={"messages": formatted_messages})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/{session_id}")
async def send_message(session_id: str, request: Request):
    """Send a message and get streaming response via SSE."""
    message_data = await request.json()
    user_message = message_data.get("message", "").strip()
    
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Initialize or load chatbot for this session
    chatbot = DietChatBot(session_id=session_id)
    
    async def generate_stream():
        try:
            # Send acknowledgment that message was received
            yield f"data: {json.dumps({'type': 'message_received', 'content': user_message})}\n\n"
            
            # Stream response from chatbot
            full_response = ""
            for chunk in chatbot.stream_response(user_message):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'stream_chunk', 'content': chunk, 'full_content': full_response})}\n\n"
                await asyncio.sleep(0.01)  # Small delay to prevent overwhelming
            
            # Send completion signal
            yield f"data: {json.dumps({'type': 'stream_complete', 'content': full_response})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
 