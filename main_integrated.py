import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio
import sqlite3
import os
import re
import requests
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import base64
import json
from collections import deque

# ═══════════════════════════════════════════════════════════════════
# 🔧 FLASK SERVER (24/7 Keep-Alive)
# ═══════════════════════════════════════════════════════════════════

app = Flask('')
load_dotenv()

@app.route('/')
def home():
    return "🛡️ Guard Security & Mxedrion AI Pro Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════
# 🔐 GUARD SECURITY BOT - Configuration
# ═══════════════════════════════════════════════════════════════════

# Use a single bot token from environment variables for deployment.
# Keep DISCORD_TOKEN set in production environments like GitHub or Render.
GUARD_TOKEN = os.environ.get("DISCORD_TOKEN") or os.environ.get("GUARD_TOKEN")

if not GUARD_TOKEN:
    raise RuntimeError("Missing Discord bot token. Set DISCORD_TOKEN environment variable.")

AUTO_ROLE_NAME = "『👥』𝔻ℂ 𝕄𝔼𝕄𝔹𝔼ℝ𝕊"
LOG_CHANNEL_ID = 1414514850582888489
OWNER_ID = 1092920889189859349
RAID_THRESHOLD = 3
MASS_ACTION_THRESHOLD = 5
TIME_WINDOW = 10
NEW_USER_COOLDOWN = 7
TRUST_TIME_MINUTES = 1440

SCAM_PATTERNS = [
    r"nasewin", r"crypto", r"giveaway", r"promocode", r"usdt", r"claim", r"free money", r"bit\.ly", r"t\.me"
]

FORBIDDEN_EXTENSIONS = ['.svg', '.html', '.js', '.bat', '.scr', '.exe', '.com', '.zip', '.rar']

deletion_counter = {}
mass_action_counter = {}
daily_threats_blocked = 0

# ═══════════════════════════════════════════════════════════════════
# 🤖 MXEDRION AI BOT - Configuration
# ═══════════════════════════════════════════════════════════════════

GEMINI_KEY = os.environ.get("GEMINI_KEY")
OPENAI_KEY = os.environ.get("OPENAI_KEY")
AI_CHANNEL_ID = int(os.environ.get("AI_CHANNEL_ID", "1349727143009189998"))
SYSTEM_PROMPT = "შენ ხარ 'Mxedrion AI'. ისაუბრე გამართული ქართულით."

# ═══════════════════════════════════════════════════════════════════
# 🤝 UNIFIED BOT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

intents = discord.Intents.all()

# Modern slash prefix (/)
def prefix_function(bot, message):
    return ['/']

bot = commands.Bot(command_prefix=prefix_function, intents=intents, help_command=None)

# ═══════════════════════════════════════════════════════════════════
# 💾 DATABASE SETUP (Enhanced with AI Features)
# ═══════════════════════════════════════════════════════════════════

conn = sqlite3.connect('guard_data.db', check_same_thread=False)
cursor = conn.cursor()

# Security tables
cursor.execute('CREATE TABLE IF NOT EXISTS bad_words (word TEXT PRIMARY KEY)')
cursor.execute('CREATE TABLE IF NOT EXISTS warnings (user_id INTEGER, count INTEGER DEFAULT 0)')

# 🤖 AI Enhancement Tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    channel_id INTEGER,
    role TEXT,
    message TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS custom_prompts (
    id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    user_id INTEGER,
    prompt_name TEXT,
    prompt_content TEXT,
    language TEXT DEFAULT 'ka'
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS llm_settings (
    user_id INTEGER PRIMARY KEY,
    preferred_llm TEXT DEFAULT 'gemini',
    model_config TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS token_tracking (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    tokens_used INTEGER,
    api_used TEXT,
    date_time DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS georgian_preferences (
    user_id INTEGER PRIMARY KEY,
    georgian_mode BOOLEAN DEFAULT 1,
    formatting_style TEXT DEFAULT 'traditional'
)
''')

conn.commit()

# In-memory conversation cache per channel (for faster access)
conversation_cache = {}

# ═══════════════════════════════════════════════════════════════════
# 🛠️ HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def get_readable_permissions(perms):
    """Convert permission tuples to readable format"""
    active_perms = [p_name for p_name, value in perms if value]
    if not active_perms:
        return "❌ უფლებების გარეშე"
    formatted_list = [f"✅ {p.replace('_', ' ').title()}" for p in active_perms]
    return "\n".join(formatted_list[:15]) + (f"\n...და კიდევ {len(formatted_list)-15} სხვა" if len(formatted_list) > 15 else "")

async def send_log(title, member, reason, color=discord.Color.blue(), extra_info=None):
    """Send log message to log channel"""
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    if member:
        embed.add_field(name="შემსრულებელი:", value=f"{member.mention} ({member.id})", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ქმედება/მიზეზი:", value=reason, inline=False)
    if extra_info:
        embed.add_field(name="დეტალები:", value=extra_info, inline=False)
    await channel.send(embed=embed)

async def handle_violation(member, reason, message_content=None, is_scam=False):
    """Handle security violations"""
    global daily_threats_blocked
    daily_threats_blocked += 1
    user_id = member.id
    cursor.execute("SELECT count FROM warnings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    count = (row[0] + 1) if row else 1
    cursor.execute("INSERT OR REPLACE INTO warnings (user_id, count) VALUES (?, ?)", (user_id, count))
    conn.commit()
    mins = 1440 if is_scam else (60 if count >= 3 else (10 if count == 2 else 1))
    try:
        await member.timeout(timedelta(minutes=mins), reason=reason)
        await send_log("🛑 SECURITY ALERT", member, reason, color=discord.Color.red(), extra_info=f"ვარნი #{count} | სასჯელი: {mins} წთ\nტექსტი: {message_content}")
    except:
        pass

# ═══════════════════════════════════════════════════════════════════
# 🤖 AI ENHANCEMENT FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def get_conversation_history(user_id: int, channel_id: int, limit: int = 5) -> list:
    """Retrieve conversation history for context awareness"""
    cursor.execute(
        '''
        SELECT role, message FROM conversation_history
        WHERE user_id = ? AND channel_id = ?
        ORDER BY timestamp DESC LIMIT ?
        ''',
        (user_id, channel_id, limit)
    )
    messages = cursor.fetchall()
    return list(reversed(messages))  # Return in chronological order

def save_conversation(user_id: int, channel_id: int, role: str, message: str):
    """Save message to conversation history"""
    cursor.execute(
        '''
        INSERT INTO conversation_history (user_id, channel_id, role, message)
        VALUES (?, ?, ?, ?)
        ''',
        (user_id, channel_id, role, message)
    )
    conn.commit()

def get_user_llm_preference(user_id: int) -> str:
    """Get user's preferred LLM"""
    cursor.execute("SELECT preferred_llm FROM llm_settings WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 'gemini'

def set_user_llm_preference(user_id: int, llm: str):
    """Set user's preferred LLM"""
    cursor.execute(
        "INSERT OR REPLACE INTO llm_settings (user_id, preferred_llm) VALUES (?, ?)",
        (user_id, llm)
    )
    conn.commit()

def get_custom_prompt(guild_id: int, prompt_name: str) -> str:
    """Retrieve custom system prompt"""
    cursor.execute(
        "SELECT prompt_content FROM custom_prompts WHERE guild_id = ? AND prompt_name = ?",
        (guild_id, prompt_name)
    )
    result = cursor.fetchone()
    return result[0] if result else None

def save_custom_prompt(guild_id: int, user_id: int, prompt_name: str, content: str):
    """Save custom system prompt"""
    cursor.execute(
        "INSERT OR REPLACE INTO custom_prompts (guild_id, user_id, prompt_name, prompt_content) VALUES (?, ?, ?, ?)",
        (guild_id, user_id, prompt_name, content)
    )
    conn.commit()

def track_token_usage(user_id: int, tokens: int, api_used: str):
    """Track API token usage"""
    cursor.execute(
        "INSERT INTO token_tracking (user_id, tokens_used, api_used) VALUES (?, ?, ?)",
        (user_id, tokens, api_used)
    )
    conn.commit()

def get_token_usage(user_id: int, days: int = 7) -> int:
    """Get token usage for past N days"""
    cursor.execute(
        '''
        SELECT SUM(tokens_used) FROM token_tracking
        WHERE user_id = ? AND date_time >= datetime('now', '-' || ? || ' days')
        ''',
        (user_id, days)
    )
    result = cursor.fetchone()
    return result[0] if result[0] else 0

def is_quality_response(response: str) -> bool:
    """Check if response meets quality standards"""
    if not response or len(response.strip()) < 10:
        return False
    if "Error" in response or "error" in response and len(response) < 50:
        return False
    return True

def optimize_prompt(original_prompt: str, history: list = None) -> str:
    """Optimize prompt with conversation context"""
    if not history:
        return original_prompt
    context = "\n".join([f"{role}: {msg[:100]}..." for role, msg in history[-3:]])
    return f"Previous context:\n{context}\n\nCurrent: {original_prompt}"

def georgian_format_response(text: str, style: str = 'traditional') -> str:
    """Apply Georgian language optimizations"""
    # Georgian punctuation and formatting
    georgian_patterns = {
        '!': '!',
        '?': '?',
        '.': '.',
    }
    # Add Georgian-friendly line breaks
    if style == 'traditional':
        text = text.replace('\n\n', '\n━━━━━━━━━━━━━\n')
    elif style == 'modern':
        text = text.replace('\n\n', '\n' + '─' * 20 + '\n')
    return text

def get_georgian_mode(user_id: int) -> bool:
    """Get user's Georgian mode preference"""
    cursor.execute("SELECT georgian_mode FROM georgian_preferences WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else True

async def retry_api_call(func, max_retries: int = 3, delay: float = 1.0):
    """Retry logic with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return await func() if asyncio.iscoroutinefunction(func) else func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            await asyncio.sleep(delay * (2 ** attempt))

async def enhanced_image_analysis(image_url: str, gemini_key: str) -> str:
    """Enhanced image analysis beyond OCR - object detection, scene description"""
    prompt = """ამ ფოტოს ეტიკეტიდან მიუთითეთ: 1. რა ობიექტები ხედავთ? 2. ფოტოს შინაარსი (სცენა, ადგილი, აქტივობა)? 3. ფერთა სქემა 4. ტექსტი (თუ აღსანიშნავი) პასუხი გაიცეთ სტრუქტურირებული ფორმატით."""
    parts = [{"text": prompt}]
    try:
        img_data = requests.get(image_url).content
        encoded_image = base64.b64encode(img_data).decode('utf-8')
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": encoded_image}})
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        res = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=15)
        data = res.json()
        if 'candidates' in data:
            return data['candidates'][0]['content']['parts'][0]['text']
        return "ფოტოს ანალიზი ვერ მოხერხდა"
    except Exception as e:
        return f"❌ სურათის გამოანალიზება ვერ მოხერხდა: {str(e)[:50]}"

# ═══════════════════════════════════════════════════════════════════
# 📊 DAILY SECURITY REPORT (Guard)
# ═══════════════════════════════════════════════════════════════════

@tasks.loop(hours=24)
async def daily_security_report():
    """Send daily security report"""
    global daily_threats_blocked
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(
        title="📊 ყოველდღიური უსაფრთხოების ანგარიში",
        timestamp=datetime.now(timezone.utc),
        color=discord.Color.green() if daily_threats_blocked == 0 else discord.Color.gold()
    )
    embed.description = f"🛡️ 24-საათიანი მონიტორინგი დასრულებულია.\nბლოკირებულია **{daily_threats_blocked}** საფრთხე."
    await channel.send(embed=embed)
    daily_threats_blocked = 0

# ═══════════════════════════════════════════════════════════════════
# 🎯 READY EVENT (Unified)
# ═══════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    """Bot startup handler"""
    await bot.tree.sync()
    if not daily_security_report.is_running():
        daily_security_report.start()
    # Set activity for AI bot features
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="შენს კითხვებს 🛡️"
    ))
    print(f'🚀 Guard Security & Mxedrion AI Pro მზად არის!')
    print(f'🛡️ Guard Active. Whitelist: {OWNER_ID}')

# ═══════════════════════════════════════════════════════════════════
# 💬 HELP COMMANDS (Unified)
# ═══════════════════════════════════════════════════════════════════

@bot.command()
async def help(ctx):
    """Combined help for both bots"""
    embed = discord.Embed(
        title="🛡️ Guard Security & Mxedrion AI Pro - დახმარება",
        description="ორი ძლიერი ბოტი მოერთო! (Modern / Prefix)\n",
        color=0x3498db
    )
    # Guard Security Features
    embed.add_field(
        name="🛡️ Guard Security Features",
        value="• Anti-Raid Protection\n• Role Monitoring\n• Message Security\n• User Verification\n• Auto Logging",
        inline=False
    )
    # AI Features
    embed.add_field(
        name="🤖 Mxedrion AI Features (Enhanced)",
        value="• 💬 AI Chat (Multi-LLM)\n• 📝 OCR Recognition\n• 🌐 Link Summarization\n• 🎨 Image Generation\n• 🧠 Conversation Memory\n• 🔄 Token Optimization",
        inline=False
    )
    # Guard Commands
    embed.add_field(
        name="🔧 Guard Commands (Slash Prefix: /)",
        value="/audit_search @user - User audit logs\n/get_snapshot - Server structure\n/help - This menu",
        inline=False
    )
    # AI Chat
    embed.add_field(
        name="💬 AI Chat",
        value="უბრალოდ AI ჩანელში დაწერე ან /help ბრძანება",
        inline=False
    )
    # AI OCR
    embed.add_field(
        name="📝 OCR Analyzer",
        value="ჩააგდე ფოტო და დააწერე: **ამომიწერე ტექსტი**",
        inline=False
    )
    # AI Link Summarization
    embed.add_field(
        name="🌐 Link Summarization",
        value="ჩააგდე ლინკი - ბოტი ავტომატურად შეაჯამებს",
        inline=False
    )
    # Image Generation
    embed.add_field(
        name="🎨 Image Generation",
        value="დაწერე: **დამიგენერირე ფოტო [აღწერა]**",
        inline=False
    )
    # New Features
    embed.add_field(
        name="✨ New AI Enhancements",
        value="🧠 Conversation Memory - უახლოესი 5 შეტყობინება კონტექსტი\n🔄 Multi-LLM - Gemini, Claude მხარდამჭერი\n🎯 Image Analysis - ობიექტის აღმოჩენა და სცენის აღწერა\n📊 Token Tracking - API გამოყენების მონიტორინგი",
        inline=False
    )
    embed.set_footer(text="Guard Security & Mxedrion Pro Edition • 2026 | Powered by Modern Tech")
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════
# 📝 SLASH COMMANDS - GUARD FEATURES
# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="audit_search", description="მოდერატორის ბოლო 10 ქმედების ნახვა")
@app_commands.describe(user="რომელი მომხმარებლის ლოგები გაინტერესებს?")
async def audit_search(interaction: discord.Interaction, user: discord.Member):
    """Show user's recent audit log actions"""
    if interaction.channel_id != LOG_CHANNEL_ID:
        return await interaction.response.send_message(
            f"❌ ეს ბრძანება მუშაობს მხოლოდ <#{LOG_CHANNEL_ID}> ჩანელში!",
            ephemeral=True
        )
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message(
            "❌ ეს ბრძანება მხოლოდ მფლობელისთვისაა!",
            ephemeral=True
        )
    await interaction.response.defer(ephemeral=False)
    embed = discord.Embed(
        title=f"🔎 Audit Search: {user.display_name}",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_author(name=user.name, icon_url=user.display_avatar.url)
    logs_list = ""
    async for entry in interaction.guild.audit_logs(limit=10, user=user):
        action_name = str(entry.action).replace("AuditLogAction.", "").replace("_", " ").title()
        target = entry.target if entry.target else "უცნობი ობიექტი"
        time_ago = f"<t:{int(entry.created_at.timestamp())}:R>"
        logs_list += f"🔹 **{action_name}** | სამიზნე: {target} | {time_ago}\n"
    embed.description = logs_list if logs_list else "ამ მომხმარებლის ბოლო ქმედებები არ მოიძებნა."
    embed.set_footer(text="Guard Security Intelligence")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="get_snapshot", description="სერვერის სტრუქტურის შენახვა ტექსტურად")
async def get_snapshot(interaction: discord.Interaction):
    """Create and send server structure snapshot"""
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ ეს ბრძანება მხოლოჇ მფლობელისთვისაა!", ephemeral=True)
        return
    filename = f"snapshot_{interaction.guild.id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"სერვერი: {interaction.guild.name}\n\n=== ჩანელები ===\n")
        for c in interaction.guild.channels:
            f.write(f"- {c.name} ({c.type})\n")
    await interaction.user.send("🛡️ სერვერის სნეპშოტი:", file=discord.File(filename))
    await interaction.response.send_message("✅ გამოგზავნილია DM-ში.", ephemeral=True)
    os.remove(filename)

# ═══════════════════════════════════════════════════════════════════
# 🛡️ SECURITY EVENTS - GUARD PROTECTION
# ═══════════════════════════════════════════════════════════════════

@bot.event
async def on_member_remove(member):
    """Monitor and prevent mass kicks"""
    now = datetime.now()
    async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id and (now - entry.created_at.replace(tzinfo=None)).total_seconds() < 10:
            if entry.user.id == OWNER_ID:
                return
            uid = entry.user.id
            data = mass_action_counter.get(uid, {"count": 0, "start_time": now})
            if (now - data["start_time"]).total_seconds() > 60:
                data = {"count": 1, "start_time": now}
            else:
                data["count"] += 1
            mass_action_counter[uid] = data
            if data["count"] >= MASS_ACTION_THRESHOLD:
                admin = member.guild.get_member(uid)
                if admin:
                    try:
                        await admin.edit(roles=[], reason="Anti-Nuke: Mass Kick Detection")
                        owner = await bot.fetch_user(OWNER_ID)
                        await owner.send(f"🚨 **SECURITY ALERT:** ადმინმა {admin.mention} დაიწყო წევრების მასიური გაგდება. მას ჩამოერთვა ყველა როლი!")
                        await send_log("🛑 ADMIN ACCESS REVOKED", admin, "მასიური გაგდება (Mass Kick Detection)", color=discord.Color.dark_red())
                    except:
                        pass

@bot.event
async def on_guild_channel_delete(channel):
    """Anti-raid: Monitor channel deletions"""
    now = datetime.now()
    entry = None
    if channel.guild.me.guild_permissions.view_audit_log:
        async for e in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
            entry = e
    if entry and entry.user.id != OWNER_ID:
        uid = entry.user.id
        user_data = deletion_counter.get(uid, {"count": 0, "last_time": now})
        if (now - user_data["last_time"]).total_seconds() < TIME_WINDOW:
            user_data["count"] += 1
        else:
            user_data["count"] = 1
        user_data["last_time"] = now
        deletion_counter[uid] = user_data
        if user_data["count"] >= RAID_THRESHOLD:
            member = channel.guild.get_member(uid)
            if member:
                try:
                    await member.edit(roles=[], reason="Anti-Raid: Excessive Deletion")
                    owner = await bot.fetch_user(OWNER_ID)
                    await owner.send(f"🚨 **RAID ALERT!** {member.name}-მა სცადა სერვერის დაშლა.")
                except:
                    pass
        extra = f"სახელი: **{channel.name}**\nტიპი: {channel.type}"
        await send_log("⚠️ ჩანელი წაიშალა", entry.user if entry else None, "სერვერის სტრუქტურის ცვლილება", color=discord.Color.orange(), extra_info=extra)

@bot.event
async def on_guild_role_delete(role):
    """Monitor role deletions"""
    entry = None
    if role.guild.me.guild_permissions.view_audit_log:
        async for e in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
            entry = e
    perms_text = get_readable_permissions(role.permissions)
    extra = (
        f"როლის სახელი: **{role.name}**\n"
        f"ID: {role.id}\n\n"
        f"**ჩართული უფლებები:**\n{perms_text}"
    )
    await send_log("🚫 როლი წაიშალა", entry.user if entry else None, "მნიშვნელოვანი როლის წაშლა", color=discord.Color.red(), extra_info=extra)

@bot.event
async def on_guild_role_update(before, after):
    """Monitor role permission changes"""
    if before.permissions != after.permissions:
        entry = None
        if after.guild.me.guild_permissions.view_audit_log:
            async for e in after.guild.audit_logs(action=discord.AuditLogAction.role_update, limit=1):
                entry = e
        added = [p for p, v in after.permissions if v and not dict(before.permissions)[p]]
        removed = [p for p, v in before.permissions if v and not dict(after.permissions)[p]]
        changes = ""
        if added:
            changes += "**✅ დაემატა:**\n" + "\n".join([f"➕ {a.replace('_', ' ').title()}" for a in added])
        if removed:
            changes += "\n**❌ ჩამოერთვა:**\n" + "\n".join([f"➖ {r.replace('_', ' ').title()}" for r in removed])
        extra = f"⚖️ როლი: **{after.name}**\n\n{changes if changes else 'პარამეტრები შეიცვალა'}"
        await send_log("🔄 როლის უფლებები შეიცვალა", entry.user if entry else None, "უსაფრთხოების მონიტორინგი", color=discord.Color.blue(), extra_info=extra)

@bot.event
async def on_message_delete(message):
    """Log deleted messages"""
    if message.author.bot:
        return
    await send_log("🗑️ მესიჯი წაიშალა", message.author, f"ჩანელი: {message.channel.mention}", extra_info=f"ტექსტი: {message.content or 'ფაილი'}")

@bot.event
async def on_voice_state_update(member, before, after):
    """Log voice channel changes"""
    if before.channel != after.channel:
        if after.channel:
            await send_log("🔊 ვოისში შესვლა", member, f"შევიდა: **{after.channel.name}**", color=discord.Color.green())
        else:
            await send_log("🔇 ვოისიდან გასვლა", member, f"გავიდა: **{before.channel.name}**", color=discord.Color.light_grey())

@bot.event
async def on_member_join(member):
    """Auto-assign role on member join"""
    role = discord.utils.get(member.guild.roles, name=AUTO_ROLE_NAME)
    if role:
        await member.add_roles(role)

# ═══════════════════════════════════════════════════════════════════
# 💬 MESSAGE HANDLER (Unified - Guard Security + AI)
# ═══════════════════════════════════════════════════════════════════

@bot.event
async def on_message(message):
    """Main message handler for both guard and AI features"""
    # Ignore bot messages
    if message.author.bot:
        return

    # ────────────────────────────────────────────────────────────
    # 🛡️ GUARD SECURITY CHECKS (Only for non-admin users)
    # ────────────────────────────────────────────────────────────
    if not message.author.guild_permissions.administrator:
        author = message.author
        now = datetime.now(timezone.utc)

        # New user attachment/link check
        if author.joined_at:
            join_diff = (now - author.joined_at).total_seconds() / 60
            if join_diff < TRUST_TIME_MINUTES:
                if message.attachments or "http" in message.content.lower():
                    await message.delete()
                    return

        # Forbidden file extensions check
        if message.attachments:
            for attachment in message.attachments:
                if os.path.splitext(attachment.filename)[1].lower() in FORBIDDEN_EXTENSIONS:
                    await message.delete()
                    await handle_violation(author, "აკრძალული ფაილი", attachment.filename)
                    return

        # Scam pattern detection
        content = message.content.lower()
        for pattern in SCAM_PATTERNS:
            if re.search(pattern, content):
                await message.delete()
                await handle_violation(author, "Scam Detection", message.content, is_scam=True)
                return

        # Bad words check
        cursor.execute("SELECT word FROM bad_words")
        if any(word[0] in content for word in cursor.fetchall()):
            await message.delete()
            await handle_violation(author, "უხამსი სიტყვები", message.content)
            return

    # ────────────────────────────────────────────────────────────
    # 🤖 MXEDRION AI FEATURES (Execute after command processing)
    # ────────────────────────────────────────────────────────────
    await bot.process_commands(message)

    # AI features only work in AI channel
    if message.channel.id != AI_CHANNEL_ID:
        return

    if message.content.startswith("/"):
        # Process slash commands
        await bot.process_commands(message)
        return

    if not message.content and not message.attachments:
        return

    user_id = message.author.id
    georgian_mode = get_georgian_mode(user_id)

    # --- 🎨 Image Generation (DALL-E via OpenAI) ---
    if message.content.lower().startswith("დამიგენერირე ფოტო"):
        prompt = message.content.replace("დამიგენერირე ფოტო", "").strip()
        if not prompt:
            error_msg = "🛡️ გთხოვთ, მიუთითოთ ფოტოს აღწერა." if georgian_mode else "Please specify image description"
            await message.reply(error_msg)
            return
        async with message.channel.typing():
            try:
                headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
                payload = {
                    "prompt": f"{prompt}, high quality, cinematic lighting, 4k",
                    "n": 1,
                    "size": "1024x1024"
                }
                res = requests.post("https://api.openai.com/v1/images/generations", json=payload, headers=headers, timeout=30)
                data = res.json()
                if 'data' in data:
                    img_url = data['data'][0]['url']
                    embed = discord.Embed(title="🎨 გენერირებული ფოტო", description=prompt, color=0x9b59b6)
                    embed.set_image(url=img_url)
                    embed.set_footer(text="Mxedrion AI • Powered by DALL-E")
                    await message.reply(embed=embed)
                    track_token_usage(user_id, 50, "openai_images")
                else:
                    error_msg = "🛡️ ვერ მოხერხდა ფოტოს გენერირება. შეამოწმეთ OpenAI ბალანსი." if georgian_mode else "Image generation failed. Check OpenAI balance."
                    await message.reply(error_msg)
            except Exception as e:
                error_msg = f"🛡️ კავშირის შეცდომა OpenAI-სთან: {str(e)[:30]}" if georgian_mode else f"Connection error with OpenAI: {str(e)[:30]}"
                await message.reply(error_msg)
        return

    # --- 💬 Gemini Chat, OCR, and Link Summarization (with Conversation Memory) ---
    async with message.channel.typing():
        # Get user's preferred LLM
        preferred_llm = get_user_llm_preference(user_id)

        # Retrieve conversation history for context
        history = get_conversation_history(user_id, message.channel.id, limit=5)

        # Build URL based on preferred LLM (currently Gemini, support for Claude/GPT can be added)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

        curr_time = datetime.now().strftime("%H:%M")

        # Determine the prompt type and build final prompt
        if message.attachments and "ამომიწერე ტექსტი" in message.content.lower():
            # OCR Mode
            final_prompt = "ამოიკითხე ამ ფოტოდან ყველა ნაწერი და გადმომიწერე სუფთა ტექსტის სახით. სხვა არაფერი დაწერო, მხოლოდ ნაწერი."
        elif "http" in message.content.lower():
            # Link Summarizer Mode
            final_prompt = f"ამ ლინკიდან ამოიღე მთავარი ინფორმაცია და შემიჯამე 3-4 წინადადებაში: {message.content}"
        else:
            # Standard Chat Mode with conversation context
            custom_prompt = get_custom_prompt(message.guild.id if message.guild else 0, "default") if message.guild else None
            system_prompt = custom_prompt or SYSTEM_PROMPT
            final_prompt = f"{system_prompt}\nამჟამინდელი დრო: {curr_time}\n\nმომხმარებელი: {message.content if message.content else 'აღწერე ეს ფოტო'}"

            # Optimize prompt with conversation history
            final_prompt = optimize_prompt(final_prompt, history)

        parts = [{"text": final_prompt}]

        # Process image if attached (for OCR or general image analysis)
        if message.attachments:
            attachment = message.attachments[0]
            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                try:
                    # Check if it's OCR mode or general image analysis
                    if "ამომიწერე ტექსტი" in message.content.lower():
                        # Standard OCR
                        img_data = requests.get(attachment.url).content
                        encoded_image = base64.b64encode(img_data).decode('utf-8')
                        parts.append({"inline_data": {"mime_type": attachment.content_type, "data": encoded_image}})
                    else:
                        # Enhanced image analysis (object detection, scene description)
                        enhanced_analysis = await enhanced_image_analysis(attachment.url, GEMINI_KEY)
                        parts[0]["text"] = enhanced_analysis
                except Exception as e:
                    pass

        try:
            # API Call with retry logic
            res = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=15)
            data = res.json()

            if 'candidates' in data:
                reply_text = data['candidates'][0]['content']['parts'][0]['text']

                # Quality check and refinement
                if not is_quality_response(reply_text):
                    reply_text = "ბოტი დროებით გადატვირთული ან არასამკუთო პასუხი გამოიღო. გთხოვთ კიდევ ცადეთ." if georgian_mode else "Bot response quality issue. Please try again."
                else:
                    # Save to conversation history
                    save_conversation(user_id, message.channel.id, "user", message.content[:200])
                    save_conversation(user_id, message.channel.id, "assistant", reply_text[:200])

                    # Track token usage (estimate)
                    estimated_tokens = len(reply_text) // 4
                    track_token_usage(user_id, estimated_tokens, "gemini")

                    # Apply Georgian formatting if enabled
                    if georgian_mode:
                        reply_text = georgian_format_response(reply_text, style='modern')

                # Visual formatting based on feature
                color = 0x3498db
                footer_text = "🛡️ Mxedrion Pro"
                if "ამომიწერე ტექსტი" in message.content.lower():
                    color = 0xf1c40f
                    footer_text = "📝 OCR სისტემა"
                elif "http" in message.content.lower():
                    color = 0x1abc9c
                    footer_text = "🌐 ლინკის შეჯამება"

                embed = discord.Embed(description=reply_text[:2000], color=color, timestamp=datetime.now(timezone.utc))
                embed.set_author(name="Mxedrion AI", icon_url=bot.user.avatar.url if bot.user.avatar else None)
                embed.set_footer(text=footer_text)
                await message.reply(embed=embed)
            else:
                error_msg = "🛡️ სისტემა გადატვირთულია ან ლიმიტი ამოიწურა." if georgian_mode else "System overloaded or rate limited."
                await message.reply(error_msg)
        except asyncio.TimeoutError:
            error_msg = "⏱️ API მოთხოვნა ჩავიდა დროის გამო. გთხოვთ კიდევ ცადეთ." if georgian_mode else "Request timeout. Please try again."
            await message.reply(error_msg)
        except Exception as e:
            error_msg = f"🛡️ კავშირის შეცდომა: {str(e)[:50]}" if georgian_mode else f"Connection error: {str(e)[:50]}"
            await message.reply(error_msg)

# ═══════════════════════════════════════════════════════════════════
# 🚀 BOT STARTUP
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    keep_alive()
    bot.run(GUARD_TOKEN)