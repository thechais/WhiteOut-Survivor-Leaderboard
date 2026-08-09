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
async def on_ready():
    print(f"Bot logged in as {bot.user.name}")

# Set your target channel name (or target channel ID for higher security)
TARGET_CHANNEL_NAME = "small-events-monitoring"

@bot.event
async def on_message(message):
    # Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # Ignore messages sent outside of #small-events-monitoring
    if message.channel.name != TARGET_CHANNEL_NAME:
        return

    # Check for image attachment AND text content (Event Name)
    if message.attachments and message.content:
        event_name = message.content.strip().upper()
        attachment = message.attachments[0]

        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
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
                if re.match(r"^#?([1-9]|1[0-9]|20)$", text):
                    rank = re.sub(r"\D", "", text)
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
                        sheet.update(f"A{duplicate_row_num}:E{duplicate_row_num}", [row])
                    else:
                        sheet.append_row(row)

                await message.clear_reactions()
                await message.add_reaction("✅")
                await message.reply(f"Processed {len(rows_to_insert)} rank entries for **{event_name}**.")
            else:
                await message.clear_reactions()
                await message.add_reaction("❌")
                await message.reply("Could not detect top 20 rankings clearly. Please upload a clear image.")

    await bot.process_commands(message)


bot.run(os.environ.get("DISCORD_TOKEN"))
