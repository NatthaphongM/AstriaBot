# -*- coding: utf-8 -*-
import os
import asyncio
import datetime
import logging
import random
from collections import defaultdict
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from groq import AsyncGroq
from colorama import Fore, Style, init

# Setup Terminal Colorama and Logging
init(autoreset=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
load_dotenv()

# Environment Variables
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))
AUTO_ROLE_ID = int(os.getenv("AUTO_ROLE_ID", "0"))

if not DISCORD_TOKEN or not GROQ_API_KEY:
    raise ValueError("Missing essential API tokens in .env file!")

groq_client = AsyncGroq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


# --- HELPER FUNCTIONS ---
def chunk_text(text: str, limit: int = 1900) -> list[str]:
    """Splits text into safely deliverable chunks under Discord's 2000 character limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_idx = text.rfind("\n", 0, limit)
        if split_idx == -1:
            split_idx = text.rfind(" ", 0, limit)
        if split_idx == -1:
            split_idx = limit
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    return chunks


# --- TICKET SYSTEM (PERSISTENT COMPONENTS) ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="astria_close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


class AIInteractiveTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Ticket 🎫", style=discord.ButtonStyle.primary, custom_id="astria_ticket_btn"
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        existing_channel = discord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower()}")
        if existing_channel:
            await interaction.response.send_message(
                f"⚠️ You already have an open ticket: {existing_channel.mention}", ephemeral=True
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name.lower()}", overwrites=overwrites
        )

        embed = discord.Embed(
            title=f"🎫 Support Ticket — {user.display_name}",
            description=(
                f"Welcome {user.mention}!\n\n"
                "**Staff has been notified.** While you wait, describe your issue below.\n"
                "*AstriaBot AI is listening—type your concern to receive instant automated help!*"
            ),
            color=discord.Color.purple(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        await ticket_channel.send(embed=embed, view=TicketControlView())
        await interaction.response.send_message(
            f"✅ Ticket opened: {ticket_channel.mention}", ephemeral=True
        )


# --- MAIN BOT CLASS ---
class AstriaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.conversation_history = defaultdict(list)
        self.user_cooldowns = {}
        self.warnings = defaultdict(list)  # Warning logs memory

    async def setup_hook(self):
        self.add_view(AIInteractiveTicketView())
        self.add_view(TicketControlView())

        await self.tree.sync()
        print(f"{Fore.GREEN}✔ Persistent Views Loaded & Slash Commands Synced Globally!{Style.RESET_ALL}")

    def is_cooldown(self, user_id: int, seconds: int = 4) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if user_id in self.user_cooldowns and now - self.user_cooldowns[user_id] < seconds:
            return True
        self.user_cooldowns[user_id] = now
        return False


bot = AstriaBot()

SYSTEM_PROMPT = """
You are AstriaBot, the AI core of Cosmic Hangout.
Server Culture:
- Vibe: Gaming, Anime, Music, Social Chat, and Fun.
- Persona: Friendly, witty, adaptive, sharp, and community-first.
- Rules: Respect members, zero tolerance for toxicity/SARA, keep it fun.
- Key Games: Roblox, Genshin Impact, Minecraft, Assetto Corsa, GTA V.
Keep responses formatted cleanly for Discord (bolding, concise lists, concise paragraphs).
"""


# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f"{Fore.CYAN}==========================================")
    print(f"   AstriaBot ULTRA Online: {bot.user.name}")
    print(f"   ID: {bot.user.id}")
    print(f"=========================================={Style.RESET_ALL}")
    await bot.change_presence(activity=discord.Game(name="Cosmic Hangout | /ask"))


@bot.event
async def on_member_join(member: discord.Member):
    if AUTO_ROLE_ID != 0:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                logging.error("Failed to add auto-role: Bot lacks Manage Roles permission.")
            except Exception as e:
                logging.error(f"Auto-role error: {e}")

    if WELCOME_CHANNEL_ID != 0:
        channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="✨ Welcome to Cosmic Hangout!",
                description=(
                    f"Hey {member.mention}, welcome to the community!\n\n"
                    "We're a hub for gaming, anime, music, and social vibes.\n"
                    "Grab your roles, introduce yourself, and jump into the chat!"
                ),
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Cosmic Hangout • Community Core")
            try:
                await channel.send(
                    content=f"Welcome {member.mention}! <a:welcome:1258121907128238132>",
                    embed=embed,
                )
            except discord.Forbidden:
                logging.error("Lacking permissions to send welcome message.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    is_mentioned = bot.user in message.mentions
    is_ticket_channel = message.channel.name.startswith("ticket-")

    if is_mentioned or is_ticket_channel:
        if bot.is_cooldown(message.author.id, 4):
            await message.reply("⏳ Please wait a few seconds before asking me again!", delete_after=5)
            return

        clean_prompt = message.content.replace(f"<@{bot.user.id}>", "").strip()
        if not clean_prompt:
            clean_prompt = "Hello AstriaBot!"

        async with message.channel.typing():
            try:
                channel_id = message.channel.id
                history = bot.conversation_history[channel_id][-6:]
                messages = (
                    [{"role": "system", "content": SYSTEM_PROMPT}]
                    + history
                    + [{"role": "user", "content": clean_prompt}]
                )

                chat_completion = await groq_client.chat.completions.create(
                    messages=messages,
                    model="openai/gpt-oss-120b",
                    max_tokens=750,
                )
                response = chat_completion.choices[0].message.content

                bot.conversation_history[channel_id].append({"role": "user", "content": clean_prompt})
                bot.conversation_history[channel_id].append({"role": "assistant", "content": response})

                for part in chunk_text(response):
                    await message.reply(part)

            except Exception as e:
                await message.reply("⚠️ AstriaBot experienced a connection error with the AI engine.")
                logging.error(f"Groq API Error: {e}")

    await bot.process_commands(message)


# ===========================================================================
# 10 NEW ADVANCED COMMANDS & FUNCTIONS
# ===========================================================================

# --- 1. SERVER INFO ---
@bot.tree.command(name="serverinfo", description="Display detailed server stats and information.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"📊 {guild.name} Stats", color=discord.Color.purple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Boost Level", value=f"Tier {guild.premium_tier}", inline=True)
    embed.add_field(name="Text Channels", value=str(len(guild.text_channels)), inline=True)
    embed.add_field(name="Voice Channels", value=str(len(guild.voice_channels)), inline=True)
    embed.add_field(name="Created On", value=guild.created_at.strftime("%B %d, %Y"), inline=True)
    await interaction.response.send_message(embed=embed)


# --- 2. USER INFO ---
@bot.tree.command(name="userinfo", description="Display profile information about a member.")
async def userinfo(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    roles = [role.mention for role in target.roles if role.name != "@everyone"]
    
    embed = discord.Embed(title=f"👤 {target.display_name}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="User ID", value=str(target.id), inline=True)
    embed.add_field(name="Joined Server", value=target.joined_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name="Account Created", value=target.created_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if roles else "None", inline=False)
    await interaction.response.send_message(embed=embed)


# --- 3. AVATAR FETCH ---
@bot.tree.command(name="avatar", description="Get high-res avatar of a member.")
async def avatar(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    embed = discord.Embed(title=f"🖼️ {target.display_name}'s Avatar", color=discord.Color.purple())
    embed.set_image(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# --- 4. POLL SYSTEM ---
@bot.tree.command(name="poll", description="Create an interactive server poll (up to 5 choices).")
async def poll(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: Optional[str] = None,
    option4: Optional[str] = None,
    option5: Optional[str] = None,
):
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    options = [opt for opt in [option1, option2, option3, option4, option5] if opt]

    description = []
    for idx, opt in enumerate(options):
        description.append(f"{emojis[idx]} {opt}")

    embed = discord.Embed(
        title=f"📊 {question}",
        description="\n\n".join(description),
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text=f"Poll started by {interaction.user.display_name}")

    await interaction.response.send_message("Poll deployed!", ephemeral=True)
    poll_msg = await interaction.channel.send(embed=embed)
    
    for idx in range(len(options)):
        await poll_msg.add_reaction(emojis[idx])


# --- 5. CHANNEL LOCKDOWN ---
@bot.tree.command(name="lockdown", description="Lock or unlock the current channel for @everyone.")
@app_commands.checks.has_permissions(manage_channels=True)
async def lockdown(interaction: discord.Interaction, lock: bool, reason: str = "No reason specified"):
    channel = interaction.channel
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    
    if lock:
        overwrite.send_messages = False
        action_text = "🔒 Channel Locked"
    else:
        overwrite.send_messages = True
        action_text = "🔓 Channel Unlocked"

    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    
    embed = discord.Embed(title=action_text, description=f"**Reason:** {reason}", color=discord.Color.red() if lock else discord.Color.green())
    await interaction.response.send_message(embed=embed)


# --- 6. MODERATION WARNING SYSTEM ---
@bot.tree.command(name="warn", description="Issue a official warning to a member.")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    bot.warnings[member.id].append({"reason": reason, "moderator": interaction.user.display_name})
    
    embed = discord.Embed(
        title="⚠️ Member Warned",
        description=f"{member.mention} has received a warning.",
        color=discord.Color.yellow()
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Total Warnings", value=str(len(bot.warnings[member.id])), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warnings", description="Check warnings issued to a member.")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    user_warns = bot.warnings.get(member.id, [])
    if not user_warns:
        await interaction.response.send_message(f"✅ {member.mention} has no warnings.", ephemeral=True)
        return

    embed = discord.Embed(title=f"📋 Warnings for {member.display_name}", color=discord.Color.orange())
    for idx, warn_entry in enumerate(user_warns, 1):
        embed.add_field(
            name=f"Warning #{idx}",
            value=f"**Reason:** {warn_entry['reason']}\n**Mod:** {warn_entry['moderator']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)


# --- 7. GAMING UTILITIES (DICE & COINFLIP) ---
@bot.tree.command(name="roll", description="Roll a random number (Default 1-100).")
async def roll(interaction: discord.Interaction, max_val: int = 100):
    result = random.randint(1, max_val)
    await interaction.response.send_message(f"🎲 {interaction.user.mention} rolled **{result}** (1-{max_val})!")

@bot.tree.command(name="coinflip", description="Flip a coin!")
async def coinflip(interaction: discord.Interaction):
    outcome = random.choice(["Heads 🪙", "Tails 🪙"])
    await interaction.response.send_message(f"🪙 {interaction.user.mention} flipped **{outcome}**!")


# --- 8. CLEAR AI CONVERSATION HISTORY ---
@bot.tree.command(name="clearmemory", description="Clear AstriaBot's AI memory for this channel.")
@app_commands.checks.has_permissions(manage_messages=True)
async def clearmemory(interaction: discord.Interaction):
    bot.conversation_history[interaction.channel.id].clear()
    await interaction.response.send_message("🧹 AstriaBot's AI memory for this channel has been wiped!", ephemeral=True)


# --- 9. PING & BOT STATUS ---
@bot.tree.command(name="ping", description="Check bot connection latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", description=f"WebSocket Latency: **{latency}ms**", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)


# --- 10. BASE AI SLASH & TICKET PANEL SETUP ---
@bot.tree.command(name="ask", description="Query AstriaBot's advanced Groq AI brain.")
async def ask(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.3-70b-versatile",
            max_tokens=850,
        )
        answer = chat_completion.choices[0].message.content

        if len(answer) < 1000:
            embed = discord.Embed(title="🧠 AstriaBot Intelligence", color=discord.Color.purple())
            embed.add_field(name="Prompt", value=prompt, inline=False)
            embed.add_field(name="Response", value=answer, inline=False)
            embed.set_footer(text="Cosmic Hangout AI • Powered by Groq")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"**Prompt:** {prompt}\n\n{answer[:1900]}")

    except Exception as e:
        await interaction.followup.send("⚠️ Failed to reach AI backend.", ephemeral=True)
        logging.error(f"Groq Slash Command Error: {e}")


@bot.tree.command(name="settickets", description="Deploy the AI Support Ticket Panel.")
@app_commands.checks.has_permissions(administrator=True)
async def settickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Cosmic Hangout Support Desk",
        description="Click below to open a ticket. AstriaBot AI and our Staff Team are ready to assist!",
        color=discord.Color.purple(),
    )
    await interaction.channel.send(embed=embed, view=AIInteractiveTicketView())
    await interaction.response.send_message("Ticket Panel Deployed!", ephemeral=True)


# --- GLOBAL ERROR HANDLER ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You do not have the required permissions to use this command.", ephemeral=True
        )
    else:
        logging.error(f"Unhandled Command Error: {error}")


# Launch Bot
bot.run(DISCORD_TOKEN)
