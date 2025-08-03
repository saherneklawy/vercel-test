import datetime
import sqlite3
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_community.chat_message_histories import SQLChatMessageHistory
from dotenv import load_dotenv
from typing import List, Optional, Generator

# Load environment variables
load_dotenv()

# Constants
DEFAULT_MODEL = "gpt-4o-mini"
DB_CONNECTION_STRING = "sqlite:///conversations.db"


class DietChatBot:
    def __init__(self, session_id: Optional[str] = None):
        """Initialize the Diet Chatbot."""
        # Read the prompt from file
        with open("prompt.md", "r") as f:
            system_message = f.read()

        self.model = init_chat_model(model=DEFAULT_MODEL, temperature=0)
        self.system_msg = SystemMessage(content=system_message)

        self._initialize_session(session_id)
        self._initialize_history()

    def _initialize_session(self, session_id: Optional[str] = None) -> None:
        """Initialize the session."""
        self.session_id = self._generate_session_id() if not session_id else session_id

    def _generate_session_id(self) -> str:
        """Generate a new session ID with timestamp."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"Diet Chat - {timestamp}"

    def _initialize_history(self) -> None:
        """Initialize or load the conversation for the current session."""
        self.history = SQLChatMessageHistory(
            session_id=self.session_id, connection_string=DB_CONNECTION_STRING
        )
        if not self.history.get_messages():
            self.history.add_message(self.system_msg)

    # main new code for streaming
    def stream_response(self, user_message: str) -> Generator[str, None, None]:
        """Stream AI response chunks for a user message."""
        # Check if message is empty
        if not (user_message := user_message.strip()):
            return

        # Add user message to history
        self.history.add_message(HumanMessage(content=user_message))

        # Stream response
        response_content = ""
        for chunk in self.model.stream(self.history.get_messages()):
            if chunk.content:
                response_content += chunk.content
                yield chunk.content

        # Add final response to history
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

        # Get the database path from the connection string
        db_path = DB_CONNECTION_STRING.replace("sqlite:///", "")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall()]