import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from logic import DietChatBot, initialize_database
import json
import asyncio
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    logger.info(f"Received request for session: {session_id}")
    
    try:
        message_data = await request.json()
        logger.info(f"Parsed message_data: {message_data} (type: {type(message_data)})")
        
        user_message = message_data.get("message", "").strip()
        logger.info(f"Extracted user_message: '{user_message}'")
        
        if not user_message:
            logger.error("Empty user message received")
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Initialize or load chatbot for this session
        logger.info(f"Initializing chatbot for session: {session_id}")
        chatbot = DietChatBot(session_id=session_id)
        
        async def generate_stream():
            try:
                logger.info("Starting stream generation")
                
                # Send acknowledgment that message was received
                ack_data = {'type': 'message_received', 'content': user_message}
                logger.info(f"Sending ack_data: {ack_data} (type: {type(ack_data)})")
                ack_json = json.dumps(ack_data)
                logger.info(f"Serialized ack_json: {ack_json}")
                yield f"data: {ack_json}\n\n"
                
                # Stream response from chatbot
                logger.info("Starting chatbot stream response")
                full_response = ""
                for chunk in chatbot.stream_response(user_message):
                    full_response += chunk
                    
                    chunk_data = {'type': 'stream_chunk', 'content': chunk, 'full_content': full_response}
                    logger.debug(f"Sending chunk_data: {type(chunk_data)}")
                    chunk_json = json.dumps(chunk_data)
                    yield f"data: {chunk_json}\n\n"
                    await asyncio.sleep(0.01)  # Small delay to prevent overwhelming
                
                # Send completion signal
                complete_data = {'type': 'stream_complete', 'content': full_response}
                logger.info(f"Sending complete_data: {complete_data} (type: {type(complete_data)})")
                complete_json = json.dumps(complete_data)
                yield f"data: {complete_json}\n\n"
                
                logger.info("Stream generation completed successfully")
                
            except Exception as e:
                logger.error(f"Error in generate_stream: {e} (type: {type(e)})")
                error_data = {'type': 'error', 'content': f'Error: {str(e)}'}
                logger.info(f"Sending error_data: {error_data} (type: {type(error_data)})")
                try:
                    error_json = json.dumps(error_data)
                    yield f"data: {error_json}\n\n"
                except Exception as json_err:
                    logger.error(f"Failed to serialize error data: {json_err}")
                    yield f"data: {json.dumps({'type': 'error', 'content': 'JSON serialization error'})}\n\n"
        
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
                    
    except Exception as e:
        logger.error(f"Error in send_message endpoint: {e} (type: {type(e)})")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
 