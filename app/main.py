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
import httpx as requests

from telegram import ForceReply, Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, Updater, CallbackContext, MessageHandler
import os

WHISPERAPI_URL = os.environ['WHISPERAPI_URL']
BOT_TOKEN = os.environ['BOT_TOKEN']

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
from datetime import datetime, timezone

def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)

def call_whisper_api(chatID: str, filename: str) -> dict:
    """Call the whisper API with the given endpoint and data."""    
    # send the voice note to the whisper API
    path = f"{WHISPERAPI_URL}/queue/{chatID}"
    files = {'audio_file':  open(f"data/{filename}", 'rb')}
    res = requests.post(path, files=files)
    return res

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

async def audio_message_handler(update: Update, context: CallbackContext) -> None:
    """Send the user a message that the bot received the audio message. And that it has been added to the queue."""
    # get chat ID from the message
    chatID = update.effective_chat.id

    try:
        first_name = update.message.api_kwargs["forward_from"]["first_name"]
    except Exception as e:
        first_name = update.message.chat.first_name
    date = utc_to_local(update.message.date).strftime("%H-%M")
    duration = update.message.audio.duration
    new_file = await context.bot.get_file(update.message.audio.file_id)
    filename = f"{first_name}-{duration}_{date}.mp3"

    # download the audio note as a file
    await new_file.download_to_drive(f"data/{filename}")

    # handle the response from the whisper API
    response = call_whisper_api(chatID, filename)
    if response.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Your audio note has been added to the queue.",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error adding your audio note to the queue. Please try again later.",
        )
    
    # remove the audio note file
    os.remove(f"data/{filename}")

async def codee_llm_handler(update: Update, context: CallbackContext) -> None:
    """Echo the user message."""
    chatID = update.effective_chat.id
    message = update.message.text
    complete_text = ""
    with requests.stream('GET', f"{WHISPERAPI_URL}/predict_llm/{chatID}", json={"message": message}, timeout=30) as r:
        sentence_chunk = ""
        code = r.status_code
        if code == 200:
            i = 0
            for chunk in r.iter_raw():
                decoded = chunk.decode()
                if any(x in decoded for x in ["<|eot_id|>", "<|im_end|>", "<|eot|>", "</s>"]):
                    decoded = decoded.replace("<|eot_id|>", "")
                    decoded = decoded.replace("<|im_end|>", "")
                    decoded = decoded.replace("<|eot|>", "")
                    decoded = decoded.replace("</s>", "")
                sentence_chunk += decoded
                # if the sentence_chunk has a period, exclamation mark, question mark, semi-colon or colon, then it is a complete sentence
                if any(x in sentence_chunk for x in [".", "!", "?", ";", ":"]):
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
            complete_text += sentence_chunk
            if i > 0 and aux_last_message != complete_text:
                # send the final response message
                await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=response_msg.message_id, text=complete_text)
            requests.post(f"{WHISPERAPI_URL}/predicted_text/{chatID}", json={"message": complete_text})
        elif code == 401:
            for chunk in r.iter_raw():
                decoded = chunk.decode()
                complete_text += decoded
            complete_text = json.loads(complete_text)["detail"]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=complete_text,
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="There was an error getting the response from the model. Please try again later.",
            )

async def voice_message_handler(update: Update, context: CallbackContext) -> None:
    """Send the user a message that the bot received the voice message. And that it has been added to the queue."""
    # get chat ID from the message
    chatID = update.effective_chat.id
    try:
        first_name = update.message.api_kwargs["forward_from"]["first_name"]
    except Exception as e:
        first_name = update.message.chat.first_name
    date = utc_to_local(update.message.date).strftime("%H-%M")
    duration = update.message.voice.duration
    new_file = await context.bot.get_file(update.message.voice.file_id)
    filename = f"{first_name}-{duration}_{date}.ogg"

    # download the audio note as a file
    await new_file.download_to_drive(f"data/{filename}")

    # handle the response from the whisper API
    response = call_whisper_api(chatID, filename)

    if response.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Your audio note has been added to the queue.",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error adding your audio note to the queue. Please try again later.",
        )
    
    # remove the audio note file
    os.remove(f"data/{filename}")   

async def video_note_message_handler(update: Update, context: CallbackContext) -> None:
    """Send the user a message that the bot received the video message. And that it has been added to the queue."""
    # get chat ID from the message
    chatID = update.effective_chat.id

    try:
        first_name = update.message.api_kwargs["forward_from"]["first_name"]
    except Exception as e:
        first_name = update.message.chat.first_name
    date = utc_to_local(update.message.date).strftime("%H-%M")
    duration = update.message.video_note.duration
    
    # create filename for the video note with a timestamp
    filename = f"{first_name}-{duration}_{date}"

    # get basic info about the video note file and prepare it for downloading
    new_file = await context.bot.get_file(update.message.video_note.file_id)
    # download the video note as a file
    await new_file.download_to_drive(f"data/{filename}.mp4")

    # convert it to an audio file
    os.system(f"ffmpeg -v quiet -i {filename}.mp4 -q:a 0 -map a {filename}.mp3")
    # remove the video note file
    os.remove(f"data/{filename}.mp4")
    # handle the response from the whisper API
    response = call_whisper_api(chatID, f"{filename}.mp3")
    if response.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Your video note has been added to the queue.",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error adding your video note to the queue. Please try again later.",
        )

    # remove the audio note file
    os.remove(f"data/{filename}.mp3")

async def get_speech2text_queue(update: Update, context: CallbackContext) -> None:
    """Get the current speech2text queue."""
    res = requests.get(f"{WHISPERAPI_URL}/queue/{update.effective_chat.id}")
    if res.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=json.loads(res.text),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error getting the speech2text queue. Please try again later.",
        )

async def start_speech2text(update: Update, context: CallbackContext) -> None:
    """Start the speech2text process."""
    chatID = update.effective_chat.id
    await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Starting the speech2text process. Wait a moment...",
        )
    res = requests.get(f"{WHISPERAPI_URL}/predict_whisper/{chatID}?remove=True")
    print(res)
    if res.status_code == 200:
        for key, value in json.loads(res.text).items():
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode=constants.ParseMode.HTML,
                text=f"<b>{key}</b>:\n{value.strip()}",
            )
    else:
        print(res.text)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error starting the speech2text process. Please try again later.",
        )
    
async def clear_speech2text(update: Update, context: CallbackContext) -> None:
    """Clear the speech2text queue."""
    res = requests.get(f"{WHISPERAPI_URL}/clear_queue/{update.effective_chat.id}")
    if res.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="The speech2text queue has been cleared.",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error clearing the speech2text queue. Please try again later.",
        )

async def info_speech2text(update: Update, context: CallbackContext) -> None:
    """Get information about the speech2text process."""
    res = requests.get(f"{WHISPERAPI_URL}/info")
    if res.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=json.loads(res.text),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error getting the speech2text information. Please try again later.",
        )

async def help_speech2text(update: Update, context: CallbackContext) -> None:
    """Get help information about the speech2text process."""
    res = requests.get(f"{WHISPERAPI_URL}/help")
    if res.status_code == 200:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=json.loads(res.text),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There was an error getting the speech2text information. Please try again later.",
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

    # Add voice message handler
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    application.add_handler(MessageHandler(filters.AUDIO, audio_message_handler))

    # add video message handler
    application.add_handler(MessageHandler(filters.VIDEO_NOTE, video_note_message_handler))

    # add speech2text handlers
    application.add_handler(CommandHandler("speech2text_queue", get_speech2text_queue))
    application.add_handler(CommandHandler("speech2text_start", start_speech2text))
    application.add_handler(CommandHandler("speech2text_clear", clear_speech2text))
    application.add_handler(CommandHandler("speech2text_info", info_speech2text))
    application.add_handler(CommandHandler("speech2text_help", help_speech2text))
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()