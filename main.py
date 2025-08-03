from logic import DietChatBot
from ui import PersistentChatBotUI

# Initialize the chatbot
diet_chatbot = DietChatBot()

# Create and launch the UI with persistence
chatbot_ui = PersistentChatBotUI(diet_chatbot)
interface = chatbot_ui.create_ui()
interface.launch()
 