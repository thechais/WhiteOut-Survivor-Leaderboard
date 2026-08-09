import os
import io
import re
import json
import discord
from discord.ext import commands
import easyocr
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image

# Initialize Discord Intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize EasyOCR (runs on CPU for free tier)
reader = easyocr.Reader(['en'], gpu=False)

# Connect to Google Sheets using environment variable
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_json = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(creds)
sheet = client.open("WOS_State_3817_Leaderboards").sheet1

# Ensure headers exist in Sheet
headers = ["Event_Name", "Rank", "Player_Name", "Score", "Submission_Date"]
if not sheet.get_all_values():
    sheet.append_row(headers)

@bot.event
async def on_message(message):
    # Ignore messages sent by the bot
    if message.author == bot.user:
        return

    # Ignore messages sent outside the monitoring channel
    if message.channel.id != TARGET_CHANNEL_ID:
        return

    # Check if the message contains an image attachment
    has_image = message.attachments and any(
        att.filename.lower().endswith(('.png', '.jpg', '.jpeg'))
        for att in message.attachments
    )

    # 1. Delete message if it lacks a valid screenshot
    if not has_image:
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, `#small-events-monitoring` is only for leaderboard screenshots. Please attach a screenshot with the event name.",
            delete_after=5  # Automatically deletes the warning after 5 seconds
        )
        return

    # 2. Delete message if screenshot is sent without an event name in the text
    if not message.content.strip():
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, please include the **Event Name** in your message text when uploading a screenshot.",
            delete_after=5
        )
        return

    # Proceed with OCR and Google Sheets processing for valid submissions...
    event_name = message.content.strip().upper()
    attachment = message.attachments[0]
    
    # [Rest of your OCR & Google Sheets processing logic here]
    await bot.process_commands(message)


bot.run(os.environ.get("DISCORD_TOKEN"))
