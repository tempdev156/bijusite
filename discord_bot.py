
import asyncio
import threading
import os

import discord
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_LOG_CHANNEL_ID = os.getenv("DISCORD_LOG_CHANNEL_ID")


if not DISCORD_BOT_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is missing from .env")

if not DISCORD_LOG_CHANNEL_ID:
    raise RuntimeError("DISCORD_LOG_CHANNEL_ID is missing from .env")

try:
    DISCORD_LOG_CHANNEL_ID = int(DISCORD_LOG_CHANNEL_ID)
except ValueError:
    raise RuntimeError("DISCORD_LOG_CHANNEL_ID must be a number")


# ============================================================
# DISCORD BOT
# ============================================================

intents = discord.Intents.none()

bot = discord.Client(intents=intents)

bot_loop = None
bot_ready = threading.Event()


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():
    global bot_loop

    bot_loop = asyncio.get_running_loop()
    bot_ready.set()

    print()
    print("========================================")
    print("[DISCORD] Bot connected successfully")
    print(f"[DISCORD] Logged in as: {bot.user}")
    print(f"[DISCORD] Logging channel: {DISCORD_LOG_CHANNEL_ID}")
    print("========================================")
    print()


# ============================================================
# SEND MESSAGE TO DISCORD
# ============================================================

async def _send_message(
    username,
    private_id,
    conversation_id,
    text,
    message_type="text",
    media_url=None
):

    try:

        # ----------------------------------------------------
        # FIND CHANNEL
        # ----------------------------------------------------

        channel = bot.get_channel(DISCORD_LOG_CHANNEL_ID)

        if channel is None:
            channel = await bot.fetch_channel(
                DISCORD_LOG_CHANNEL_ID
            )

        if channel is None:
            print("[DISCORD] Channel not found")
            return


        # ----------------------------------------------------
        # TEXT MESSAGE
        # ----------------------------------------------------

        if message_type == "text":

            embed = discord.Embed(
                title="💬 New PrivateChat Message",
                description=text if text else "*(empty message)*",
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow()
            )

            embed.set_author(
                name=f"{username} • {private_id}"
            )

            embed.add_field(
                name="🆔 Conversation",
                value=f"`{conversation_id}`",
                inline=True
            )

            embed.add_field(
                name="👤 Sender",
                value=f"`{username}`",
                inline=True
            )

            embed.add_field(
                name="🔐 Private ID",
                value=f"`{private_id}`",
                inline=True
            )

            embed.set_footer(
                text="PrivateChat • Message Backup"
            )

            await channel.send(embed=embed)


        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        elif message_type == "image":

            embed = discord.Embed(
                title="🖼️ New Image",
                description=text if text else "*(No caption)*",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )

            embed.set_author(
                name=f"{username} • {private_id}"
            )

            embed.add_field(
                name="🆔 Conversation",
                value=f"`{conversation_id}`",
                inline=True
            )

            embed.add_field(
                name="👤 Sender",
                value=f"`{username}`",
                inline=True
            )

            if media_url:
                embed.set_image(url=media_url)

                embed.add_field(
                    name="🔗 Media",
                    value=f"[Open image]({media_url})",
                    inline=False
                )

            embed.set_footer(
                text="PrivateChat • Image Backup"
            )

            await channel.send(embed=embed)


        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        elif message_type == "video":

            embed = discord.Embed(
                title="🎥 New Video",
                description=text if text else "*(No caption)*",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )

            embed.set_author(
                name=f"{username} • {private_id}"
            )

            embed.add_field(
                name="🆔 Conversation",
                value=f"`{conversation_id}`",
                inline=True
            )

            embed.add_field(
                name="👤 Sender",
                value=f"`{username}`",
                inline=True
            )

            if media_url:

                embed.add_field(
                    name="🔗 Video",
                    value=f"[Open video]({media_url})",
                    inline=False
                )

            embed.set_footer(
                text="PrivateChat • Video Backup"
            )

            await channel.send(embed=embed)


        # ----------------------------------------------------
        # OTHER FILE
        # ----------------------------------------------------

        else:

            embed = discord.Embed(
                title="📎 New File",
                description=text if text else "*(No description)*",
                color=discord.Color.greyple(),
                timestamp=discord.utils.utcnow()
            )

            embed.set_author(
                name=f"{username} • {private_id}"
            )

            embed.add_field(
                name="🆔 Conversation",
                value=f"`{conversation_id}`",
                inline=True
            )

            embed.add_field(
                name="👤 Sender",
                value=f"`{username}`",
                inline=True
            )

            embed.add_field(
                name="📁 Type",
                value=f"`{message_type}`",
                inline=True
            )

            if media_url:

                embed.add_field(
                    name="🔗 File",
                    value=f"[Open file]({media_url})",
                    inline=False
                )

            embed.set_footer(
                text="PrivateChat • File Backup"
            )

            await channel.send(embed=embed)


        print(
            f"[DISCORD] Message logged "
            f"from {username} "
            f"(conversation {conversation_id})"
        )


    except Exception as e:

        print("[DISCORD] Failed to send message:")
        print(e)


# ============================================================
# PUBLIC FUNCTION USED BY FLASK
# ============================================================

def send_to_discord(
    username,
    private_id,
    conversation_id,
    text,
    message_type="text",
    media_url=None
):

    if not bot_ready.is_set():

        print(
            "[DISCORD] Bot isn't ready yet. "
            "Message was not logged."
        )

        return


    if bot_loop is None:

        print(
            "[DISCORD] Bot event loop isn't available."
        )

        return


    future = asyncio.run_coroutine_threadsafe(
        _send_message(
            username=username,
            private_id=private_id,
            conversation_id=conversation_id,
            text=text,
            message_type=message_type,
            media_url=media_url
        ),
        bot_loop
    )


    def check_result(f):

        try:
            f.result()

        except Exception as e:

            print("[DISCORD] Send error:")
            print(e)


    future.add_done_callback(check_result)


# ============================================================
# START BOT
# ============================================================

def start_discord_bot():

    def runner():

        try:

            asyncio.run(
                bot.start(DISCORD_BOT_TOKEN)
            )

        except Exception as e:

            print("[DISCORD] Bot stopped:")
            print(e)


    thread = threading.Thread(
        target=runner,
        daemon=True
    )

    thread.start()

    return thread
