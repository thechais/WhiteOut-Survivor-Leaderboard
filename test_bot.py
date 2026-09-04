import os
import sys
import discord

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"\nSUCCESS! Connected to Discord as: {bot.user} (ID: {bot.user.id})\n")
    await bot.close()

token = os.environ.get("DISCORD_TOKEN")
if not token:
    print("❌ ERROR: DISCORD_TOKEN variable is missing!")
    sys.exit(1)

print("Attempting connection to Discord...")
bot.run(token)
