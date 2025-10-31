import logging
import aiohttp
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InputMediaPhoto, InputMediaDocument, LabeledPrice, PreCheckoutQuery, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, PreCheckoutQueryHandler, filters, ContextTypes, CallbackContext
import io
from PIL import Image
import asyncio
from collections import deque
from pymongo import MongoClient
import json
from bson import ObjectId
import os
import tempfile
import urllib.parse
import requests
from datetime import datetime, timezone
import http.server
import socketserver
import threading 

# Set your bot token here
TOKEN = "7205442355:AAEQW9N-E8eymfp4f_t0sWvDqpDSJ9Vja28"

# MongoDB configuration
MONGO_URI = "mongodb+srv://kamal:9988Kamal@cluster0.j8d7v.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "tgbot"
COLLECTION_NAME = "user"
QUEUE_COLLECTION_NAME = "queue"

# Initialize MongoDB client and collection
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

user_collection = db[COLLECTION_NAME]
queue_collection = db[QUEUE_COLLECTION_NAME]
HEALTH_CHECK_PORT = 80

# Required channels for users to join
REQUIRED_CHANNELS = ['@AIpromptFree'] # Removed '@Team_Ai_Networks'

# YouTube link to replace the second channel join
YOUTUBE_LINK = "https://www.youtube.com/@KrazyAiMoney"
TELEGRAM_CHANNEL_LINK = "https://t.me/AIpromptFree" # New variable for telegram link

# API URL for image generation from polonation
API_URL = "https://pollinations.ai/p/"
TEXT_URL = "https://text.pollinations.ai"

# Available models
AVAILABLE_MODELS = [
    "flux",
    "flux-pro",
    "flux-cablyai",
    "turbo"
]

# Dictionary to track the number of images sent per user
image_counter = {}
user_request_count = {}
REQUEST_LIMIT = 5
# Admin User IDs and Notification Channel
ADMIN_USER_ID = 7481241644
NOTIFICATION_CHANNEL = "@new_userJoin"


# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# User data storage (in-memory dictionary for simplicity)
user_data = {}
total_users = set()  # Use a set to track unique users
prompt_queue = deque()
queue_processing = False
ESTIMATED_TIME_PER_REQUEST = 10  # seconds

# Welcome message when user presses /start
# --- UPDATED START_TEXT ---
START_TEXT = f"""<b>🎉 Hey there, welcome! 🎨 I'm your friendly, free text-to-image generator bot, ready to turn your ideas into stunning art! 🤖✨

🚀 Let's get started:

1️⃣ First, please join our channels to unlock the bot. You need to join the Telegram channel AND subscribe to our YouTube channel:
👉 <a href="{TELEGRAM_CHANNEL_LINK}">TELEGRAM</a> | <a href="{YOUTUBE_LINK}">YOUTUBE</a>

2️⃣ Once you're done, just hit the button below and let’s dive into the world of AI-powered creativity! 🎨

Need help? Just type /help to see what you can do! 😊</b>
"""
# --- END UPDATED START_TEXT ---

# Function to create the inline keyboard
def get_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("Join✔️", url=TELEGRAM_CHANNEL_LINK)],
        [InlineKeyboardButton("Subscribe🎥", url=YOUTUBE_LINK)], # Updated button text
        [InlineKeyboardButton("✅ Done", callback_data='joined')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Function to create the inline keyboard for models
def get_models_keyboard():
    keyboard = [[InlineKeyboardButton(model, callback_data=f"model_{model}")] for model in AVAILABLE_MODELS]
    return InlineKeyboardMarkup(keyboard)

# Inline keyboard for donation options
def donation_keyboard():
    keyboard = [
        [InlineKeyboardButton("10⭐", callback_data="donate_10"), InlineKeyboardButton("⭐50⭐", callback_data="donate_50")],
        [InlineKeyboardButton("⭐100⭐⭐", callback_data="donate_100"), InlineKeyboardButton("⭐⭐1000⭐⭐", callback_data="donate_1000")],
        [InlineKeyboardButton("PayPal 💳", url="https://paypal.me/TeamAi0")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Function to create the inline keyboard for generated images
def get_generated_image_keyboard():
    # Removed Faceswap and Upscale buttons
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Next ⏭️", callback_data="next_image")],
        [InlineKeyboardButton("Donate⭐️", callback_data="donate"), InlineKeyboardButton("📣 Publish", callback_data="publish")]
    ])
# Function to create the inline keyboard for settings
def get_settings_keyboard():
    keyboard = [
        [InlineKeyboardButton("Change Model⚙️", callback_data="change_model"), InlineKeyboardButton("Change Size📏", callback_data="change_size")],
        [InlineKeyboardButton("Delivery Preference🚀", callback_data="delivery_preference")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Function to check if the user has joined all required channels
async def check_user_in_channels(user_id):
    try:
        for channel in REQUIRED_CHANNELS:
            response = await application.bot.get_chat_member(chat_id=channel, user_id=user_id)
            logger.info(f"Response for user {user_id} in {channel}: {response.status}")
            # Note: Checking subscription to a YouTube channel cannot be done via Telegram API.
            # We are only checking the required Telegram channel(s).
            if response.status == 'left':
                logger.info(f"User {user_id} has left {channel}")
                return False
        logger.info(f"User {user_id} is a member of all required channels.")
        return True
    except Exception as e:
        logger.error(f"Error checking user in channels: {e}")
        return False

# Notify admin and channel when a new user joins
async def notify_new_user(user):
    user_name = user.first_name or "Unknown"
    user_id = user.id
    user_link = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    # Add to MongoDB if the user is new
    if user_collection.find_one({"user_id": user_id}) is None:
        user_collection.insert_one({
            "user_id": user_id,
            "first_name": user.first_name,
            "username": user.username,
            "is_invited": False,
            "can_generate": False,
            "prompts_generated": 0
        })

    # Add to total users set
    total_users.add(user_id)

    # Fetch total users count from the database
    total_users_count = user_collection.count_documents({})

    # Format the notification message
    notification_message = f"""✔️ <b>New User Notification</b>

👤 <b>User</b>: {user_link}
👉 <b>Username</b>: @{user.username}
🆔 <b>User ID</b>: {user_id}

✅ <b>Total Users</b>: {total_users_count}"""

    try:
        # Fetch user's profile photos
        photos = await application.bot.get_user_profile_photos(user_id=user_id, limit=1)
        if photos.total_count > 0:
            # Get the file ID of the most recent profile photo
            file_id = photos.photos[0][-1].file_id  # Choose the highest resolution photo

            # Send profile photo with the notification message as a caption
            await application.bot.send_photo(chat_id=ADMIN_USER_ID, photo=file_id, caption=notification_message, parse_mode="HTML")
            await application.bot.send_photo(chat_id=NOTIFICATION_CHANNEL, photo=file_id, caption=notification_message, parse_mode="HTML")
        else:
            # No profile photo available; send the message without a photo
            await application.bot.send_message(chat_id=ADMIN_USER_ID, text=notification_message, parse_mode="HTML")
            await application.bot.send_message(chat_id=NOTIFICATION_CHANNEL, text=notification_message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error fetching or sending profile photo for user {user_id}: {e}")
        # Fallback: Send the message without a photo
        await application.bot.send_message(chat_id=ADMIN_USER_ID, text=notification_message, parse_mode="HTML")
        await application.bot.send_message(chat_id=NOTIFICATION_CHANNEL, text=notification_message, parse_mode="HTML")

# /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return  # Ignore non-private messages

    user_id = update.effective_user.id
    user = update.effective_user

    # Extract the referral code from the start parameter
    args = context.args
    referrer_id = None
    if args and args[0].startswith("ref_"):
        referrer_id = args[0][4:]  # Extract the referrer ID from the referral link

    # Check if the user is already in the database
    existing_user = user_collection.find_one({"user_id": user_id})
    if not existing_user:
        # Add the new user to the database
        user_collection.insert_one({
            "user_id": user_id,
            "first_name": user.first_name,
            "username": user.username,
            "referrer_id": referrer_id,
            "credits": 0,
            "is_invited": False,
            "can_generate": False,
            "prompts_generated": 0
        })

    # If the user was referred, update the referrer's credits and referral count
    referrer = None  # Initialize referrer to avoid UnboundLocalError
    if referrer_id:
        referrer = user_collection.find_one({"user_id": int(referrer_id)})
    if referrer:
        user_collection.update_one(
            {"user_id": int(referrer_id)},
            {
                "$inc": {"credits": 30, "referral_count": 1}  # Increment referral count
            }
        )
        await context.bot.send_message(
            chat_id=int(referrer_id),
            text=f"🎉 <b>Congratulations!</b> You just earned <b>30 credits</b> and your referral count increased by 1 for referring <b>{user.first_name}</b> to our bot! 🚀",
            parse_mode="HTML"
        )

    # Notify admin and channel about the new user
    if user_id not in total_users:
        await notify_new_user(user)

    # Send the welcome message with the inline keyboard
    await update.message.reply_text(
        text=START_TEXT,
        parse_mode='HTML',
        disable_web_page_preview=True, 
        reply_markup=get_inline_keyboard()
    )

# Callback handler for "Joined" button
async def joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check if the user has joined all required channels
    if await check_user_in_channels(user_id):
        user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"is_invited": True, "can_generate": True}}
        )
        # Log the updated user data
        user_data = user_collection.find_one({"user_id": user_id})
        logger.info(f"User {user_id} updated in database: {user_data}")

        # Delete the welcome message
        await update.callback_query.message.delete()

        # Send the confirmation message
        await update.callback_query.message.reply_text(
            text="You're all set! 🎉\nNow, send me a prompt 📩 and watch as I turn your imagination into stunning art! 🌟🖌️",
            parse_mode='Markdown'
        )
    else:
        # If the user hasn't joined, remind them to join the channels
        await update.callback_query.message.reply_text(
            text="🔐 You have to join the required channels first /start.",
            parse_mode='Markdown',
            reply_markup=get_inline_keyboard()
        )

        # Callback handler for "Donate" button
async def handle_donate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Send donation options
    await query.message.reply_text(
        """✨ Support Our FREE AI Generator! ✨

Our bot is 100% FREE, but your support helps us keep it running and improving! 🙏

💖 Donate now to keep the magic going! 💖

Choose an amount to contribute and help us continue offering amazing AI art for everyone! 🌟

💎 If you donate 50 or more stars, you'll become a Pro User with enhanced benefits! 🚀

⬇️ Select your donation ⬇️""",
        reply_markup=donation_keyboard()
    )

# Common function to handle donations
async def handle_donation(update: Update, context: ContextTypes.DEFAULT_TYPE, amount):
    prices = [LabeledPrice(label=f"{amount} XTR Donation", amount=amount * 1)]  # Amount in the smallest currency unit
    await context.bot.send_invoice(
        chat_id=update.callback_query.message.chat_id,
        title=f"Donate {amount} Star",
        description=f"Support🤝our project with {amount} Stars⭐. Your donation is appreciated!😊💌. you will be upgraded to pro💎",
        payload=f"donation_{amount}",
        provider_token="",  # No provider token needed for Telegram Stars
        currency="XTR",
        prices=prices
    )
# Modify handle_donate callback to ensure 'amount' is passed correctly.
async def handle_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    amount_map = {
        "donate_10": 10,
        "donate_50": 50,
        "donate_100": 100,
        "donate_1000": 1000
    }

    amount = amount_map.get(query.data)
    
    # Ensure 'amount' is found and passed to handle_donation function
    if amount:
        await handle_donation(update, context, amount)  # Pass 'amount' correctly here
    else:
        # Handle the case where no amount was matched
        await query.answer("Invalid donation amount selected.")

        # Handler for pre-checkout queries
async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

# Telegram group to log donations
DONATION_LOG_GROUP = "@donations_byusers"  # Replace with your group username or ID

# Handler for successful payments
async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    donation_amount = message.successful_payment.total_amount / 1  # Convert smallest currency unit

    user_name = user.first_name or "Unknown"
    username = f"@{user.username}" if user.username else "No Username"
    user_id = user.id
    user_link = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    # Promote user to Pro if they donated 50 or more stars
    if donation_amount >= 50:
        user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"pro_user": True}},
            upsert=True
        )
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 Thank you for your generous donation! You have been promoted to a Pro User. Enjoy your enhanced benefits! 🚀"
        )

    # Notify user of successful donation
    await message.reply_text(
        f"✅ Payment successful! Thank you 🙌 for your donation of {donation_amount} stars. Your support means a lot to us! 🥰"
    )

    # Log donation details in the specified Telegram group
    donation_message = f"""🎉 <b>New Donation Received</b>

👤 <b>User</b>: {user_link}
👉 <b>Username</b>: {username}
🆔 <b>User ID</b>: {user_id}
💰 <b>Donated</b>: {donation_amount} Stars

Thank you for supporting our project! 🌟"""
    try:
        await context.bot.send_message(
            chat_id=DONATION_LOG_GROUP,
            text=donation_message,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error logging donation for user {user_id}: {e}")


group_unique_prompts = set()

# Generate image with model parameter
async def generate_image(prompt, seed, width, height, model):
    try:
        # Build the API URL with nologo, seed, and model parameters
        full_url = f"{API_URL}{prompt}?nologo=true&width={width}&height={height}&seed={seed}&model={model}"
        # Send the request to the API
        async with aiohttp.ClientSession() as session:
            async with session.get(full_url) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.error(f"API Error: {response.status} {await response.text()}")
    except Exception as e:
        logger.error(f"Image generation failed😣: {e}")
    return None

# Process the queue with enhanced prompts and timeout
# NOTE: The job queue will call this function every 5 seconds. We keep the inner processing loop 
# to handle multiple items if they are present when called.
async def process_queue(context: ContextTypes.DEFAULT_TYPE = None): # Added context parameter for job queue compatibility
    global queue_processing

    if queue_processing:
        # Log this if needed, but for a job queue approach, it's fine to just return.
        # logger.info("Queue processing already running.") 
        return  # Avoid multiple processors

    queue_processing = True

    try:
        while True:
            # Fetch the next item from the queue (oldest first)
            user_request = queue_collection.find_one_and_delete(
                {},  # No filter, fetch any document
                # Sort: Pro users first, then by timestamp
                sort=[("is_pro_user", -1), ("timestamp", 1)] 
            )

            if not user_request:
                # If queue is empty, break the inner loop. 
                # The job scheduler will call this function again shortly.
                break

            user_id = user_request.get('chat_id')
            prompt = user_request.get('prompt')
            width = user_request.get('width')
            height = user_request.get('height')
            model = user_request.get('model')
            seed = random.randint(1, 100000)

            if not all([user_id, prompt, width, height, model]):
                logger.error(f"Skipping malformed request: {user_request}")
                # Continue to next item without halting the processor
                continue 

            try:
                # Use a timeout for the entire image generation process
                image_data = await asyncio.wait_for(generate_image(prompt, seed, width, height, model), timeout=90)
                
                if image_data:
                    try:
                        # Load the image into a Pillow object
                        image = Image.open(io.BytesIO(image_data))

                        # Save the image to a byte array
                        byte_array = io.BytesIO()
                        image.save(byte_array, format='JPEG')
                        byte_array.seek(0)

                        # Retrieve the user's delivery preference
                        user_data = user_collection.find_one({"user_id": user_id})
                        delivery_preference = user_data.get("delivery_preference", "Fast")

                        # We use application.bot directly for job tasks
                        bot_instance = application.bot if 'application' in globals() else context.bot

                        if delivery_preference == "Quality":
                            # Send the image as a document (no compression)
                            await bot_instance.send_document(
                                chat_id=user_id,
                                document=InputFile(byte_array, filename="generated_image.jpg"),
                                caption="✨ Generated by @St_diffusion_bot",
                                reply_markup=get_generated_image_keyboard()
                            )
                        else:
                            # Send the image as a photo (compressed)
                            await bot_instance.send_photo(
                                chat_id=user_id,
                                photo=InputFile(byte_array, filename="generated_image.jpg"),
                                caption="✨ Generated by @St_diffusion_bot",
                                reply_markup=get_generated_image_keyboard()
                            )

                        # Increment the user's prompts_generated count in the database
                        user_collection.update_one(
                            {"user_id": user_id},
                            {"$inc": {"prompts_generated": 1}}
                        )

                        # Update image counter
                        if user_id not in image_counter:
                            image_counter[user_id] = 0
                        image_counter[user_id] += 1

                    except Exception as e:
                        logger.error(f"Error sending image to user {user_id}: {e}")
                        # Ensure we use context.bot if available, otherwise assume global application.bot
                        bot_instance = context.bot if context and context.bot else application.bot
                        await bot_instance.send_message(chat_id=user_id, text="😔 Failed to process the image. Please try again.")

                else:
                    bot_instance = context.bot if context and context.bot else application.bot
                    await bot_instance.send_message(chat_id=user_id, text="⚠️ Oops! Image generation failed. 😕 Please try again with a different prompt.")

            except asyncio.TimeoutError:
                bot_instance = context.bot if context and context.bot else application.bot
                await bot_instance.send_message(
                    chat_id=user_id,
                    text="⏳ Your request took too long to process and has been skipped. Please try again with a different prompt."
                )
            except Exception as e:
                logger.error(f"Unexpected error during image generation for user {user_id}: {e}")
                bot_instance = context.bot if context and context.bot else application.bot
                await bot_instance.send_message(
                    chat_id=user_id,
                    text="🚨 An unexpected error occurred while processing your request. It has been skipped. Please try again."
                )

            # Yield control back to the event loop momentarily after processing one request
            await asyncio.sleep(0.1) 
    
    except Exception as e:
        # Catches critical errors outside the per-request handling (e.g., MongoDB disconnection)
        logger.critical(f"FATAL: Critical error in queue processing loop: {e}")
    finally:
        # Ensure the flag is reset whether the loop breaks naturally or due to a critical error
        queue_processing = False

#handle prompt funtion
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        logger.warning("Received an update without a valid message or text.")
        return

    user_prompt = update.message.text
    user_id = update.effective_user.id
    first_name = update.message.from_user.first_name

    user_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_prompt": user_prompt}},
        upsert=True
    )

    # Retrieve user data from the database
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data or not user_data.get('can_generate', False):
        await update.message.reply_text(
            "🔐 You are not authorized to generate images. Please join the required channels. /start"
        )
        return

    # Check if the user is a pro user
    is_pro_user = user_data.get("pro_user", False)
    request_limit = 15 if is_pro_user else 5  # Pro users get 15 concurrent requests, others get 5

    # Count the number of pending requests for the user
    pending_requests = queue_collection.count_documents({"chat_id": user_id})

    if pending_requests >= request_limit:
        await update.message.reply_text(
            f"🚫 Oops! You already have {pending_requests} pending requests. Please wait for them to be processed before submitting more."
        )
        return

    # Add the user's request to the queue
    user_request = {
        "chat_id": user_id,
        "prompt": user_prompt,
        "width": user_data.get("image_size", "1385x2048").split('x')[0],
        "height": user_data.get("image_size", "1385x2048").split('x')[1],
        "model": user_data.get("selected_model", "flux"),
        "is_pro_user": is_pro_user,
        "timestamp": datetime.now(timezone.utc),  # Use timezone-aware datetime
    }
    queue_collection.insert_one(user_request)

    # Notify the user about their position in the queue
    total_requests = queue_collection.count_documents({})
    queue_position = queue_collection.count_documents({"timestamp": {"$lt": user_request["timestamp"]}}) + 1

    await update.message.reply_text(
        f"🌀 Your request is now in the queue! \n✨<b>Your position:</b> {queue_position}/{total_requests}.\n⌚<b>Estimated time:</b> {queue_position * ESTIMATED_TIME_PER_REQUEST} seconds",
        parse_mode="HTML"
    )
    
# Function to start the queue processing task right after the application starts
async def on_app_start(application: Application):
    """Schedules the queue processing to run continuously using the JobQueue."""
    # We use job_queue.run_repeating instead of asyncio.create_task to ensure the
    # task is restarted if it fails, which is common for infinite loops.
    application.job_queue.run_repeating(
        callback=process_queue,
        interval=20,  # Check the queue every 5 seconds
        first=1,     # Start 1 second after bot initialization
        name="queue_processor"
    )
    logger.info("Queue processor scheduled to run every 5 seconds.")

# Initialize an async bot application
# NOTE: We add the 'post_init' hook here
application = Application.builder().token(TOKEN).post_init(on_app_start).build()

# Publish button callback handler
async def handle_publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # Create confirmation buttons
    keyboard = [
        [
            InlineKeyboardButton("❌ Don't Share", callback_data=f"cancel_publish:{user_id}"),
            InlineKeyboardButton("✅ Share", callback_data=f"confirm_publish:{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit the original message to replace old buttons with confirmation buttons
    await query.message.edit_reply_markup(reply_markup=reply_markup)

async def handle_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    action, uid = query.data.split(":")
    
    # Ensure only the correct user can confirm/cancel
    if int(uid) != user_id:
        await query.answer("You are not allowed to perform this action.")
        return

    if action == "cancel_publish":
        await query.answer("❌ Image publishing canceled.")

        # Restore original buttons
        await query.message.edit_reply_markup(reply_markup=get_generated_image_keyboard())

    elif action == "confirm_publish":
        user_link = f'<a href="tg://user?id={user_id}">{user.first_name}</a>'
        
        # Retrieve the prompt from the database
        user_data = user_collection.find_one({"user_id": user_id})
        prompt = user_data.get("last_prompt", "No prompt found") if user_data else "No prompt found"

        # Check if the message contains a photo or document
        if query.message.photo:
            media_type = "photo"
            file_id = query.message.photo[-1].file_id
        elif query.message.document:
            media_type = "document"
            file_id = query.message.document.file_id
        else:
            await query.answer("⚠️ No image or document found. Please try again with a valid file.")
            return

        caption = f"👤 User: {user_link}\n\n📩 Prompt: {prompt}\n\n✨made with @St_diffusion_bot"

        try:
            # Forward the media to the channel
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id="@LiveFeed_Of_Ai",
                    photo=file_id,
                    caption=caption,
                    parse_mode="HTML",
                )
            elif media_type == "document":
                await context.bot.send_document(
                    chat_id="@LiveFeed_Of_Ai",
                    document=file_id,
                    caption=caption,
                    parse_mode="HTML",
                )

            await query.answer("📣 Your image has been published!")
            await context.bot.send_message(
                chat_id=user_id,
                text="Your image has been published📣 at @LiveFeed_Of_Ai and @AIPromptsh!"
            )

            # Increment the published count in the database
            user_collection.update_one(
                {"user_id": user_id},
                {"$inc": {"published_count": 1}},
                upsert=True  # Ensures the document exists; creates if not
            )

        except Exception as e:
            await query.answer("⚠️ Failed to publish the image. Please try again later.")

        # Restore original buttons
        await query.message.edit_reply_markup(reply_markup=get_generated_image_keyboard())

# /help command handler
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    Here are the commands you can use:

/start - Start the bot 🙌.\n
/me - View your stats 📊.\n
/settings - Change your image size and model 📏.\n
/prompt <idea> - Create a detailed prompt from a simple idea 📩.\n
/models - Select a model 🎨.\n
/top - View the top 🔝 users.\n
/ptop - View the top 🔝 published users.\n
/100 - See users who have generated 100+ images.\n
/support <your message> - Contact 📞 the support team.\n
/refer - Get your referral link and track referrals 🔗.\n

Join our support group for guidance👇\n@TeamAiSupport
    """
    await update.message.reply_text(help_text)

# Callback handler for "Next ⏭️" button
async def handle_next_image_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # Retrieve the prompt from the database
    user_data = user_collection.find_one({"user_id": user_id})
    prompt = user_data.get("last_prompt", "No prompt found") if user_data else "No prompt found"

    if prompt == "No prompt found":
        await query.answer("No prompt found. Please send a new prompt.")
        return

    # Retrieve user data from the database
    user_data = user_collection.find_one({"user_id": user_id})

    # Get the user's selected size or use the default size
    selected_size = user_data.get("image_size", "1385x2048")
    width, height = map(int, selected_size.split('x'))

    # Get the user's selected model or use the default model
    selected_model = user_data.get("selected_model", "flux")

    # Check if the user is a pro user
    is_pro_user = user_data.get("pro_user", False)
    request_limit = 15 if is_pro_user else 5

    # Count the number of pending requests for the user
    pending_requests = queue_collection.count_documents({"chat_id": user_id})

    if pending_requests >= request_limit:
        await query.answer(f"🚫 Oops! You already have {pending_requests} pending requests. Please wait for them to be processed before submitting more.")
        return

    # Add the enhanced prompt to the queue in the database
    user_request = {
        "chat_id": user_id,
        "prompt": prompt,
        "width": width,
        "height": height,
        "model": selected_model,
        "is_pro_user": is_pro_user, # Added this field back for priority sorting
        "timestamp": datetime.now(timezone.utc),  # Use timezone-aware datetime
    }
    queue_collection.insert_one(user_request)

    # Count the total requests in the queue
    total_requests = queue_collection.count_documents({})

    # Calculate the user's position in the queue
    queue_position = queue_collection.count_documents({"timestamp": {"$lt": user_request["timestamp"]}}) + 1

    await query.answer("Generating a new image with the same prompt...")
    await query.message.reply_text(
        f"🌀 Your request is now in the queue! \n✨<b>Your position:</b> {queue_position}/{total_requests}.\n⌚<b>Estimated time:</b> {queue_position * ESTIMATED_TIME_PER_REQUEST} seconds.",
        parse_mode="HTML"
    )

    # The on_app_start hook handles starting the continuous processing job.


# Dictionary to store user images (Keeping this dict but removing logic)
user_images = {}

# /live command handler to display live statistics
async def live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return  # Restrict command to admin

    # Fetch total users from the database
    total_users_count = user_collection.count_documents({})  # Get the total count of users

    # Fetch the count of pending requests in the database queue
    pending_requests_count = queue_collection.count_documents({})

    await update.message.reply_text(
        f"📊 <b>Live Statistics</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users_count}\n"
        f"⏳ <b>Pending Requests:</b> {pending_requests_count}",
        parse_mode="HTML"
    )

# /models command handler
async def models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '''🌟 Available Models:  
1. Flux 🚀(Flux-Schnell) - A standard model for balanced quality and speed.  
2. Flux-Pro 🌌: (Flux 1.1) - Enhanced version with improved quality and precision.  
3. Flux CablyAI 🌟: A next-gen model focused on ultra-detailed,outputs.  
4. Turbo ⚡: A super-fast model optimized for quick results.  

✨ Select the model that suits your needs and start generating amazing images!''',
        reply_markup=get_models_keyboard()
    )

# Callback handler for model selection
async def select_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected_model = query.data.split("_")[1]
    user_id = update.effective_user.id

    # Delete the model selection message
    await query.message.delete()

    # Update the user's selected model in the database
    user_collection.update_one(
        {"user_id": user_id},
        {"$set": {"selected_model": selected_model}}
    )

    await query.answer(f"Model '{selected_model}' selected.")
    await query.message.reply_text(f"You have selected the🙌 '{selected_model}' model for image generation🎨.")


# /settings command handler
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Retrieve user data from the database
    user_data = user_collection.find_one({"user_id": user_id})
    if user_data:
        selected_model = user_data.get("selected_model", "flux")
        image_size = user_data.get("image_size", "1385x2048")
        is_pro_user = user_data.get("pro_user", False)
        delivery_preference = user_data.get("delivery_preference", "Fast")
    else:
        selected_model = "flux"
        image_size = "1385x2048"
        is_pro_user = False
        delivery_preference = "Fast"

    # Create the settings message
    message = (
        f"📊 <b>Your Settings:</b>\n\n"
        f"🛠️ <b>Selected Model:</b> {selected_model}\n"
        f"📏 <b>Image Size:</b> {image_size}\n"
        f"🚀 <b>Delivery Preference:</b> {delivery_preference}\n"
    )

    # Send the settings message with the settings keyboard
    await update.message.reply_text(
        text=message,
        parse_mode="HTML",
        reply_markup=get_settings_keyboard()
    )

# Callback handler for "Delivery Preference" button
async def delivery_preference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id

    # Retrieve user data from the database
    user_data = user_collection.find_one({"user_id": user_id})
    is_pro_user = user_data.get("pro_user", False) if user_data else False

    if is_pro_user:
        # Show options for "Quality" and "Fast" for pro users
        keyboard = [
            [InlineKeyboardButton("Quality 📄", callback_data="delivery_quality")],
            [InlineKeyboardButton("Fast ⚡", callback_data="delivery_fast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.answer()
        await query.message.reply_text("🚀 Select your delivery preference:", reply_markup=reply_markup)
    else:
        # Inform non-pro users that this feature is only for pro users
        await query.answer()
        await query.message.reply_text(
            "🚫 This feature is only available for Pro users. Upgrade to Pro to access advanced features! 🎉"
        )

# Callback handler for "Quality" and "Fast" selection
async def set_delivery_preference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id

    if query.data == "delivery_quality":
        preference = "Quality"
    elif query.data == "delivery_fast":
        preference = "Fast"
    else:
        await query.answer("Invalid selection.")
        return

    # Update the user's delivery preference in the database
    user_collection.update_one(
        {"user_id": user_id},
        {"$set": {"delivery_preference": preference}}
    )

    await query.answer(f"Delivery preference set to {preference}.")
    await query.message.delete()  # Delete the message after selection
    await query.message.reply_text(f"🚀 Your delivery preference has been updated to {preference}. 🎉")

# Callback handler for "Change Size" button
async def change_size_callback(update: Update):
    keyboard = [
        [InlineKeyboardButton("Landscape↔️", callback_data="size_landscape"), InlineKeyboardButton("Square🖼️", callback_data="size_square")],
        [InlineKeyboardButton("Portrait📱", callback_data="size_portrait"), InlineKeyboardButton("Portrait 2📱", callback_data="size_portrait_2")],
        [InlineKeyboardButton("Default🔁", callback_data="size_default")]
    ]
    await update.callback_query.message.reply_text(
        "Select the image size:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Callback handler for size selection
async def select_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    size_map = {
        "size_landscape": "1792x1024",
        "size_square": "1024x1024",
        "size_portrait": "1024x1792",
        "size_portrait_2": "1080x1350",
        "size_default": "1385x2048"
    }
    selected_size = size_map.get(query.data)
    user_id = update.effective_user.id

    if selected_size:
        # Update the user's selected size in the database
        user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"image_size": selected_size}}
        )

        await query.answer(f"Size '{selected_size}' selected.")
        await query.message.reply_text(f"You have selected the '{selected_size}' size for image generation.")
        await query.message.delete()  # Delete the inline message

# /broadcast command handler
# Initialize media files list
media_files = []

# Logger for errors
logger = logging.getLogger(__name__)


# Broadcast command handler
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the sender is the admin
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    if not context.args and not media_files:
        await update.message.reply_text(
            "⚠️ Please provide a message broadcasting. Use /broadcast <message>."
        )
        return

    # Combine the message arguments into a single string with line breaks
    broadcast_message = ' '.join(context.args) if context.args else ""
    broadcast_message = broadcast_message.replace('\\n', '\n')  # Replace '\n' with actual newlines

    await update.message.reply_text("📣 The broadcast process has started.")

    # Start the broadcast as a background task
    asyncio.create_task(start_broadcast(broadcast_message))


async def start_broadcast(broadcast_message):
    all_users = list(user_collection.find())  # Convert cursor to list for iteration
    success_count = 0
    failed_count = 0
    rate_limit_delay = 0.1  # Delay in seconds between each message

    async def send_broadcast(user):
        nonlocal success_count, failed_count
        user_id = user.get("user_id")
        if not user_id:
            return

        try:
            if media_files:  # Case: Media with optional text
                media = [
                    InputMediaPhoto(media=media_files[0], caption=broadcast_message, parse_mode='HTML')
                ]
                # Add additional media files if present
                for media_id in media_files[1:]:
                    media.append(InputMediaPhoto(media=media_id))

                await application.bot.send_media_group(chat_id=user_id, media=media)
            else:  # Case: Text-only broadcast
                await application.bot.send_message(chat_id=user_id, text=broadcast_message, parse_mode='HTML')

            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send message to {user_id}: {e}")
            failed_count += 1

    async def rate_limited_broadcast(users):
        for user in users:
            await send_broadcast(user)
            await asyncio.sleep(rate_limit_delay)  # Add delay to respect API rate limits

    # Divide users into manageable chunks
    chunk_size = 50
    user_chunks = [all_users[i:i + chunk_size] for i in range(0, len(all_users), chunk_size)]

    for chunk in user_chunks:
        await rate_limited_broadcast(chunk)

    # Notify the admin about the broadcast results
    await application.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"✅ Broadcast complete!\n\n✔️ Successful: {success_count}\n❌ Failed: {failed_count}"
    )

    # Clear media_files after broadcasting
    media_files.clear()

# /list command handler to display all user IDs, names/user links, and number of images generated
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Fetch all users from the database
    all_users = user_collection.find({})  # Query all users
    user_list = []

    for user in all_users:
        user_id = user.get("user_id")
        first_name = user.get("first_name", "Unknown")
        username = user.get("username")
        prompts_generated = user.get("prompts_generated", 0)  # Total images generated

        # Create the user link
        user_link = f"<a href='tg://user?id={user_id}'>{first_name}</a>" if username else first_name

        # Prepare user information
        user_info = f"👤 {user_link} (ID: {user_id})\n📊 Images Generated: {prompts_generated}"
        user_list.append(user_info)

    # Send the list in chunks to avoid Telegram message length limits
    chunk_size = 50
    for i in range(0, len(user_list), chunk_size):
        chunk = user_list[i:i + chunk_size]
        await update.message.reply_text(
            "\n\n".join(chunk),
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    await update.message.reply_text("✅ User list has been sent.")

# /stats command handler
async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Query database for statistics
    total_users = user_collection.count_documents({})
    active_users = user_collection.count_documents({"can_generate": True})
    inactive_users = total_users - active_users
    total_pro_users = user_collection.count_documents({"pro_user": True})  # Count total pro users

    # Example: Count users joined in the last week
    from datetime import datetime, timedelta
    last_week = datetime.now() - timedelta(days=7)
    # The 'joined_date' field is not set in 'start' handler, so this count will be 0.
    # Assuming 'joined_date' should have been added on user creation for this to work.
    new_users_last_week = user_collection.count_documents({"joined_date": {"$gte": last_week}}) 

    # Calculate the total number of images generated
    total_images_generated = user_collection.aggregate([
        {"$group": {"_id": None, "total_images": {"$sum": "$prompts_generated"}}}
    ])
    total_images_generated = next(total_images_generated, {}).get("total_images", 0)

    # Calculate the total number of published images
    total_published_count = user_collection.aggregate([
        {"$group": {"_id": None, "total_published": {"$sum": "$published_count"}}}
    ])
    total_published_count = next(total_published_count, {}).get("total_published", 0)

    # Calculate the total referral count
    # Correcting the aggregation query to use the 'referral_count' field directly.
    total_referrals = user_collection.aggregate([
        {"$group": {"_id": None, "total_referrals": {"$sum": {"$ifNull": ["$referral_count", 0]}}}}
    ])
    total_referrals = next(total_referrals, {}).get("total_referrals", 0)

    # Send statistics to the user
    await update.message.reply_text(
        f"📊 <b>User Statistics</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"🟢 <b>Active Users:</b> {active_users}\n"
        f"🔴 <b>Inactive Users:</b> {inactive_users}\n"
        f"💎 <b>Total Pro Users:</b> {total_pro_users}\n"
        f"🖼️ <b>Total Images Generated:</b> {total_images_generated}\n"
        f"📣 <b>Total Published Images:</b> {total_published_count}\n"
        f"🔗 <b>Total Referrals:</b> {total_referrals}",
        parse_mode="HTML"
    )
# /top command handler
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Fetch top 15 users sorted by prompts_generated in descending order
    top_users = user_collection.find().sort("prompts_generated", -1).limit(15)
    
    # Prepare the message
    message = "🏆 <b>Top 15 Users Who Generated the Most Images:</b>\n\n"
    
    rank = 1
    user_found_in_top = False
    for user in top_users:
        current_user_id = user.get("user_id", 0)
        first_name = user.get("first_name", "Unknown")
        prompts_generated = user.get("prompts_generated", 0)
        
        # Create a clickable link for the user
        user_link = f"<a href='tg://user?id={current_user_id}'>{first_name}</a>"
        
        # Format the user's info
        message += (
            f"{rank}. {user_link}\n"
            f"   🖼️ Images Generated: <b>{prompts_generated}</b>\n"
        )
        if current_user_id == user_id:
            message += "🏅 <b>your rank👆</b>\n"
        
        # Check if the current user is in the top 15
        if current_user_id == user_id:
            user_found_in_top = True
        
        rank += 1
    
    # If no users found, inform the user
    if rank == 1:
        message = "📊 No users have generated texts yet."
    
    # If the user is not in the top 15, calculate their rank
    if not user_found_in_top:
        user_data = user_collection.find_one({"user_id": user_id})
        if user_data:
            user_prompts_generated = user_data.get("prompts_generated", 0)
            user_rank = user_collection.count_documents({"prompts_generated": {"$gt": user_prompts_generated}}) + 1
            message += (
                f"\n\n📊 <b>Your Rank:</b> {user_rank}\n"
                f"   🖼️ Images Generated: <b>{user_prompts_generated}</b>"
            )
        else:
            message += "\n\n⚠️ You have not generated any images yet."

    # Send the top users' stats
    await update.message.reply_text(message, parse_mode="HTML")

# /ptop command handler
async def ptop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fetch top 15 users sorted by published_count in descending order
    top_published_users = user_collection.find().sort("published_count", -1).limit(15)
    
    # Prepare the message
    message = "🏆 <b>Top 15 Users Who Published the Most Content:</b>\n\n"
    
    rank = 1
    for user in top_published_users:
        user_id = user.get("user_id", 0)
        first_name = user.get("first_name", "Unknown")
        published_count = user.get("published_count", 0)
        
        # Create a clickable link for the user
        user_link = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        
        # Format the user's info
        message += (
            f"{rank}. {user_link}\n"
            f"   📣 Published Content: <b>{published_count}</b>\n"
        )
        rank += 1
    
    # If no users found, inform the user
    if rank == 1:
        message = "📊 No users have published content yet."
    
    # Send the top users' stats
    await update.message.reply_text(message, parse_mode="HTML")

# /message command handler to send a message to a specific user
async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Check if a user ID and message were provided
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Please provide a user ID and the message text.")
        return

    user_id = context.args[0]  # The first argument is the user ID
    message_text = " ".join(context.args[1:])  # The rest is the message text

    # Send the message to the user with the given user_id
    try:
        await context.bot.send_message(chat_id=user_id, text=message_text)
        await update.message.reply_text(f"✅ Message sent to user {user_id}.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to send message: {e}")

# /support command handler to send a user message to the support group
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the user provided a message
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Please provide your message like this /support your message.")
        return
    
    # Get the user's message and their user details
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Unknown"
    username = update.effective_user.username or "No Username"
    
    # Create the user link
    user_link = f"<a href='tg://user?id={user_id}'>{first_name}</a>"

    # Get the user's support message
    user_message = " ".join(context.args)

    # Format the message to be sent to the support group
    support_message = f"""
    🆘 <b>Support Request</b> 🆘
    
    👤 <b>User</b>: {user_link}
    🆔 <b>User ID</b>: {user_id}
    
    📩 <b>Message</b>: {user_message}
    """

    # Send the formatted message to the support group
    try:
        await context.bot.send_message(chat_id='@TeamAI_Bot_Support', text=support_message, parse_mode='HTML')
        await update.message.reply_text("✅ Your message has been sent to the support team.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to send the message: {e}")

# /clear command handler
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Notify users whose requests are being deleted
    users_in_queue = queue_collection.distinct("chat_id")
    for user_id in users_in_queue:
        try:
            await application.bot.send_message(
                chat_id=user_id,
                text="❌ Your request has been cleared from the queue. Please try submitting a new one."
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

    # Clear the queue from the database
    queue_collection.delete_many({})

    # Notify admin and the user who initiated the command
    await update.message.reply_text("✅ All requests in the queue have been cleared.")
    await application.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text="⚠️ The queue has been cleared by the admin. All pending requests have been removed."
    )

# /me command handler
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Retrieve user data from MongoDB or use the image_counter
    user_data = user_collection.find_one({"user_id": user_id})
    if user_data:
        images_generated = user_data.get("prompts_generated", 0)
        selected_model = user_data.get("selected_model", "flux")
        published_count = user_data.get("published_count", 0)
        is_pro_user = user_data.get("pro_user", False)  # Check if the user is a pro user
        credits = "♾️" if is_pro_user else user_data.get("credits", 0)
        # Fix: use 'referral_count' field directly which is updated in start handler
        referral_count = user_data.get("referral_count", 0) 
    else:
        images_generated = image_counter.get(user_id, 0)
        selected_model = "flux"
        published_count = 0
        is_pro_user = False
        credits = 0
        referral_count = 0

    pro_status = "✅ Yes" if is_pro_user else "❌ No"  # Display pro status

    await update.message.reply_text(
        f"📊 <b>Your Stats:</b>\n\n"
        f"🖼️ <b>Images Generated:</b> {images_generated}\n"
        f"🛠️ <b>Selected Model:</b> {selected_model}\n"
        f"📏 <b>Selected Size:</b> {user_data.get('image_size', '1385x2048')}\n"
        f"🚀 <b>Delivery Preference:</b> {user_data.get('delivery_preference', 'Fast')}\n"
        f"📣 <b>Published Content:</b> {published_count}\n"
        f"🔗 <b>Referrals:</b> {referral_count}\n"
        f"💰 <b>Credits:</b> {credits}\n"
        f"💎 <b>Pro User:</b> {pro_status}\n",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Change Model⚙️", callback_data="change_model"), InlineKeyboardButton("Change Size📏", callback_data="change_size")],
            [InlineKeyboardButton("Delivery Preference🚀", callback_data="delivery_preference")]
        ])
    )

# Callback handler for "Change Model" button
async def change_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        '''🌟 Available Models:  
1. Flux 🚀(Flux-Schnell) - A standard model for balanced quality and speed.  
2. Flux-Pro 🌌: (Flux 1.1) - Enhanced version with improved quality and precision.  
3. Flux CablyAI 🌟: A next-gen model focused on ultra-detailed,outputs.  
4. Turbo ⚡: A super-fast model optimized for quick results.  

✨ Select the model that suits your needs and start generating amazing images!''',
        reply_markup=get_models_keyboard()
    )

# Callback handler for "Change Size" button
async def change_size_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Landscape↔️", callback_data="size_landscape"), InlineKeyboardButton("Square🖼️", callback_data="size_square")],
        [InlineKeyboardButton("Portrait📱", callback_data="size_portrait"), InlineKeyboardButton("Portrait 2📱", callback_data="size_portrait_2")],
        [InlineKeyboardButton("Default🔁", callback_data="size_default")]
    ]
    await update.callback_query.message.reply_text(
        "Select the image size:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Function to convert MongoDB ObjectId to string
def convert_objectid_to_str(document):
    if isinstance(document, dict):
        return {k: convert_objectid_to_str(v) for k, v in document.items()}
    elif isinstance(document, list):
        return [convert_objectid_to_str(item) for item in document]
    elif isinstance(document, ObjectId):
        return str(document)
    else:
        return document
    
# /database command handler to send all user data
async def database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Fetch all users from the database
    all_users = user_collection.find({})  # Query all users

    # Create a list to store the user data in JSON format
    user_data_list = []
    for user in all_users:
        user_data_list.append(convert_objectid_to_str(user))  # Convert ObjectId to string

    # Convert the list to JSON format
    user_data_json = json.dumps(user_data_list, indent=4)

    # Use tempfile to create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, mode="w", encoding="utf-8") as temp_file:
        temp_file.write(user_data_json)
        temp_file_path = temp_file.name

    # Send the file to the admin
    with open(temp_file_path, "rb") as file:
        await update.message.reply_document(
            document=InputFile(file, filename="user_data.json"),
            caption="Here is the full user data."
        )

    # Optionally, clean up the temporary file
    os.remove(temp_file_path)

# /100 command handler
async def list_hundred_plus_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Query users who have generated 100 or more images, sorted by 'prompts_generated' in descending order
    hundred_plus_users = user_collection.find({"prompts_generated": {"$gte": 100}}).sort("prompts_generated", -1)
    user_list = []
    rank = 1

    for user in hundred_plus_users:
        user_id = user.get("user_id")
        first_name = user.get("first_name", "Unknown")
        username = user.get("username")
        prompts_generated = user.get("prompts_generated", 0)

        # Create a clickable user link
        user_link = (
            f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        )

        # Prepare user information
        user_info = f"{rank}. {user_link}\n   🎨 Images Generated: {prompts_generated}"
        user_list.append(user_info)
        rank += 1

    # Check if there are any users in the list
    if not user_list:
        await update.message.reply_text("📊 No users have generated 100 or more images.")
        return

    # Send the list in chunks to avoid Telegram message length limits
    chunk_size = 30  # Adjust based on message limits
    for i in range(0, len(user_list), chunk_size):
        chunk = user_list[i:i + chunk_size]
        message = "🏆 <b>Users Who Generated More Than 100 Images:</b>\n\n" + "\n".join(chunk)
        await update.message.reply_text(
            message,
            parse_mode="HTML",
            disable_web_page_preview=True  # Prevent unnecessary previews
        )

# /prompt command handler
async def handle_prompt_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) == 0:
        await update.message.reply_text("Please provide a prompt idea. Usage: /prompt <idea>")
        return

    idea = " ".join(context.args)
    system_prompt = "You are an advanced AI prompt generator specializing in creating short, high-quality prompts for AI image generation. When a user types anything, generate a concise yet detailed AI prompt that enhances creativity and visual appeal. Keep the prompt relevant to the keyword while adding creative elements, lighting, and composition details when appropriate. Keep the prompts short and effective (around 50-100 words). Avoid generic descriptions—make them visually engaging and artistically rich. If the user provides only a simple word (e.g., 'cat'), expand it into an artistic concept (e.g., 'A majestic feline basking in golden sunlight, cinematic lighting, ultra-detailed fur and add more details'). Ensure prompts align with AI capabilities. If the keyword is unclear, interpret it creatively instead of leaving it blank and also dont use any special characters in prompt."
    seed = random.randint(1, 1000000)
    model = "mistral"
    url = f"https://text.pollinations.ai/{urllib.parse.quote(idea)}?system={urllib.parse.quote(system_prompt)}&seed={seed}&model={model}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                generated_prompt = await response.text()
                await update.message.reply_text(f"{generated_prompt}")
            else:
                await update.message.reply_text("Failed to generate prompt. Please try again later.")

# /clearprompt command handler
async def clear_prompt_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) == 0:
        await update.message.reply_text("Please provide a prompt. Usage: /clearprompt <prompt>")
        return

    idea = " ".join(context.args)
    system_prompt = "You are an AI bot that filters and refines user prompts by removing exploitative and NSFW content while maintaining creativity and artistic value. When a user inputs a prompt, analyze the text, replace inappropriate words with suitable alternatives, and ensure the final output remains high-quality and visually engaging. Keep prompts concise (50-150 words), enhancing them with artistic elements like lighting, composition, and textures. If necessary, reinterpret unclear keywords creatively while ensuring all content aligns with AI safety guidelines. and also only send the refined prompt no other words"
    seed = random.randint(1, 1000000)
    model = "mistral"
    url = f"https://text.pollinations.ai/{urllib.parse.quote(idea)}?system={urllib.parse.quote(system_prompt)}&seed={seed}&model={model}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                generated_prompt = await response.text()
                await update.message.reply_text(f"{generated_prompt}")
            else:
                await update.message.reply_text("Failed to generate prompt. Please try again later.")

# /pro command handler to add a user as a premium user
async def pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Please provide a user ID. Usage: /pro <user_id>")
        return

    user_id = int(context.args[0])

    # Update the user in the database to set them as a premium user
    user_collection.update_one(
        {"user_id": user_id},
        {"$set": {"pro_user": True}},
        upsert=True  # Create the document if it doesn't exist
    )

    # Notify the user about their promotion
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 Congratulations! You have been promoted to a Pro User. Enjoy your enhanced benefits! 🚀"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about Pro promotion: {e}")

    await update.message.reply_text(f"✅ User {user_id} has been added as a premium user.")

# /unpro command handler to remove a user from the premium list
async def unpro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Please provide a user ID. Usage: /unpro <user_id>")
        return

    user_id = int(context.args[0])

    # Update the user in the database to remove them from the premium list
    user_collection.update_one(
        {"user_id": user_id},
        {"$set": {"pro_user": False}}
    )

    # Notify the user about their removal from the premium list
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ You have been removed from the Pro User list. If you believe this is a mistake, please contact support."
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about Pro removal: {e}")

    await update.message.reply_text(f"✅ User {user_id} has been removed from the premium list.")


# /prolist command handler
async def prolist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Fetch all pro users from the database
    pro_users = user_collection.find({"pro_user": True})
    user_list = []

    for user in pro_users:
        user_id = user.get("user_id")
        first_name = user.get("first_name", "Unknown")
        username = user.get("username", "No Username")

        # Create a clickable user link
        user_link = f"<a href='tg://user?id={user_id}'>{first_name}</a>"

        # Prepare user information
        user_info = f"👤 {user_link} (ID: {user_id})\n"
        user_list.append(user_info)

    # Check if there are any pro users
    if not user_list:
        await update.message.reply_text("📊 No pro users found.")
        return

    # Send the list in chunks to avoid Telegram message length limits
    chunk_size = 50
    for i in range(0, len(user_list), chunk_size):
        chunk = user_list[i:i + chunk_size]
        await update.message.reply_text(
            "\n".join(chunk),
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    await update.message.reply_text("✅ Pro user list has been sent.")


# /refer command to display the user's referral link, count, and balance
async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_link = f"https://t.me/St_diffusion_bot?start=ref_{user_id}"

    # Fetch the user's referral count and balance from the database
    user_data = user_collection.find_one({"user_id": user_id})
    if user_data:
        is_pro_user = user_data.get("pro_user", False)
        balance = "♾️" if is_pro_user else user_data.get("credits", 0)
        # Fix: use 'referral_count' field directly which is updated in start handler
        referral_count = user_data.get("referral_count", 0) 
    else:
        referral_count = 0
        balance = 0

    await update.message.reply_text(
        f"🎉 Share this link with your friends to earn credits:\n\n{referral_link}\n\n"
        f"💰 <b>Balance:</b> {balance} credits\n"
        f"🔗 <b>Referrals:</b> {referral_count}\n\n"
        "You will earn 30 credits for each user who joins using your link!",
        parse_mode="HTML"
    )

# /remove command to remove a user from the database
async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Please provide a user ID. Usage: /remove <user_id>")
        return

    user_id = int(context.args[0])

    # Remove the user from the database
    result = user_collection.delete_one({"user_id": user_id})

    if result.deleted_count > 0:
        await update.message.reply_text(f"✅ User {user_id} has been removed from the database.")
    else:
        await update.message.reply_text(f"⚠️ User {user_id} not found in the database.")

# /topref command to display the top 15 users with the most referrals to admin only
async def topref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Fetch top 15 users sorted by referral_count in descending order
    top_referrers = user_collection.find({"referral_count": {"$exists": True}}).sort("referral_count", -1).limit(20)
    
    # Prepare the message
    message = "🏆 <b>Top 15 Users with the Most Referrals:</b>\n\n"
    
    rank = 1
    for user in top_referrers:
        user_id = user.get("user_id", 0)
        first_name = user.get("first_name", "Unknown")
        referral_count = user.get("referral_count", 0)
        
        # Create a clickable link for the user
        user_link = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        
        # Format the user's info
        message += (
            f"{rank}. {user_link}\n"
            f"   🔗 Referrals: <b>{referral_count}</b>\n"
        )
        rank += 1
    
    # If no users found, inform the admin
    if rank == 1:
        message = "📊 No users have made referrals yet."
    
    # Send the top referrers' stats
    await update.message.reply_text(message, parse_mode="HTML")


# /userstats command handler to display user statistics
async def userstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Please provide a user ID. Usage: /userstats <user_id>")
        return

    user_id = int(context.args[0])

    # Fetch user data from the database
    user_data = user_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text(f"⚠️ User with ID {user_id} not found in the database.")
        return

    # Extract user details
    first_name = user_data.get("first_name", "Unknown")
    username = user_data.get("username", "No Username")
    prompts_generated = user_data.get("prompts_generated", 0)
    published_count = user_data.get("published_count", 0)
    is_pro_user = user_data.get("pro_user", False)
    credits = "♾️" if is_pro_user else user_data.get("credits", 0)
    referral_count = user_data.get("referral_count", 0)
    faceswap_count = user_data.get("faceswap_count", 0)
    upscale_count = user_data.get("upscale_count", 0)
    selected_model = user_data.get("selected_model", "flux")
    image_size = user_data.get("image_size", "1385x2048")
    delivery_preference = user_data.get("delivery_preference", "Fast")

    # Calculate user's rank in top users
    user_rank = user_collection.count_documents({"prompts_generated": {"$gt": prompts_generated}}) + 1

    # Create a clickable user link
    user_link = f"<a href='tg://user?id={user_id}'>{first_name}</a>"

    # Prepare the statistics message
    stats_message = (
        f"📊 <b>User Statistics:</b>\n\n"
        f"👤 <b>User:</b> {user_link}\n"
        f"🆔 <b>User ID:</b> {user_id}\n"
        f"📛 <b>Username:</b> @{username}\n\n"
        f"🖼️ <b>Images Generated:</b> {prompts_generated}\n"
        f"📣 <b>Published Content:</b> {published_count}\n"
        f"💎 <b>Pro User:</b> {'✅ Yes' if is_pro_user else '❌ No'}\n"
        f"💰 <b>Credits:</b> {credits}\n"
        f"🔗 <b>Referrals:</b> {referral_count}\n"
        f"🤖 <b>Selected Model:</b> {selected_model}\n"
        f"📏 <b>Image Size:</b> {image_size}\n"
        f"🚀 <b>Delivery Preference:</b> {delivery_preference}\n"
        # Removed faceswap_count and upscale_count from display
        f"🏅 <b>Rank in Top Users:</b> {user_rank}\n"
    )

    await update.message.reply_text(stats_message, parse_mode="HTML")

# /admin command handler to see all admin commands
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    admin_commands = """
    🛠️ <b>Admin Commands:</b>
    
    /live - View live statistics 📊
    /broadcast <message> - Broadcast a message to all users 📣
    /list - List all users 👥
    /stats - View overall user statistics 📈
    /100 - List users who generated 100+ images 🎨
    /database - Download the user database 📂
    /message <user_id> <message> - Send a message to a specific user ✉️
    /remove <user_id> - Remove a user from the database ❌
    /pro <user_id> - Promote a user to Pro 💎
    /unpro <user_id> - Remove Pro status from a user 🚫
    /prolist - List all Pro users 💎
    /topref - View top users by referrals 🔗
    /userstats <user_id> - View detailed stats of a specific user 📊
    /clear - Clear all pending requests from the queue 🗑️
    """
    await update.message.reply_text(admin_commands, parse_mode="HTML")


# Simple function to start the HTTP server in a separate thread
def run_health_check_server():
    # Use ThreadingTCPServer to avoid blocking the main async loop
    class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            # Always respond with a 200 OK status for the health check
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Bot is alive and polling.")

    # Start the server on the required port
    try:
        with socketserver.ThreadingTCPServer(("", HEALTH_CHECK_PORT), HealthCheckHandler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Health Check Server failed to start: {e}")

# Add command handlers to the application
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(joined, pattern="^joined$"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
application.add_handler(CommandHandler("live", live))
application.add_handler(CommandHandler("broadcast", broadcast))
application.add_handler(CommandHandler("list", list_users))
application.add_handler(CommandHandler("stats", user_stats))
application.add_handler(CommandHandler("top", top))
application.add_handler(CommandHandler("message", send_message))
application.add_handler(CommandHandler("support", support))
application.add_handler(CommandHandler("help", help))
application.add_handler(CommandHandler("clear", clear))
application.add_handler(CommandHandler("me", me))
application.add_handler(CommandHandler("database", database))
application.add_handler(CommandHandler("100", list_hundred_plus_users))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
application.add_handler(CallbackQueryHandler(handle_donate_callback, pattern="^donate$"))
application.add_handler(CallbackQueryHandler(handle_donate, pattern=r"^donate_\d+$"))
application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
application.add_handler(CommandHandler("models", models))
application.add_handler(CallbackQueryHandler(change_model_callback, pattern="^change_model$"))
application.add_handler(CallbackQueryHandler(select_model, pattern=r"^model_"))
application.add_handler(CallbackQueryHandler(handle_publish_callback, pattern="^publish$"))
application.add_handler(CommandHandler("ptop", ptop))
application.add_handler(CommandHandler("prompt", handle_prompt_command))
application.add_handler(CommandHandler("clearprompt", clear_prompt_command))
application.add_handler(CallbackQueryHandler(handle_next_image_callback, pattern="^next_image$"))
application.add_handler(CommandHandler("settings", settings))
application.add_handler(CallbackQueryHandler(change_size_callback, pattern="^change_size$"))
application.add_handler(CallbackQueryHandler(select_size, pattern=r"^size_"))
application.add_handler(CallbackQueryHandler(handle_confirmation_callback, pattern="^(cancel_publish|confirm_publish):"))
application.add_handler(CommandHandler("pro", pro))
application.add_handler(CommandHandler("unpro", unpro))
application.add_handler(CallbackQueryHandler(delivery_preference_callback, pattern="^delivery_preference$"))
application.add_handler(CallbackQueryHandler(set_delivery_preference, pattern="^delivery_(quality|fast)$"))
application.add_handler(CommandHandler("prolist", prolist))
application.add_handler(CommandHandler("refer", refer))
application.add_handler(CommandHandler("remove", remove_user))
application.add_handler(CommandHandler("topref", topref))
application.add_handler(CommandHandler("userstats", userstats))
application.add_handler(CommandHandler("admin", admin))

# Run the bot
if __name__ == '__main__':
    # 1. Start the Health Check Server in a separate thread
    # This must run BEFORE the blocking run_polling() call
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    # 2. Start the main Telegram long polling loop (This is a BLOCKING call)
    try:
        application.run_polling()
    except Exception as e:
        logger.error(f"Telegram Bot Polling Failed: {e}")
