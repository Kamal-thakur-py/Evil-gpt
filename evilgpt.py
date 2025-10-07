import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Constants
API_URL = "https://text.pollinations.ai"
DEFAULT_MODEL = "evil"  # Changed to "evil"
TOKEN = "7297075275:AAE1XGYnDNIrROUP2BSw1j6NcCtvEAL4EAo"   # Replace with your bot token
MAX_TELEGRAM_MESSAGE_LENGTH = 4096

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Telegram Application
application = Application.builder().token(TOKEN).build()

# Generate Text Function
def generate_text(prompt, model=DEFAULT_MODEL):
    try:
        response = requests.get(f"{API_URL}/{prompt}", params={"model": model})
        if response.status_code == 200:
            return response.text.strip()
        else:
            return f"Error: Unable to generate text. Status Code: {response.status_code}"
    except Exception as e:
        logger.error(f"Error in generate_text: {e}")
        return f"Error: {e}"

# Start Command Handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Send me a text prompt, and I’ll generate a response for you!"
    )

# Handle Prompt and Generate Text
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text

    # Log user details and prompt
    logger.info(f"Received prompt from user {update.message.from_user.id}: {user_prompt}")

    generated_text = generate_text(user_prompt)
    if len(generated_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
        await update.message.reply_text("The generated response is too long. Try a shorter prompt.")
        return
    
    # Send the generated text back to the user
    await update.message.reply_text(generated_text)

# Error Handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("An unexpected error occurred. Please try again later.")

# Application Start
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
application.add_handler(CommandHandler("start", start))

# Error Handler
application.add_error_handler(error_handler)

# Run the bot
if __name__ == "__main__":
    application.run_polling()