import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from logic import DietChatBot, initialize_database
from typing import Dict
import json

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

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Store active WebSocket connections
connections: Dict[str, WebSocket] = {}

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

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time chat."""
    await websocket.accept()
    connections[session_id] = websocket
    
    # Initialize or load chatbot for this session
    chatbot = DietChatBot(session_id=session_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "").strip()
            
            if not user_message:
                continue
            
            # Send acknowledgment that message was received
            await websocket.send_text(json.dumps({
                "type": "message_received",
                "content": user_message
            }))
            
            # Stream response from chatbot
            try:
                full_response = ""
                for chunk in chatbot.stream_response(user_message):
                    full_response += chunk
                    await websocket.send_text(json.dumps({
                        "type": "stream_chunk",
                        "content": chunk,
                        "full_content": full_response
                    }))
                
                # Send completion signal
                await websocket.send_text(json.dumps({
                    "type": "stream_complete",
                    "content": full_response
                }))
                
            except Exception as e:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": f"Error: {str(e)}"
                }))
    
    except WebSocketDisconnect:
        if session_id in connections:
            del connections[session_id]
    except Exception as e:
        print(f"WebSocket error: {e}")
        if session_id in connections:
            del connections[session_id]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
 