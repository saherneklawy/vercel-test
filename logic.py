import datetime
import os
import logging
from langchain.chat_models import init_chat_model

# Configure logging
logger = logging.getLogger(__name__)
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
try:
    from langchain_community.chat_message_histories import SQLChatMessageHistory
except ImportError:
    from langchain.memory.chat_message_histories import SQLChatMessageHistory
from dotenv import load_dotenv
from typing import List, Optional, Generator
import psycopg2
from psycopg2 import sql

# Load environment variables
load_dotenv()

# Constants
DEFAULT_MODEL = "gpt-4o-mini"

# PostgreSQL connection string from environment
DATABASE_URL = os.getenv("DATABASE_URL_UNPOOLED")
if not DATABASE_URL:
    # Fallback to individual components for development
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "diet_assistant")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

DB_CONNECTION_STRING = DATABASE_URL

def initialize_database():
    """Initialize the database tables if they don't exist."""
    try:
        with psycopg2.connect(DB_CONNECTION_STRING) as conn:
            with conn.cursor() as cursor:
                # Create the message_store table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS message_store (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        message JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create an index on session_id for faster queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_store_session_id 
                    ON message_store(session_id);
                """)
                
                # Create an index on created_at for time-based queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_store_created_at 
                    ON message_store(created_at);
                """)
                
                conn.commit()
                print("Database tables initialized successfully")
                
    except psycopg2.Error as e:
        print(f"Error initializing database: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error initializing database: {e}")
        raise


class DietChatBot:
    def __init__(self, session_id: Optional[str] = None):
        """Initialize the Diet Chatbot."""
        # Ensure database is initialized before using it
        self._ensure_database_initialized()
        
        # Read the prompt from file
        with open("prompt.md", "r") as f:
            system_message = f.read()

        logger.info(f"Initializing chat model: {DEFAULT_MODEL}")
        self.model = init_chat_model(model=DEFAULT_MODEL, temperature=0)
        logger.info(f"Model initialized successfully: {type(self.model)}")
        self.system_msg = SystemMessage(content=system_message)
        logger.info(f"System message created: {len(system_message)} chars")

        self._initialize_session(session_id)
        self._initialize_history()
    
    def _ensure_database_initialized(self) -> None:
        """Ensure database is initialized, with fallback for serverless environments."""
        try:
            # Try to check if tables exist by running a simple query
            with psycopg2.connect(DB_CONNECTION_STRING) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='message_store')")
                    table_exists = cursor.fetchone()[0]
                    
                    if not table_exists:
                        print("Database tables not found, initializing...")
                        initialize_database()
        except psycopg2.Error as e:
            print(f"Database check failed, attempting initialization: {e}")
            try:
                initialize_database()
            except Exception as init_error:
                print(f"Database initialization failed: {init_error}")
                raise

    def _initialize_session(self, session_id: Optional[str] = None) -> None:
        """Initialize the session."""
        self.session_id = self._generate_session_id() if not session_id else session_id

    def _generate_session_id(self) -> str:
        """Generate a new session ID with timestamp."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"Diet Chat - {timestamp}"

    def _initialize_history(self) -> None:
        """Initialize or load the conversation for the current session."""
        logger.info(f"Initializing SQLChatMessageHistory for session: {self.session_id}")
        logger.info(f"DB connection string: {DB_CONNECTION_STRING[:50]}...")
        
        # Try different SQLChatMessageHistory initialization approaches
        try:
            self.history = SQLChatMessageHistory(
                session_id=self.session_id, 
                connection_string=DB_CONNECTION_STRING
            )
            logger.info("SQLChatMessageHistory created successfully")
        except Exception as e:
            logger.error(f"Failed to create SQLChatMessageHistory: {e}")
            # Try with table_name parameter
            try:
                self.history = SQLChatMessageHistory(
                    session_id=self.session_id, 
                    connection_string=DB_CONNECTION_STRING,
                    table_name="message_store"
                )
                logger.info("SQLChatMessageHistory created with table_name parameter")
            except Exception as e2:
                logger.error(f"Failed with table_name parameter: {e2}")
                raise e
        
        # Only add system message for new sessions (empty history)
        try:
            existing_messages = self.history.get_messages()
            logger.info(f"Found {len(existing_messages)} existing messages")
            if not existing_messages:
                logger.info("Adding system message to new session")
                self.history.add_message(self.system_msg)
        except Exception as e:
            logger.error(f"Error checking/adding system message: {e}")
            # Clear the session and start fresh
            logger.info("Clearing corrupted session and starting fresh")
            with psycopg2.connect(DB_CONNECTION_STRING) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM message_store WHERE session_id = %s", (self.session_id,))
                    conn.commit()
            # Add system message to fresh session
            self.history.add_message(self.system_msg)

    # main new code for streaming
    def stream_response(self, user_message: str) -> Generator[str, None, None]:
        """Stream AI response chunks for a user message."""
        logger.info(f"stream_response called with user_message: '{user_message}'")
        
        # Check if message is empty
        if not (user_message := user_message.strip()):
            logger.warning("Empty user message, returning")
            return

        # Add user message to history
        logger.info("Adding user message to history")
        human_msg = HumanMessage(content=user_message)
        self.history.add_message(human_msg)
        logger.info("Successfully added human message to history")

        # Get messages for streaming
        logger.info("Getting messages from history")
        messages = self.history.get_messages()
        logger.info(f"Retrieved {len(messages)} messages successfully")
        logger.info(f"Messages to stream: {len(messages)} messages")
        for i, msg in enumerate(messages):
            logger.debug(f"Message {i}: {type(msg)} - {msg.content[:100] if hasattr(msg, 'content') else str(msg)[:100]}")
        
        response_content = ""
        try:
            logger.info("Calling self.model.stream(messages)")
            # Add a simple test to see if the model can handle the messages at all
            logger.info("Testing model with basic invoke first")
            test_response = self.model.invoke(messages[:2])  # Just test with system + first human message
            logger.info(f"Test response successful: {type(test_response)}")
            
            logger.info("Now starting actual streaming")
            for chunk in self.model.stream(messages):
                logger.debug(f"Received chunk: {chunk} (type: {type(chunk)})")
                logger.debug(f"Chunk content: {chunk.content} (type: {type(chunk.content)})")
                
                if chunk.content:
                    # Ensure chunk.content is a string
                    content_str = str(chunk.content)
                    response_content += content_str
                    logger.debug(f"Yielding content_str: '{content_str}' (type: {type(content_str)})")
                    yield content_str
        except Exception as e:
            logger.error(f"Error during model streaming: {e} (type: {type(e)})")
            logger.error(f"Error details: {str(e)}")
            raise e

        # Add final response to history
        logger.info(f"Adding final response to history: '{response_content}'")
        self.history.add_message(AIMessage(content=response_content))

    def new_session(self) -> None:
        """Create a new conversation."""
        self._initialize_session()
        self._initialize_history()

    def load_session(self, session_id: str) -> None:
        """Load an existing conversation."""
        if not session_id:
            return

        self._initialize_session(session_id)
        self._initialize_history()

    def get_messages(self) -> List[BaseMessage]:
        """Get all messages from the current session."""
        return self.history.get_messages()

    @staticmethod
    def get_previous_conversations() -> List[str]:
        """Get a list of all available conversations."""
        # SQL Query to get previous conversations with more than just the system message
        query = """
        SELECT session_id FROM message_store 
        GROUP BY session_id 
        HAVING COUNT(*) > 1
        ORDER BY session_id DESC
        """

        try:
            # Connect to PostgreSQL
            with psycopg2.connect(DB_CONNECTION_STRING) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return [row[0] for row in cursor.fetchall()]
        except psycopg2.Error as e:
            print(f"PostgreSQL error: {e}")
            return []
        except Exception as e:
            print(f"Database error: {e}")
            return []
