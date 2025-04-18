#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""
from pprint import pprint
from datetime import datetime
import json
import logging
import os
import time
import httpx as requests

from telegram import ForceReply, Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, Updater, CallbackContext, MessageHandler
import os
from utils import get_prompt, update_chat_history, calculate_similarity

LLM_URL = os.environ['LLM_URL']
ENCODER_URL = os.environ['ENCODER_URL']
BOT_TOKEN = os.environ['BOT_TOKEN']

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
from datetime import datetime, timezone


def call_embedder_api(prompt, messages):
    return [0.2, 0.3, 0.4]  # Placeholder for actual embedding call

def call_llm_api(system_prompt, messages):
    url = "http://192.168.178.200:8000/v1/chat/completions"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            { "role": "system", "content": system_prompt },
        ],
        "cache_prompt": True,
        "temperature": 0.4,
        "top_k": 1,
        "stream": True,
        "repeat_penalty": 2,
    }
    for message in messages:
        payload["messages"].append({
            "role": message["role"],
            "content": message["content"]
        })

    return requests.post(url, headers=headers, json=payload, stream=True) 

def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)

async def start_handler(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Hi! I'm a bot that converts your voice messages to text. Send me an audio message and I'll add it to the queue.",
    )

async def help_handler(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Send me an audio message and I'll add it to the queue. Use /speech2text_queue to get the current queue, /speech2text_start to start the speech2text process, /speech2text_clear to clear the queue, /speech2text_info to get information about the process, and /speech2text_help to get help information.",
    )

async def codee_llm_handler(update: Update, context: CallbackContext) -> None:
    """Echo the user message."""
    chatID = update.effective_chat.id
    message = update.message.text
    complete_text = ""

    prompt, messages = get_prompt(chatID, message, message)

    interaction = []
    interaction_timsetamp = time.time() 
    
    embedding = call_embedder_api(messages)

    interaction.append({
            "chat_id": chatID,
            "role": "user",
            "content": embedding,
            "timestamp": interaction_timsetamp,
            "embedding": embedding,
            "metadata": None,
        })

    messages = [{"role": "user", "content": embedding}]
    
    llm_response = call_llm_api(prompt, messages)
    code = llm_response.status_code
    if code == 200:
        i = 0
        aux_last_message = ""
        sentence_chunk = ""
        for response_orig in llm_response.iter_lines():
            response = response_orig.decode("utf-8").replace("data: ", "")
            if response == "[DONE]":
                break
            if response == "":
                continue
            response = json.loads(response)
            if "choices" in response:
                for choice in response["choices"]:
                    if "delta" in choice and "content" in choice["delta"]:
                        sentence_chunk += choice["delta"]["content"]
                        # if the sentence_chunk has a period, exclamation mark, question mark, semi-colon or colon, then it is a complete sentence
                        if any(x in sentence_chunk for x in [".", "\n"]):
                            complete_text += sentence_chunk
                            sentence_chunk = ""
                            if len(complete_text) > 0:
                                if  i == 0:
                                    # if is the first chunk start the response message 
                                    response_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=complete_text)
                                    aux_last_message = complete_text
                                else:
                                    # if is not the first chunk edit the response message
                                    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=response_msg.message_id, text=complete_text)
                                    aux_last_message = complete_text
                                i += 1
                    if "finish_reason" in choice and choice["finish_reason"] == "stop":
                        break
        complete_text += sentence_chunk
        if i > 0 and aux_last_message != complete_text:
            # send the final response message
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=response_msg.message_id, text=complete_text)
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error getting the response from the model. Please try again later.",
        )

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # add bot text message handlers
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & (~filters.VOICE) & (~filters.AUDIO) & (~filters.VIDEO_NOTE), codee_llm_handler))

    # add bot command handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()