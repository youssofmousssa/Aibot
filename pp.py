import os
import base64
import asyncio
from io import BytesIO
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction

# Initialize rich console
console = Console()

# Configuration
TELEGRAM_TOKEN = "8189213742:AAEaqylJAdHgkYA9dUXi27L9_uMeY9KnM_0"
A4F_API_KEY = "ddc-a4f-93fa3ba5eb0d46d8af0a3534fd623dba"
A4F_BASE_URL = "https://api.a4f.co/v1"

# Initialize OpenAI client for A4F
a4f_client = OpenAI(
    api_key=A4F_API_KEY,
    base_url=A4F_BASE_URL,
)

def log_request(user_id: int, request_type: str, content: str):
    """Log user requests with rich formatting"""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Field", style="dim")
    table.add_column("Value")
    
    table.add_row("User ID", str(user_id))
    table.add_row("Request Type", request_type)
    table.add_row("Content", content[:200] + "..." if len(content) > 200 else content)
    
    console.print(Panel.fit(table, title="📨 Incoming Request"))

def log_response(user_id: int, response: str, processing_time: float):
    """Log bot responses with rich formatting"""
    text = Text()
    text.append(f"Response to user {user_id}:", style="bold green")
    text.append("\n")
    text.append(response[:500] + ("..." if len(response) > 500 else ""), style="green")
    text.append(f"\n\n⏱️ Processed in {processing_time:.2f}s", style="dim")
    
    console.print(Panel.fit(text, title="📤 Bot Response"))

def log_error(user_id: int, error: Exception):
    """Log errors with rich formatting"""
    console.print(
        Panel.fit(
            f"🚨 Error for user {user_id}:\n{str(error)}",
            style="bold red",
            title="Error",
        )
    )

async def send_typing_indicator(update: Update):
    """Send typing action to user"""
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except Exception as e:
        log_error(update.effective_user.id, e)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    log_request(update.effective_user.id, "Command", "/start")
    await send_typing_indicator(update)
    await update.message.reply_text(
        "👋 Hello! I'm your AI assistant. You can:\n"
        "- Ask me anything in text\n"
        "- Send me images with questions in the caption\n"
        "- I'll do my best to understand and respond!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    log_request(update.effective_user.id, "Command", "/help")
    await send_typing_indicator(update)
    help_text = """
    🤖 Bot Help Guide:
    
    📝 Text Messages:
    Just send me any text question or message, and I'll respond.
    
    🖼️ Image Messages:
    Send an image with a caption/question like:
    - "What is this landmark?"
    - "Explain this diagram"
    - "What's in this picture?"
    
    I'll analyze both the image and your question to provide the best answer.
    """
    await update.message.reply_text(help_text)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    log_request(user_id, "Text", user_message)
    
    try:
        await send_typing_indicator(update)
        start_time = asyncio.get_event_loop().time()
        
        response = await asyncio.to_thread(
            generate_text_response,
            user_message
        )
        
        processing_time = asyncio.get_event_loop().time() - start_time
        log_response(user_id, response, processing_time)
        
        await update.message.reply_text(response)
    except Exception as e:
        log_error(user_id, e)
        await update.message.reply_text("⚠️ Sorry, I encountered an error processing your text message.")

async def handle_image_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image messages with optional captions"""
    user_id = update.effective_user.id
    caption = update.message.caption or "What is in this image?"
    
    log_request(user_id, "Image", f"Caption: {caption}")
    
    try:
        await send_typing_indicator(update)
        start_time = asyncio.get_event_loop().time()
        
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        image_file = await photo.get_file()
        image_bytes = await image_file.download_as_bytearray()
        
        # Convert to base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        response = await asyncio.to_thread(
            generate_image_response,
            base64_image,
            caption
        )
        
        processing_time = asyncio.get_event_loop().time() - start_time
        log_response(user_id, response, processing_time)
        
        await update.message.reply_text(response)
    except Exception as e:
        log_error(user_id, e)
        await update.message.reply_text("⚠️ Sorry, I couldn't process your image. Please try again.")

def generate_text_response(prompt: str) -> str:
    """Generate response for text-only prompts"""
    try:
        completion = a4f_client.chat.completions.create(
            model="provider-3/gemini-2.5-pro-preview-06-05",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        console.print(f"[bold red]API Error:[/bold red] {str(e)}")
        raise

def generate_image_response(base64_image: str, prompt: str) -> str:
    """Generate response for image + prompt"""
    try:
        completion = a4f_client.chat.completions.create(
            model="provider-3/gemini-2.5-pro-preview-06-05",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        console.print(f"[bold red]API Image Processing Error:[/bold red] {str(e)}")
        raise

def main():
    """Start the bot"""
    console.print(Panel.fit("🤖 Starting Telegram Bot...", style="bold blue"))
    
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Commands
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        
        # Messages
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_image_message))
        
        console.print(Panel.fit("✅ Bot is now running. Press Ctrl+C to stop.", style="bold green"))
        console.print("🔄 Polling for updates...", style="italic")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        console.print(Panel.fit(f"🔥 Critical Error: {str(e)}", style="bold red"))
    finally:
        console.print("🛑 Bot has stopped.", style="bold red")

if __name__ == "__main__":
    main()