import os
import asyncio
import datetime
from collections import defaultdict
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from groq import AsyncGroq
from colorama import Fore, Style, init

init(autoreset=True)
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))
AUTO_ROLE_ID = int(os.getenv("AUTO_ROLE_ID", "0"))

groq_client = AsyncGroq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class AstriaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.conversation_history = defaultdict(list)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"{Fore.GREEN}? Slash commands synced globally!{Style.RESET_ALL}")

bot = AstriaBot()

SYSTEM_PROMPT = """
You are AstriaBot, the AI core of Cosmic Hangout ??.
Server Culture:
- Vibe: Gaming, Anime, Music, Social Chat, and Fun.
- Persona: Friendly, witty, adaptive, sharp, and community-first.
- Rules: Respect members, zero tolerance for toxicity/SARA, keep it fun.
- Key Games: Roblox, Genshin Impact, Minecraft, Assetto Corsa, GTA V.
Keep responses formatted cleanly for Discord (bolding, concise lists, concise paragraphs).
"""

# --- RATE LIMITING & HELPER ---
user_cooldowns = {}

def is_cooldown(user_id: int, seconds: int = 5) -> bool:
    now = datetime.datetime.now().timestamp()
    if user_id in user_cooldowns and now - user_cooldowns[user_id] < seconds:
        return True
    user_cooldowns[user_id] = now
    return False

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"{Fore.CYAN}==========================================")
    print(f"  AstriaBot ULTRA Online: {bot.user.name}")
    print(f"  ID: {bot.user.id}")
    print(f"=========================================={Style.RESET_ALL}")
    await bot.change_presence(activity=discord.Game(name="Cosmic Hangout ?? | /ask"))

@bot.event
async def on_member_join(member: discord.Member):
    if AUTO_ROLE_ID != 0:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"Auto-role error: {e}")

    if WELCOME_CHANNEL_ID != 0:
        channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="?? Welcome to Cosmic Hangout!",
                description=(
                    f"Hey {member.mention}, welcome to the community!\n\n"
                    "We're a hub for gaming, anime, music, and social vibes. "
                    "Grab your roles, introduce yourself, and jump into the chat!"
                ),
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Cosmic Hangout • Est. July 2024")
            await channel.send(content=f"Welcome {member.mention}! <a:welcome:1258121907128238132>", embed=embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Trigger AI on Mention
    if bot.user in message.mentions:
        if is_cooldown(message.author.id, 4):
            await message.reply("? Please wait a few seconds before asking me again!", delete_after=5)
            return

        clean_prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not clean_prompt:
            clean_prompt = "Hello AstriaBot!"

        async with message.channel.typing():
            try:
                # Append context for conversation memory
                channel_id = message.channel.id
                history = bot.conversation_history[channel_id][-6:] # keep last 6 messages
                messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": clean_prompt}]

                chat_completion = await groq_client.chat.completions.create(
                    messages=messages,
                    model="llama-3.3-70b-versatile",
                    max_tokens=600
                )
                response = chat_completion.choices[0].message.content
                
                # Save to memory
                bot.conversation_history[channel_id].append({"role": "user", "content": clean_prompt})
                bot.conversation_history[channel_id].append({"role": "assistant", "content": response})

                await message.reply(response)
            except Exception as e:
                await message.reply("?? AstriaBot experienced a brain glitch connection error.")
                print(f"Groq API Error: {e}")

    await bot.process_commands(message)

# --- AI SLASH COMMAND ---
@bot.tree.command(name="ask", description="Query AstriaBot's advanced Groq AI brain.")
async def ask(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            max_tokens=700
        )
        answer = chat_completion.choices[0].message.content
        embed = discord.Embed(title="?? AstriaBot Intelligence", color=discord.Color.purple())
        embed.add_field(name="Prompt", value=prompt, inline=False)
        embed.add_field(name="Response", value=answer, inline=False)
        embed.set_footer(text="Cosmic Hangout AI • Powered by Groq")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send("?? Failed to reach AI backend.", ephemeral=True)
        print(f"Groq API Error: {e}")

# --- MODERATION COMMANDS ---
@bot.tree.command(name="ban", description="Ban a member.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"? Banned {member.mention} | Reason: {reason}")

@bot.tree.command(name="kick", description="Kick a member.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"? Kicked {member.mention} | Reason: {reason}")

@bot.tree.command(name="timeout", description="Mute a member in minutes.")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"? Timed out {member.mention} for {minutes}m | Reason: {reason}")

@bot.tree.command(name="purge", description="Purge multiple messages.")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"?? Purged {len(deleted)} messages.", ephemeral=True)

# --- AI ENHANCED TICKET SYSTEM ---
class AIInteractiveTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket ??", style=discord.ButtonStyle.primary, custom_id="astria_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites
        )
        await interaction.response.send_message(f"Ticket opened: {ticket_channel.mention}", ephemeral=True)
        
        # Initial greeting with AI auto-response notice
        await ticket_channel.send(
            f"Welcome {interaction.user.mention}! Staff has been notified.\n"
            "*AstriaBot AI is listening—feel free to type your issue below for an instant answer while you wait for human support!*"
        )

@bot.tree.command(name="settickets", description="Deploy the AI Ticket Panel.")
@app_commands.checks.has_permissions(administrator=True)
async def settickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="?? Cosmic Hangout Support",
        description="Click below to open a ticket. AstriaBot AI and our Staff Team are ready to assist!",
        color=discord.Color.purple()
    )
    await interaction.channel.send(embed=embed, view=AIInteractiveTicketView())
    await interaction.response.send_message("Ticket Panel Deployed!", ephemeral=True)

bot.run(DISCORD_TOKEN)
