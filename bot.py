import os
import io
import re
import json
import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
from google.oauth2 import service_account
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# DUMMY HTTP SERVER FOR RENDER HEALTH CHECKS
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Discord bot is alive")

    # Mute console request logs to keep terminal output clean
    def log_message(self, format, *args):
        return

def run_web_server():
    # Render assigns an HTTP port dynamically via the PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Background HTTP server listening on 0.0.0.0:{port}")
    server.serve_forever()

# Launch the HTTP server in a daemon background thread
threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# YOUR DISCORD BOT LOGIC FOLLOWS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

# ==========================================
# CONFIGURATION
# ==========================================
TARGET_CHANNEL_ID = 1535518390276460575  # Replace with your actual Channel ID
SHEET_NAME = "WOS_State_3817_Leaderboards"

# Initialize Discord Intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Parse Google Credentials once from Environment Variable
creds_json = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT"))

# 1. Connect to Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
sheet_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(sheet_creds)
sheet = client.open(SHEET_NAME).sheet1

# 2. Connect to Google Vision API (Ultra-Lightweight OCR)
vision_creds = service_account.Credentials.from_service_account_info(creds_json)
vision_client = vision.ImageAnnotatorClient(credentials=vision_creds)

# Ensure headers exist in Sheet
headers = ["Event_Name", "Rank", "Player_Name", "Score", "Submission_Date"]
if not sheet.get_all_values():
    sheet.append_row(headers)

# ==========================================
# BOT EVENTS
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user or message.channel.id != TARGET_CHANNEL_ID:
        return

    has_image = message.attachments and any(
        att.filename.lower().endswith(('.png', '.jpg', '.jpeg'))
        for att in message.attachments
    )

    if not has_image:
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, `#small-events-monitoring` is only for leaderboard screenshots.",
            delete_after=5
        )
        return

    if not message.content.strip():
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, please include the **Event Name** in your message text when uploading.",
            delete_after=5
        )
        return

    event_name = message.content.strip().upper()
    attachment = message.attachments[0]

    await message.add_reaction("⏳")
    
    # Read image into memory
    image_bytes = await attachment.read()
    
    # Process with Google Cloud Vision API
    image = vision.Image(content=image_bytes)
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations

    if not texts:
        await message.clear_reactions()
        await message.add_reaction("❌")
        await message.reply("❌ Could not read any text from the screenshot.")
        return

    # Extract lines from OCR response
    raw_text = texts[0].description
    ocr_results = [line.strip() for line in raw_text.split('\n') if line.strip()]
    
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
        
        for row in rows_to_insert:
            duplicate_row_num = None
            for idx, record in enumerate(existing_records, start=2):
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
        await message.reply(f"✅ Processed {len(rows_to_insert)} rank entries for **{event_name}**.")
    else:
        await message.clear_reactions()
        await message.add_reaction("❌")
        await message.reply("❌ Could not detect top 20 rankings clearly. Please upload a clear screenshot.")

    await bot.process_commands(message)

bot.run(os.environ.get("DISCORD_TOKEN"))
