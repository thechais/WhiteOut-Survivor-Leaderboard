import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# 1. IMMEDIATE RENDER PORT BIND (FIXES PORT SCANNER)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Discord bot is alive")

    def log_message(self, format, *args):
        return  # Silence HTTP server log noise

def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Background HTTP server bound to port {port}")
    server.serve_forever()

# Start HTTP server IMMEDIATELY so Render port check succeeds on boot
threading.Thread(target=start_web_server, daemon=True).start()

# ==========================================
# 2. IMPORTS & CONFIGURATION
# ==========================================
import io
import re
import json
import time
import urllib.request
from datetime import datetime, timezone
import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
from google.oauth2 import service_account

TARGET_CHANNEL_ID = 1535518390276460575  # <--- REPLACE WITH YOUR DISCORD CHANNEL ID
SHEET_NAME = "WOS_State_3817_Leaderboards"
STREAMLIT_URL = "https://your-streamlit-app-url.streamlit.app"  # <--- REPLACE WITH YOUR STREAMLIT DASHBOARD URL

# Keep Streamlit app awake in the background
def keep_streamlit_alive():
    while True:
        try:
            time.sleep(600)
            if "your-streamlit-app-url" not in STREAMLIT_URL:
                req = urllib.request.Request(STREAMLIT_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    print(f"⏰ Keep-alive ping sent to Streamlit (Status: {response.status})")
        except Exception as e:
            print(f"⚠️ Streamlit keep-alive ping failed: {e}")

threading.Thread(target=keep_streamlit_alive, daemon=True).start()

# ==========================================
# 3. NON-BLOCKING API AUTHENTICATION
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

creds_raw = os.environ.get("GCP_SERVICE_ACCOUNT")
if not creds_raw:
    print("❌ FATAL: GCP_SERVICE_ACCOUNT environment variable is missing!")
    sys.exit(1)

try:
    creds_json = json.loads(creds_raw)
except Exception as e:
    print(f"❌ FATAL: GCP_SERVICE_ACCOUNT is not valid JSON: {e}")
    sys.exit(1)

try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    sheet_creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    client = gspread.authorize(sheet_creds)
    sheet = client.open(SHEET_NAME).sheet1
    
    headers = ["Event_Name", "Rank", "Player_Name", "Score", "Submission_Date"]
    if not sheet.get_all_values():
        sheet.append_row(headers)
    print("✅ Google Sheets connected successfully!")
except Exception as e:
    print(f"⚠️ Warning: Google Sheets connection failed: {e}")

try:
    vision_creds = service_account.Credentials.from_service_account_info(creds_json)
    vision_client = vision.ImageAnnotatorClient(credentials=vision_creds)
    print("✅ Cloud Vision API ready!")
except Exception as e:
    print(f"⚠️ Warning: Cloud Vision failed: {e}")

@bot.event
async def on_ready():
    print(f"🎉 SUCCESS: Bot is connected and online as {bot.user.name}")

# ==========================================
# 4. DISCORD EVENT LISTENER & OCR ENGINE
# ==========================================
@bot.event
async def on_message(message):
    if message.author == bot.user or message.channel.id != TARGET_CHANNEL_ID:
        return

    now_utc = message.created_at.astimezone(timezone.utc)
    is_admin = message.author.guild_permissions.administrator

    # 3-Hour Submission Window Check (00:00 to 02:59 UTC)
    if not is_admin and not (0 <= now_utc.hour < 3):
        await message.delete()
        await message.channel.send(
            f"⛔ {message.author.mention}, screenshot submissions are closed!\n"
            f"Submissions are only allowed within **3 hours after event reset (00:00 UTC to 03:00 UTC)**.",
            delete_after=10
        )
        return

    image_attachments = [
        att for att in message.attachments
        if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))
    ]

    if not image_attachments or not message.content.strip():
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, please upload leaderboard screenshots along with the **Event Name** in text.",
            delete_after=5
        )
        return

    event_name = message.content.strip().upper()
    submission_date = str(now_utc.date())
    
    await message.add_reaction("⏳")
    all_extracted_ranks = {}

    for attachment in image_attachments:
        try:
            image_bytes = await attachment.read()
            image = vision.Image(content=image_bytes)
            response = vision_client.text_detection(image=image)
            texts = response.text_annotations

            if not texts:
                continue

            raw_text = texts[0].description
            ocr_lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

            for i in range(len(ocr_lines) - 2):
                text = ocr_lines[i]
                if re.match(r"^#?([1-9]|1[0-9]|20)$", text):
                    rank = int(re.sub(r"\D", "", text))
                    player_name = ocr_lines[i+1]
                    score = ocr_lines[i+2]
                    all_extracted_ranks[rank] = [event_name, rank, player_name, score, submission_date]
        except Exception as e:
            print(f"⚠️ Error processing attachment: {e}")

    if all_extracted_ranks:
        sorted_ranks = sorted(all_extracted_ranks.keys())
        rows_to_insert = [all_extracted_ranks[r] for r in sorted_ranks]

        all_rows = sheet.get_all_values()
        cleaned_rows = []

        # Overwrite entries matching today's event, keep historical
        for idx, row in enumerate(all_rows):
            if idx == 0:
                cleaned_rows.append(row)
                continue
            
            row_event = row[0].strip().upper() if len(row) > 0 else ""
            row_date = row[4].strip() if len(row) > 4 else ""
            
            if row_event == event_name and row_date == submission_date:
                continue
            
            cleaned_rows.append(row)

        cleaned_rows.extend(rows_to_insert)
        sheet.clear()
        sheet.update("A1", cleaned_rows)

        await message.clear_reactions()
        await message.add_reaction("✅")
        await message.reply(
            f"✅ Processed **{len(image_attachments)} screenshot(s)**.\n"
            f"Updated **{event_name}** ({submission_date}) with **{len(rows_to_insert)} rank entries**."
        )
    else:
        await message.clear_reactions()
        await message.add_reaction("❌")
        await message.reply("❌ Unable to parse Top 20 ranks from screenshots.", delete_after=10)

    await bot.process_commands(message)

# ==========================================
# 5. RUNNER WITH DISCORD 429 BACKOFF
# ==========================================
token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("❌ FATAL: DISCORD_TOKEN environment variable is missing!")
    sys.exit(1)

retry_delay = 60

while True:
    try:
        print("🚀 Starting Discord Bot...")
        bot.run(token)
    except discord.errors.HTTPException as e:
        if e.status == 429:
            print(f"⚠️ Discord 429 Rate Limit! Backing off for {retry_delay} seconds...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 600)  # Max 10 minutes
        else:
            print(f"❌ Discord HTTP Exception: {e}")
            time.sleep(15)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        time.sleep(15)
