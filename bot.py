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

# ==========================================
# CONFIGURATION
# ==========================================
# Replace this with your actual #small-events-monitoring channel ID
TARGET_CHANNEL_ID = 1535518390276460575 
SHEET_NAME = "WOS_State_3817_Leaderboards"

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
sheet = client.open(SHEET_NAME).sheet1

# Ensure headers exist in the Google Sheet
headers = ["Event_Name", "Rank", "Player_Name", "Score", "Submission_Date"]
if not sheet.get_all_values():
    sheet.append_row(headers)

# ==========================================
# BOT EVENTS
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user.name}")
    print(f"Listening to channel ID: {TARGET_CHANNEL_ID}")

@bot.event
async def on_message(message):
    # 1. Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # 2. Ignore messages sent outside the specific monitoring channel
    if message.channel.id != TARGET_CHANNEL_ID:
        return

    # 3. Check if the message contains a valid image attachment
    has_image = message.attachments and any(
        att.filename.lower().endswith(('.png', '.jpg', '.jpeg'))
        for att in message.attachments
    )

    # 4. Delete message if it lacks a valid screenshot
    if not has_image:
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, `#small-events-monitoring` is only for leaderboard screenshots. Please attach a screenshot with the event name.",
            delete_after=5
        )
        return

    # 5. Delete message if screenshot is sent without an event name in the text
    if not message.content.strip():
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, please include the **Event Name** in your message text when uploading a screenshot.",
            delete_after=5
        )
        return

    # ==========================================
    # PROCESS VALID SCREENSHOT
    # ==========================================
    event_name = message.content.strip().upper()
    attachment = message.attachments[0]

    await message.add_reaction("⏳")
    
    # Read image into memory
    image_bytes = await attachment.read()
    
    # Extract text using EasyOCR
    ocr_results = reader.readtext(image_bytes, detail=0)
    
    rows_to_insert = []
    submission_date = str(message.created_at.date())

    # Parse detected text lines into Rank, Name, Score
    for i in range(len(ocr_results) - 2):
        text = ocr_results[i]
        # Look for numbers 1 through 20 (with or without #)
        if re.match(r"^#?([1-9]|1[0-9]|20)$", text):
            rank = re.sub(r"\D", "", text) # Strip out the # if it exists
            player_name = ocr_results[i+1]
            score = ocr_results[i+2]
            rows_to_insert.append([event_name, rank, player_name, score, submission_date])

    if rows_to_insert:
        existing_records = sheet.get_all_records()
        
        # Deduplication logic
        for row in rows_to_insert:
            duplicate_row_num = None
            for idx, record in enumerate(existing_records, start=2): # Header is row 1
                if (str(record['Event_Name']) == row[0] and 
                    str(record['Rank']) == row[1] and 
                    str(record['Submission_Date']) == row[4]):
                    duplicate_row_num = idx
                    break

            if duplicate_row_num:
                # Update existing row if duplicate found
                sheet.update(f"A{duplicate_row_num}:E{duplicate_row_num}", [row])
            else:
                # Append new row
                sheet.append_row(row)

        await message.clear_reactions()
        await message.add_reaction("✅")
        await message.reply(f"✅ Processed {len(rows_to_insert)} rank entries for **{event_name}**.")
    else:
        await message.clear_reactions()
        await message.add_reaction("❌")
        await message.reply("❌ Could not detect top 20 rankings clearly. Please upload an uncropped, clear screenshot.")

    await bot.process_commands(message)

# Run the bot using the token from environment variables
bot.run(os.environ.get("DISCORD_TOKEN"))
