import os
import io
import re
import json
import time
import sys
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
from google.oauth2 import service_account

# ==========================================
# 1. DUMMY HTTP SERVER FOR RENDER KEEP-ALIVE
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Discord bot is alive")

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Background HTTP server listening on port {port}")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. BOT CONFIGURATION & CREDENTIALS
# ==========================================
TARGET_CHANNEL_ID = 123456789012345678  # <--- REPLACE WITH YOUR DISCORD CHANNEL ID
SHEET_NAME = "WOS_State_3817_Leaderboards"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Load GCP JSON Credentials from Render Environment Variable
creds_raw = os.environ.get("GCP_SERVICE_ACCOUNT")
if not creds_raw:
    print("❌ FATAL: GCP_SERVICE_ACCOUNT environment variable is missing!")
    sys.exit(1)

creds_json = json.loads(creds_raw)

# Google Sheets Auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
sheet_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(sheet_creds)
sheet = client.open(SHEET_NAME).sheet1

# Cloud Vision Auth
vision_creds = service_account.Credentials.from_service_account_info(creds_json)
vision_client = vision.ImageAnnotatorClient(credentials=vision_creds)

# Ensure sheet headers exist
headers = ["Event_Name", "Rank", "Player_Name", "Score", "Submission_Date"]
if not sheet.get_all_values():
    sheet.append_row(headers)

@bot.event
async def on_ready():
    print(f"✅ Bot logged in successfully as {bot.user.name}")

# ==========================================
# 3. MESSAGE LISTENER & OCR PROCESSING
# ==========================================
@bot.event
async def on_message(message):
    # Ignore bot's own messages or messages outside target channel
    if message.author == bot.user or message.channel.id != TARGET_CHANNEL_ID:
        return

    # ------------------------------------------
    # TIME WINDOW CHECK (00:00 - 03:00 UTC)
    # ------------------------------------------
    now_utc = message.created_at.astimezone(timezone.utc)
    is_admin = message.author.guild_permissions.administrator

    # If non-admin posts outside 00:00 - 02:59 UTC, delete and warn
    if not is_admin and not (0 <= now_utc.hour < 3):
        await message.delete()
        await message.channel.send(
            f"⛔ {message.author.mention}, screenshot submissions are closed!\n"
            f"Submissions are only allowed within **3 hours after event reset (00:00 UTC to 03:00 UTC)**.",
            delete_after=10
        )
        return

    # ------------------------------------------
    # ATTACHMENT & TEXT VALIDATION
    # ------------------------------------------
    image_attachments = [
        att for att in message.attachments
        if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
    ]

    if not image_attachments:
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, `#small-events-monitoring` is strictly for leaderboard screenshots.",
            delete_after=5
        )
        return

    if not message.content.strip():
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, please type the **Event Name** in your message text when uploading screenshots.",
            delete_after=5
        )
        return

    event_name = message.content.strip().upper()
    submission_date = str(now_utc.date())
    
    await message.add_reaction("⏳")

    all_extracted_ranks = {}

    # ------------------------------------------
    # OCR PARSING FOR MULTIPLE IMAGES
    # ------------------------------------------
    for attachment in image_attachments:
        image_bytes = await attachment.read()
        image = vision.Image(content=image_bytes)
        response = vision_client.text_detection(image=image)
        texts = response.text_annotations

        if not texts:
            continue

        raw_text = texts[0].description
        ocr_lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

        # Parse OCR text lines for Rank, Player Name, and Score
        for i in range(len(ocr_lines) - 2):
            text = ocr_lines[i]
            # Match Rank digits 1 to 20 (e.g., "1", "#1", "20")
            if re.match(r"^#?([1-9]|1[0-9]|20)$", text):
                rank = int(re.sub(r"\D", "", text))
                player_name = ocr_lines[i+1]
                score = ocr_lines[i+2]
                
                # Dictionary prevents duplicate ranks across multiple screenshots
                all_extracted_ranks[rank] = [event_name, rank, player_name, score, submission_date]

    # ------------------------------------------
    # BATCH WRITE TO GOOGLE SHEETS (CLEAR TODAY'S RUN ONLY)
    # ------------------------------------------
    if all_extracted_ranks:
        sorted_ranks = sorted(all_extracted_ranks.keys())
        rows_to_insert = [all_extracted_ranks[r] for r in sorted_ranks]

        # Get all existing rows
        all_rows = sheet.get_all_values()
        cleaned_rows = []

        # Retain header row and historical records from other dates or events
        for idx, row in enumerate(all_rows):
            if idx == 0:
                cleaned_rows.append(row)
                continue
            
            row_event = row[0].strip().upper() if len(row) > 0 else ""
            row_date = row[4].strip() if len(row) > 4 else ""
            
            # Remove ONLY records matching this exact event and today's date
            if row_event == event_name and row_date == submission_date:
                continue
            
            cleaned_rows.append(row)

        # Append latest extracted rows
        cleaned_rows.extend(rows_to_insert)

        # Overwrite sheet with updated dataset
        sheet.clear()
        sheet.update("A1", cleaned_rows)

        await message.clear_reactions()
        await message.add_reaction("✅")
        await message.reply(
            f"✅ Processed **{len(image_attachments)} screenshot(s)**. "
            f"Updated **{event_name}** ({submission_date}) with **{len(rows_to_insert)} rank entries** (Ranks {min(sorted_ranks)}–{max(sorted_ranks)})."
        )
    else:
        await message.clear_reactions()
        await message.add_reaction("❌")
        await message.reply("❌ Unable to parse Top 20 ranks from screenshots. Ensure images are clear and uncropped.", delete_after=10)

    await bot.process_commands(message)

# ==========================================
# 4. BOT RUNNER WITH RATE-LIMIT SAFEGUARD
# ==========================================
token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("❌ FATAL: DISCORD_TOKEN environment variable is missing!")
    sys.exit(1)

while True:
    try:
        print("🚀 Starting Discord Bot...")
        bot.run(token)
    except discord.errors.HTTPException as e:
        if e.status == 429:
            print("⚠️ Rate limited by Discord API! Waiting 60 seconds before retrying...")
            time.sleep(60)
        else:
            print(f"❌ Discord HTTP Exception: {e}")
            time.sleep(10)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        time.sleep(10)
