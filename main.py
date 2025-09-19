import os
import json
import requests
from flask import Flask, render_template, redirect, url_for, request, session
from threading import Thread
from discord.ext import commands
from discord import Intents
import discord
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ===================== Data Directory Setup =====================
# Ensure data directory and required files exist
def init_data_directory():
    """Initialize data directory and create required files if they don't exist"""
    print("Initializing data directory structure...")
    
    # Create main data directory
    if not os.path.exists("data"):
        os.makedirs("data")
        print("Created data directory")
    
    # Create warnings file
    warnings_path = os.path.join("data", "warnings.json")
    if not os.path.exists(warnings_path):
        with open(warnings_path, "w") as f:
            json.dump({}, f, indent=2)
        print(f"Created {warnings_path}")
    
    print("Data directory initialization complete!")

def create_test_guild_config(guild_id):
    """Create a test configuration for a specific guild"""
    guild_dir = os.path.join("data", str(guild_id))
    if not os.path.exists(guild_dir):
        os.makedirs(guild_dir)
        print(f"Created directory for guild {guild_id}")
    
    config_path = os.path.join(guild_dir, "config.json")
    if not os.path.exists(config_path):
        default_config = {
            "welcome_channel": None,
            "welcome_message": "Welcome {ping} to {server_name}! We now have {members} members.",
            "join_role": None,
            "blacklisted_words": [],
            "ticket_categories": ["Support", "Bug Report", "Feature Request", "Other"],
            "ticket_message": "Click a button below to create a ticket!"
        }
        
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)
        print(f"Created default config for guild {guild_id}")

# ===================== Flask Setup =====================
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))  # required for session

# Discord OAuth2 Configuration
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Flask Configuration
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.getenv('FLASK_PORT', '13526'))
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# Validate required environment variables
if not all([DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI, BOT_TOKEN]):
    raise EnvironmentError("Missing required Discord configuration in .env file")

# ===================== Bot Setup =====================
PREFIX = os.getenv('PREFIX', 'ss!')
INTENTS = Intents.default()
INTENTS.guilds = True
INTENTS.members = True
INTENTS.messages = True
INTENTS.message_content = True  # This is required for commands to work
INTENTS.guild_reactions = True

bot = commands.Bot(command_prefix=PREFIX, intents=INTENTS, help_command=None)  # disable default help

# ===================== Load Cogs =====================
COGS = ["cogs.utility", "cogs.moderation", "cogs.tickets", "cogs.fun"]

async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded cog: {cog}")
        except Exception as e:
            print(f"❌ Failed to load cog {cog}: {e}")
            # Try without cogs prefix for backwards compatibility
            try:
                cog_name = cog.split('.')[-1]  # Get just the filename
                await bot.load_extension(cog_name)
                print(f"✅ Loaded cog (alt method): {cog_name}")
            except Exception as e2:
                print(f"❌ Failed to load cog {cog_name}: {e2}")

@bot.event
async def on_ready():
    print(f"✅ Bot connected as {bot.user}")
    print(f"📊 Bot is in {len(bot.guilds)} servers")
    print(f"🔧 Loaded {len(bot.cogs)} cogs: {list(bot.cogs.keys())}")
    
    # Initialize data directory structure
    init_data_directory()
    
    # Create default configs for all guilds the bot is in
    for guild in bot.guilds:
        guild_dir = os.path.join("data", str(guild.id))
        config_path = os.path.join(guild_dir, "config.json")
        
        # Create guild directory if it doesn't exist
        if not os.path.exists(guild_dir):
            os.makedirs(guild_dir)
        
        # Create default config if it doesn't exist
        if not os.path.exists(config_path):
            default_config = {
                "welcome_channel": None,
                "welcome_message": "Welcome {ping} to {server_name}! We now have {members} members.",
                "join_role": None,
                "blacklisted_words": [],
                "ticket_categories": ["Support", "Bug Report", "Feature Request", "Other"],
                "ticket_message": "Click a button below to create a ticket!"
            }
            
            with open(config_path, "w") as f:
                json.dump(default_config, f, indent=2)
            print(f"Created default config for guild {guild.id}")
    
    # Set bot status
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name=f"{len(bot.guilds)} servers | ss!help"
    )
    await bot.change_presence(activity=activity, status=discord.Status.online)
    print("🚀 Bot is ready!")

@bot.event 
async def on_command_error(ctx, error):
    """Global error handler for commands"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore command not found errors
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command!")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have the required permissions to execute this command!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param}")
    else:
        print(f"❌ Command error in {ctx.command}: {error}")
        await ctx.send("❌ An error occurred while executing this command!")

# ===================== OAuth2 Helpers =====================
DISCORD_OAUTH_URL = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20guilds"

def get_user_info(token):
    """Get user information from Discord API"""
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get("https://discord.com/api/users/@me", headers=headers)
    if res.status_code == 200:
        return res.json()
    return None

def get_user_guilds(token):
    """Get user's guilds from Discord API"""
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get("https://discord.com/api/users/@me/guilds", headers=headers)
    if res.status_code == 200:
        guilds = res.json()
        # Filter guilds where user has manage server permissions and bot is present
        filtered_guilds = []
        for guild in guilds:
            # Check if user has manage server permission (0x20 = MANAGE_GUILD)
            if guild.get('permissions', 0) & 0x20:
                # Check if bot is in the guild
                bot_guild = bot.get_guild(int(guild['id']))
                if bot_guild:
                    filtered_guilds.append(guild)
        return filtered_guilds
    return []

def get_bot_guilds():
    """Get guilds the bot is in"""
    return [{'id': str(guild.id), 'name': guild.name} for guild in bot.guilds]

# ===================== Flask Routes =====================
@app.route("/")
def start():
    return render_template("start.html")

@app.route("/tos")
def tos():
    return render_template("tos.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/login")
def login():
    return redirect(DISCORD_OAUTH_URL)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("start"))

    # Exchange code for access token
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify guilds"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        token_res = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
        token_data = token_res.json()
        
        if "access_token" not in token_data:
            print(f"OAuth error: {token_data}")
            return redirect(url_for("start"))
            
        session["access_token"] = token_data.get("access_token")
        return redirect(url_for("servers"))
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return redirect(url_for("start"))

@app.route("/servers")
def servers():
    if "access_token" not in session:
        return redirect(url_for("login"))
    
    try:
        # Get user info
        user_info = get_user_info(session["access_token"])
        if not user_info:
            return redirect(url_for("login"))
        
        # Get user's guilds where they can manage and bot is present
        guilds = get_user_guilds(session["access_token"])
        
        return render_template("servers.html", 
                             servers=guilds, 
                             guilds=guilds,  # For backward compatibility
                             username=user_info.get('username', 'Unknown'),
                             bot_guild_count=len(bot.guilds) if bot.guilds else 0)
    except Exception as e:
        print(f"Servers route error: {e}")
        return redirect(url_for("login"))

@app.route("/server/<guild_id>")
def server(guild_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    
    # Get user info
    user_info = get_user_info(session["access_token"])
    if not user_info:
        return redirect(url_for("login"))
    
    # Verify user has access to this guild
    user_guilds = get_user_guilds(session["access_token"])
    guild_ids = [g['id'] for g in user_guilds]
    
    if guild_id not in guild_ids:
        return redirect(url_for("servers"))
    
    # Get the actual guild object from the bot
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return redirect(url_for("servers"))
    
    # Get guild info from user's guilds (for permissions, etc.)
    user_guild_info = next((g for g in user_guilds if g['id'] == guild_id), None)
    
    # Create server object for template
    server_data = {
        'id': guild_id,
        'name': guild.name,
        'member_count': guild.member_count,
        'icon': user_guild_info.get('icon') if user_guild_info else None,
        'permissions': user_guild_info.get('permissions') if user_guild_info else None
    }
    
    # Load config
    config_path = f"data/{guild_id}/config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        # Create default config
        config = {
            "welcome_channel": None,
            "welcome_message": "Welcome to the server!",
            "join_role": None,
            "blacklisted_words": [],
            "ticket_categories": ["Support", "Bug Report"],
            "ticket_message": "Please select a category to create a ticket:"
        }
        # Ensure data directory exists
        os.makedirs(f"data/{guild_id}", exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
    
    # Get warned users from JSON file
    warned_users = []
    warnings_file = os.path.join("data", "warnings.json")
    if os.path.exists(warnings_file):
        try:
            with open(warnings_file, 'r') as f:
                warnings_data = json.load(f)
            
            for user_key, data in warnings_data.items():
                if data.get('guild_id') == guild_id and data.get('warns'):
                    user_id = user_key.split('_')[1] if '_' in user_key else user_key
                    member = guild.get_member(int(user_id)) if guild else None
                    warned_users.append({
                        'id': user_id,
                        'name': member.display_name if member else f"Unknown User ({user_id})",
                        'warning_count': len(data['warns'])
                    })
        except Exception as e:
            print(f"Error loading warned users: {e}")
    
    from datetime import datetime
    
    return render_template("server.html", 
                         guild_id=guild_id, 
                         config=config,
                         server=server_data,
                         settings=config,  # alias for settings
                         warned_users=warned_users,
                         username=user_info.get('username', 'Unknown'),
                         now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("start"))

# ===================== API Routes (for dashboard functionality) =====================
@app.route("/api/server/<guild_id>/data")
def api_server_data(guild_id):
    """Get server data including roles, channels, and saved settings"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    # Get the guild from bot
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return {"error": "Guild not found"}, 404
    
    # Get roles and channels
    roles = [{"id": str(role.id), "name": role.name} for role in guild.roles if role.name != "@everyone"]
    channels = [{"id": str(channel.id), "name": f"#{channel.name}"} for channel in guild.text_channels]
    
    # Get saved settings from JSON file
    config_path = os.path.join("data", str(guild_id), "config.json")
    saved = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                saved = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            saved = {
                "welcome_channel": None,
                "welcome_message": "Welcome {ping} to {server_name}! We now have {members} members.",
                "join_role": None,
                "blacklisted_words": [],
                "ticket_categories": ["Support", "Bug Report", "Feature Request", "Other"],
                "ticket_message": "Click a button below to create a ticket!"
            }
    else:
        saved = {
            "welcome_channel": None,
            "welcome_message": "Welcome {ping} to {server_name}! We now have {members} members.",
            "join_role": None,
            "blacklisted_words": [],
            "ticket_categories": ["Support", "Bug Report", "Feature Request", "Other"],
            "ticket_message": "Click a button below to create a ticket!"
        }
    
    return {
        "roles": roles,
        "channels": channels,
        "saved": saved
    }

@app.route("/api/server/<guild_id>/save", methods=["POST"])
def api_save_settings(guild_id):
    """Save server settings to JSON file"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        settings = request.get_json()
        
        # Ensure directory exists
        guild_dir = os.path.join("data", str(guild_id))
        os.makedirs(guild_dir, exist_ok=True)
        
        # Save settings to JSON file
        config_path = os.path.join(guild_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(settings, f, indent=4)
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Save settings error: {e}")
        return {"error": "Failed to save settings"}, 500

@app.route("/api/server/<guild_id>/blacklist", methods=["POST"])
def api_save_blacklist(guild_id):
    """Save blacklisted words to JSON file"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        data = request.get_json()
        blacklisted_words = data.get('blacklisted_words', [])
        
        # Load existing config
        guild_dir = os.path.join("data", str(guild_id))
        os.makedirs(guild_dir, exist_ok=True)
        config_path = os.path.join(guild_dir, "config.json")
        
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
        
        # Update blacklisted words
        config['blacklisted_words'] = blacklisted_words
        
        # Save config
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        
        return {"success": True}
    except Exception as e:
        print(f"Save blacklist error: {e}")
        return {"error": "Failed to save blacklist"}, 500

@app.route("/api/bot/status")
def api_bot_status():
    """Get bot status information"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        guild_count = len(bot.guilds)
        user_count = sum(guild.member_count for guild in bot.guilds)
        cogs_loaded = list(bot.cogs.keys())
        uptime = "Online" # In a real implementation, you would track the actual uptime
        
        return {
            "status": "online",
            "guild_count": guild_count,
            "user_count": user_count,
            "cogs_loaded": cogs_loaded,
            "uptime": uptime,
            "version": "1.0.0"
        }
    except Exception as e:
        print(f"Bot status API error: {e}")
        return {"error": "Failed to get bot status"}, 500

@app.route("/api/server/<guild_id>/create_ticket_panel", methods=["POST"])
def api_create_ticket_panel(guild_id):
    """Create ticket panel in specified channel"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        data = request.get_json()
        channel_id = data.get('channel_id')
        message = data.get('message', 'Click below to create a ticket.')
        
        print(f"Creating ticket panel: guild_id={guild_id}, channel_id={channel_id}")
        
        guild = bot.get_guild(int(guild_id))
        if not guild:
            print(f"Guild {guild_id} not found")
            return {"error": "Guild not found"}, 404
        
        channel = guild.get_channel(int(channel_id))
        if not channel:
            print(f"Channel {channel_id} not found in guild {guild_id}")
            print(f"Available channels: {[ch.id for ch in guild.text_channels]}")
            return {"error": "Channel not found"}, 404
        
        # Get or update server config with the message
        guild_dir = os.path.join("data", str(guild_id))
        os.makedirs(guild_dir, exist_ok=True)
        config_path = os.path.join(guild_dir, "config.json")
        
        config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        
        config['ticket_message'] = message
        categories = config.get('ticket_categories', ['Support', 'Bug Report', 'Feature Request', 'Other'])
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        
        # Get the tickets cog to create the panel properly
        tickets_cog = bot.get_cog('Tickets')
        if not tickets_cog:
            print("Tickets cog not found")
            return {"error": "Tickets system not available"}, 500
        
        # Use the cog's method to create a ticket panel
        async def create_panel():
            try:
                # Create embed
                embed = discord.Embed(
                    title="🎫 Support Tickets",
                    description=message,
                    color=0x00aaff
                )
                embed.add_field(
                    name="📋 Available Categories",
                    value="\n".join([f"🎫 {cat}" for cat in categories]),
                    inline=False
                )
                embed.set_footer(text="SSupport Bot - Ticket System")

                # Create view with buttons
                from discord.ui import View, Button
                view = View(timeout=None)
                
                category_emojis = {
                    'Support': '🎧',
                    'Bug Report': '🐛',
                    'Feature Request': '💡',
                    'General': '💬',
                    'Technical': '⚙️',
                    'Billing': '💳',
                    'Other': '📩'
                }
                
                for category in categories[:5]:  # Limit to 5 buttons
                    emoji = category_emojis.get(category, '🎫')
                    button = Button(
                        label=category,
                        style=discord.ButtonStyle.primary,
                        emoji=emoji,
                        custom_id=f"ticket_{category.lower().replace(' ', '_')}"
                    )
                    # Set the callback
                    button.callback = lambda i, cat=category: tickets_cog.create_ticket(i, cat)
                    view.add_item(button)

                panel_message = await channel.send(embed=embed, view=view)
                
                # Store panel message info
                panel_file = os.path.join("data", "panel_messages.json")
                panel_messages = {}
                if os.path.exists(panel_file):
                    with open(panel_file, 'r') as f:
                        panel_messages = json.load(f)
                
                panel_messages[str(guild_id)] = {
                    'channel_id': channel.id,
                    'message_id': panel_message.id,
                    'created_by': 'dashboard',
                    'created_at': datetime.now().isoformat()
                }
                
                with open(panel_file, 'w') as f:
                    json.dump(panel_messages, f, indent=4)
                
                print(f"Successfully created ticket panel in {channel.name}")
                return True
            except Exception as e:
                print(f"Error in create_panel: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(create_panel())
        loop.close()
        
        if success:
            return {"success": True}
        else:
            return {"error": "Failed to create panel"}, 500
            
    except Exception as e:
        print(f"Create ticket panel error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to create ticket panel: {str(e)}"}, 500

@app.route("/api/server/<guild_id>/bans")
def api_get_bans(guild_id):
    """Get server bans"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return {"error": "Guild not found"}, 404
        
        # Get bans (requires bot to have ban members permission)
        bans = []
        try:
            async def get_bans():
                ban_list = []
                async for ban_entry in guild.bans():
                    ban_list.append({
                        "user": str(ban_entry.user),
                        "reason": ban_entry.reason
                    })
                return ban_list
            
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bans = loop.run_until_complete(get_bans())
            loop.close()
        except Exception as e:
            print(f"Error fetching bans: {e}")
        
        return {"success": True, "bans": bans}
    except Exception as e:
        print(f"Get bans error: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/server/<guild_id>/timeouts")
def api_get_timeouts(guild_id):
    """Get server timeouts"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return {"error": "Guild not found"}, 404
        
        # Get members with timeouts
        from datetime import datetime, timezone
        timeouts = []
        for member in guild.members:
            if member.timed_out_until and member.timed_out_until > datetime.now(timezone.utc):
                timeouts.append({
                    "user": str(member),
                    "until": member.timed_out_until.isoformat()
                })
        
        return {"success": True, "timeouts": timeouts}
    except Exception as e:
        print(f"Get timeouts error: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/server/<guild_id>/tickets")
def api_get_tickets(guild_id):
    """Get open tickets"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        # Get tickets from the tickets cog
        tickets_cog = bot.get_cog('Tickets')
        if tickets_cog:
            dashboard_data = tickets_cog.get_dashboard_data(guild_id)
            return {"success": True, **dashboard_data}
        else:
            return {"success": True, "tickets": []}
    except Exception as e:
        print(f"Get tickets error: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/server/<guild_id>/create_ticket_panel", methods=["POST"])
def api_create_ticket_panels(guild_id):
    """Create ticket panel in specified channel"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        data = request.get_json()
        channel_id = data.get('channel_id')
        message = data.get('message', 'Click below to create a ticket.')
        
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return {"error": "Guild not found"}, 404
        
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return {"error": "Channel not found"}, 404
        
        # Get tickets cog and create panel
        tickets_cog = bot.get_cog('Tickets')
        if not tickets_cog:
            return {"error": "Tickets system not available"}, 500
        
        # Use the cog's method to create a ticket panel
        async def create_panel():
            try:
                # Get server config
                config = tickets_cog.get_server_config(guild_id)
                categories = config.get('ticket_categories', ['Support'])
                
                # Update message in config
                config['ticket_message'] = message
                tickets_cog.save_server_config(guild_id, config)
                
                # Create embed
                embed = discord.Embed(
                    title="🎫 Support Tickets",
                    description=message,
                    color=0x00aaff
                )
                embed.add_field(
                    name="📋 Available Categories",
                    value="\n".join([f"🎫 {cat}" for cat in categories]),
                    inline=False
                )
                embed.set_footer(text="SSupport Bot - Ticket System")

                # Create view (simplified for API creation)
                from discord.ui import View, Button
                view = View(timeout=None)
                
                for category in categories[:5]:  # Limit to 5 for buttons
                    button = Button(
                        label=category,
                        style=discord.ButtonStyle.primary,
                        custom_id=f"ticket_{category.lower().replace(' ', '_')}"
                    )
                    # We'll need to set the callback in the cog
                    button.callback = lambda i, cat=category: tickets_cog.create_ticket(i, cat)
                    view.add_item(button)

                panel_message = await channel.send(embed=embed, view=view)
                
                # Store panel message
                tickets_cog.panel_messages[str(guild_id)] = {
                    'channel_id': channel.id,
                    'message_id': panel_message.id,
                    'created_by': 'dashboard',
                    'created_at': datetime.now().isoformat()
                }
                tickets_cog.save_data(tickets_cog.panel_messages_file, tickets_cog.panel_messages)
                
                return True
            except Exception as e:
                print(f"Error creating panel: {e}")
                return False
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(create_panel())
        loop.close()
        
        if success:
            return {"success": True}
        else:
            return {"error": "Failed to create panel"}, 500
            
    except Exception as e:
        print(f"Create ticket panel error: {e}")
        return {"error": "Failed to create ticket panel"}, 500

@app.route("/api/warnings/<user_id>")
def api_get_warnings(user_id):
    """Get warnings for a user"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        guild_id = request.args.get('server_id')
        if not guild_id:
            return {"error": "Server ID required"}, 400
        
        # Get warnings from moderation cog
        moderation_cog = bot.get_cog('Moderation')
        if moderation_cog:
            warnings = moderation_cog.get_user_warnings(user_id, guild_id)
            formatted_warnings = []
            for warning in warnings:
                formatted_warnings.append({
                    'reason': warning['reason'],
                    'timestamp': warning['timestamp'],
                    'moderator': warning.get('moderator', 'Unknown')
                })
            return {"success": True, "warnings": formatted_warnings}
        else:
            return {"success": True, "warnings": []}
    except Exception as e:
        print(f"Get warnings error: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/warnings/clear/<user_id>", methods=["POST"])
def api_clear_warnings(user_id):
    """Clear warnings for a user"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        guild_id = request.args.get('server_id')
        if not guild_id:
            return {"error": "Server ID required"}, 400
        
        # Clear warnings using moderation cog
        moderation_cog = bot.get_cog('Moderation')
        if moderation_cog:
            moderation_cog.clear_warnings(user_id, guild_id)
            return {"success": True}
        else:
            return {"success": False, "error": "Moderation system not available"}
    except Exception as e:
        print(f"Clear warnings error: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/server/<guild_id>/warned_users")
def api_get_warned_users(guild_id):
    """Get all users with warnings in a guild"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        warnings_file = os.path.join("data", "warnings.json")
        warned_users = []
        
        if os.path.exists(warnings_file):
            with open(warnings_file, 'r') as f:
                warnings_data = json.load(f)
            
            guild = bot.get_guild(int(guild_id))
            
            for user_key, data in warnings_data.items():
                if data.get('guild_id') == str(guild_id) and data.get('warns'):
                    user_id = user_key.split('_')[1] if '_' in user_key else user_key
                    member = guild.get_member(int(user_id)) if guild else None
                    
                    warned_users.append({
                        'id': user_id,
                        'name': member.display_name if member else f"Unknown User ({user_id})",
                        'warning_count': len(data['warns'])
                    })
        
        return {"success": True, "warned_users": warned_users}
    except Exception as e:
        print(f"Get warned users error: {e}")
        return {"success": False, "error": str(e), "warned_users": []}

@app.route("/api/warnings/<user_id>")
def api_get_warns(user_id):
    """Get warnings for a user"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        guild_id = request.args.get('server_id')
        if not guild_id:
            return {"error": "Server ID required"}, 400
        
        warnings_file = os.path.join("data", "warnings.json")
        warnings = []
        
        if os.path.exists(warnings_file):
            with open(warnings_file, 'r') as f:
                warnings_data = json.load(f)
            
            user_key = f"{guild_id}_{user_id}"
            if user_key in warnings_data:
                warnings = warnings_data[user_key].get('warns', [])
        
        return {"success": True, "warnings": warnings}
    except Exception as e:
        print(f"Get warnings error: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/warnings/clear/<user_id>", methods=["POST"])
def api_clear_warns(user_id):
    """Clear warnings for a user"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        guild_id = request.args.get('server_id')
        if not guild_id:
            return {"error": "Server ID required"}, 400
        
        warnings_file = os.path.join("data", "warnings.json")
        
        if os.path.exists(warnings_file):
            with open(warnings_file, 'r') as f:
                warnings_data = json.load(f)
            
            user_key = f"{guild_id}_{user_id}"
            if user_key in warnings_data:
                warnings_data[user_key]['warns'] = []
                
                with open(warnings_file, 'w') as f:
                    json.dump(warnings_data, f, indent=4)
        
        return {"success": True}
    except Exception as e:
        print(f"Clear warnings error: {e}")
        return {"success": False, "error": str(e)}

@app.route("/api/server/<guild_id>/tickets")
def api_get_ticket(guild_id):
    """Get open tickets"""
    if "access_token" not in session:
        return {"error": "Unauthorized"}, 401
    
    try:
        tickets_file = os.path.join("data", "tickets.json")
        tickets = []
        
        if os.path.exists(tickets_file):
            with open(tickets_file, 'r') as f:
                tickets_data = json.load(f)
            
            if str(guild_id) in tickets_data:
                for category, category_tickets in tickets_data[str(guild_id)].items():
                    for ticket in category_tickets:
                        if not ticket.get('closed', False):
                            tickets.append(ticket)
        
        return {"success": True, "tickets": tickets}
    except Exception as e:
        print(f"Get tickets error: {e}")
        return {"success": False, "error": str(e)}

# ===================== Run Bot and Flask =====================
def run_bot():
    import asyncio
    import logging
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s:%(levelname)s:%(name)s: %(message)s'
    )
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("🤖 Loading cogs...")
    loop.run_until_complete(load_cogs())
    
    print("🚀 Starting bot...")
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"❌ Bot failed to start: {e}")

def run_flask():
    print("🌐 Starting Flask server...")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)

if __name__ == "__main__":
    # Start bot in separate thread
    Thread(target=run_bot, daemon=True).start()
    
    # Give bot time to start
    import time
    time.sleep(3)
    
    # Start Flask
    run_flask()