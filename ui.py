import gradio as gr
from typing import List, Tuple, Any
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage


class PersistentChatBotUI:
    def __init__(self, diet_chatbot):
        """Initialize the UI with a chatbot instance."""
        self.diet_chatbot = diet_chatbot

    # important change to handle streaming
    def stream_message_handler(
        self, user_message: str, history: list
    ) -> Generator[Tuple[str, list], None, None]:
        """Send message to chatbot and stream the response."""
        # Check if message is empty
        if not (user_message := user_message.strip()):
            yield "", history
            return

        # Add user message to UI history
        history.append(gr.ChatMessage(content=user_message, role="user"))
        history.append(gr.ChatMessage(content="", role="assistant"))

        # Yield user message and empty assistant message
        yield "", history

        # Stream response
        full_response = ""
        # important change to handle streaming
        for chunk in self.diet_chatbot.stream_response(user_message):
            full_response += chunk
            history[-1] = gr.ChatMessage(content=full_response, role="assistant")
            yield "", history

    def new_session_handler(self) -> Tuple[list, Any]:
        """Create a new conversation and update UI."""
        self.diet_chatbot.new_session()
        return [], self.update_session_choices()

    def load_session_handler(self, session_id: str) -> Tuple[list, Any]:
        """Load an existing conversation and update UI."""
        if not session_id:
            return [], self.update_session_choices()

        self.diet_chatbot.load_session(session_id)
        return (
            self._format_messages_for_ui(self.diet_chatbot.get_messages()),
            self.update_session_choices(),
        )

    def _format_messages_for_ui(self, messages: List[BaseMessage]) -> list:
        """Format messages from LangChain format to Gradio UI format."""
        ui_messages = []

        # Skip the system message (first message)
        for msg in messages[1:]:
            if isinstance(msg, HumanMessage):
                ui_messages.append(gr.ChatMessage(content=msg.content, role="user"))
            elif isinstance(msg, AIMessage):
                ui_messages.append(
                    gr.ChatMessage(content=msg.content, role="assistant")
                )

        return ui_messages

    def update_session_choices(self) -> gr.update:
        """Helper method to ensure current session is in choices."""
        choices = self.diet_chatbot.get_previous_conversations()
        if self.diet_chatbot.session_id not in choices:
            choices.insert(0, self.diet_chatbot.session_id)
        return gr.update(choices=choices, value=self.diet_chatbot.session_id)

    def create_ui(self) -> gr.Blocks:
        """Create the Gradio user interface."""
        with gr.Blocks(
            theme=gr.themes.Soft(), title="Diet Planning Assistant with History"
        ) as interface:
            gr.Markdown("# Diet Planning Assistant")
            gr.Markdown(
                "I can help you create balanced meal plans. Your conversations are saved!"
            )

            chatbot = gr.Chatbot(max_height=400, type="messages")

            with gr.Row():
                with gr.Column(scale=3):
                    msg = gr.Textbox(
                        placeholder="Ask about nutrition or diet plans...",
                        show_label=False,
                    )

                with gr.Column(scale=1):
                    submit = gr.Button("💬 Send", variant="primary")

            with gr.Row():
                sessions = gr.Dropdown(
                    choices=self.diet_chatbot.get_previous_conversations(),
                    value=self.diet_chatbot.session_id,
                    label="Previous Conversations",
                    interactive=True,
                )
                new = gr.Button("🆕 New Chat", size="sm")

            # Event handlers
            submit.click(self.stream_message_handler, [msg, chatbot], [msg, chatbot])
            msg.submit(self.stream_message_handler, [msg, chatbot], [msg, chatbot])
            new.click(self.new_session_handler, None, [chatbot, sessions])
            sessions.change(self.load_session_handler, sessions, [chatbot, sessions])

            # Add a refresh handler to update sessions on page load
            interface.load(self.update_session_choices, None, sessions)

        return interface