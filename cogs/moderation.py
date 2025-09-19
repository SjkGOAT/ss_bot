import discord
from discord.ext import commands, tasks
from collections import defaultdict
import re
import json
import os
import time
import datetime
import logging
import asyncio

logger = logging.getLogger('SSupportBot.moderation')

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Load all data
        self.warnings_data = self.load_data("warnings.json", {})
        self.config_data = self.load_data("config.json", {
            "warning_system_enabled": True, 
            "spam_protection_enabled": True,
            "auto_mod_enabled": True
        })
        
        # Spam protection
        self.message_history = defaultdict(list)
        self.spam_cooldown = defaultdict(float)
        self.spam_threshold = 5
        self.spam_timeframe = 5
        self.spam_warn_cooldown = 30
        
        # Blacklist violation tracking (NEW)
        self.blacklist_violations = defaultdict(int)
        self.blacklist_threshold = 3  # Number of violations before warning
        
        # Start background tasks
        self.check_temp_bans.start()
        self.reset_warnings_weekly.start()
        self.cleanup_message_history.start()

    def load_data(self, filename, default):
        """Load JSON data from file"""
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            with open(path, 'w') as f:
                json.dump(default, f, indent=4)
            return default
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Error loading {filename}, using default")
            return default

    def save_data(self, filename, data):
        """Save JSON data to file"""
        path = os.path.join(self.data_dir, filename)
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")

    def get_server_config(self, guild_id):
        """Get server-specific configuration"""
        config_path = os.path.join(self.data_dir, f"{guild_id}", "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "blacklisted_words": [],
            "warning_system_enabled": True,
            "spam_protection_enabled": True,
            "auto_mod_enabled": True,
            "auto_ban_threshold": 5,
            "temp_ban_duration": 7,
            "welcome_channel": None,
            "welcome_message": "Welcome {ping} to {server_name}! We now have {members} members.",
            "join_role": None,
            "ticket_categories": ["Support", "Bug Report", "Feature Request", "Other"],
            "ticket_message": "Click a button below to create a ticket!"
        }

    def save_server_config(self, guild_id, config):
        """Save server-specific configuration"""
        guild_dir = os.path.join(self.data_dir, str(guild_id))
        os.makedirs(guild_dir, exist_ok=True)
        config_path = os.path.join(guild_dir, "config.json")
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving server config for {guild_id}: {e}")

    def get_user_warnings(self, user_id, guild_id=None):
        """Get warnings for a specific user"""
        user_key = f"{guild_id}_{user_id}" if guild_id else str(user_id)
        return self.warnings_data.get(user_key, {}).get('warns', [])

    def add_warning(self, user_id, guild_id, reason, moderator):
        """Add a warning to a user"""
        user_key = f"{guild_id}_{user_id}"
        if user_key not in self.warnings_data:
            self.warnings_data[user_key] = {'warns': [], 'guild_id': guild_id}
        
        warning = {
            'reason': reason,
            'timestamp': time.time(),
            'moderator': moderator,
            'guild_id': guild_id
        }
        
        self.warnings_data[user_key]['warns'].append(warning)
        self.save_data("warnings.json", self.warnings_data)
        return len(self.warnings_data[user_key]['warns'])

    def clear_warnings(self, user_id, guild_id):
        """Clear all warnings for a user"""
        user_key = f"{guild_id}_{user_id}"
        if user_key in self.warnings_data:
            self.warnings_data[user_key]['warns'] = []
            self.save_data("warnings.json", self.warnings_data)

    def get_all_warned_users(self, guild_id):
        """Get all users with warnings in a guild"""
        warned_users = []
        for user_key, data in self.warnings_data.items():
            if data.get('guild_id') == str(guild_id) and data.get('warns'):
                user_id = user_key.split('_')[1]
                warned_users.append({
                    'id': user_id,
                    'warning_count': len(data['warns'])
                })
        return warned_users

    # ================== EVENT LISTENERS ================== #

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle message filtering and spam detection"""
        if message.author.bot or not message.guild:
            return

        guild_config = self.get_server_config(message.guild.id)
        
        # Blacklist word filtering
        if guild_config.get('auto_mod_enabled', True):
            await self.check_blacklisted_words(message, guild_config)
        
        # Spam detection
        if guild_config.get('spam_protection_enabled', True):
            await self.check_spam(message, guild_config)

    async def check_blacklisted_words(self, message, guild_config):
        """Check for blacklisted words and take action after 3 violations"""
        blacklisted_words = guild_config.get('blacklisted_words', [])
        if not blacklisted_words:
            return

        content_lower = message.content.lower()
        violation_found = False
        
        for word in blacklisted_words:
            pattern = r'\b' + re.escape(word.lower()) + r'\b'
            if re.search(pattern, content_lower):
                violation_found = True
                
                try:
                    await message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logger.error(f"Error deleting message: {e}")
                
                # Track violations
                user_key = f"{message.guild.id}_{message.author.id}"
                self.blacklist_violations[user_key] += 1
                
                violations = self.blacklist_violations[user_key]
                
                if violations >= self.blacklist_threshold:
                    # Reset counter and warn
                    self.blacklist_violations[user_key] = 0
                    
                    if guild_config.get('warning_system_enabled', True):
                        warning_count = self.add_warning(
                            message.author.id,
                            message.guild.id,
                            f"Repeated use of blacklisted words (3 violations)",
                            "AutoMod"
                        )
                        
                        embed = discord.Embed(
                            title="Warning Issued",
                            description=f"{message.author.mention}, you have been warned for repeatedly using blacklisted words.",
                            color=discord.Color.red()
                        )
                        embed.add_field(
                            name="Total Warnings",
                            value=f"You now have {warning_count} warning(s).",
                            inline=False
                        )
                        
                        try:
                            await message.channel.send(embed=embed, delete_after=10)
                        except:
                            pass
                        
                        # Check for auto-ban
                        await self.check_auto_ban(message.author, message.guild, warning_count, guild_config)
                else:
                    # Just notify about the violation
                    embed = discord.Embed(
                        title="Message Deleted",
                        description=f"{message.author.mention}, your message contained a blacklisted word.",
                        color=discord.Color.orange()
                    )
                    embed.add_field(
                        name="Violations",
                        value=f"{violations}/{self.blacklist_threshold} before warning",
                        inline=False
                    )
                    
                    try:
                        await message.channel.send(embed=embed, delete_after=5)
                    except:
                        pass
                
                logger.info(f"Deleted message from {message.author} in {message.guild.name}: blacklisted word '{word}' (violation {violations})")
                break

    async def check_spam(self, message, guild_config):
        """Check for spam and take action"""
        user_id = message.author.id
        current_time = time.time()
        
        # Clean old messages
        self.message_history[user_id] = [
            msg_time for msg_time in self.message_history[user_id]
            if current_time - msg_time < self.spam_timeframe
        ]
        
        # Add current message
        self.message_history[user_id].append(current_time)
        
        # Check if spam threshold exceeded
        if len(self.message_history[user_id]) >= self.spam_threshold:
            # Check cooldown
            if current_time - self.spam_cooldown[user_id] >= self.spam_warn_cooldown:
                self.spam_cooldown[user_id] = current_time
                
                # Auto-warn for spam
                if guild_config.get('warning_system_enabled', True):
                    warning_count = self.add_warning(
                        message.author.id,
                        message.guild.id,
                        "Spam detection",
                        "AutoMod"
                    )
                    
                    embed = discord.Embed(
                        title="Spam Detected",
                        description=f"{message.author.mention}, please slow down your messages.",
                        color=discord.Color.red()
                    )
                    embed.add_field(
                        name="Warning",
                        value=f"You now have {warning_count} warning(s).",
                        inline=False
                    )
                    
                    try:
                        await message.channel.send(embed=embed, delete_after=10)
                    except:
                        pass
                    
                    # Check for auto-ban
                    await self.check_auto_ban(message.author, message.guild, warning_count, guild_config)
                
                logger.info(f"Spam warning issued to {message.author} in {message.guild.name}")
                
                # Clear message history after warning
                self.message_history[user_id].clear()

    async def check_auto_ban(self, member, guild, warning_count, guild_config):
        """Check if user should be auto-banned"""
        threshold = guild_config.get('auto_ban_threshold', 5)
        if warning_count >= threshold:
            duration_days = guild_config.get('temp_ban_duration', 7)
            unban_time = time.time() + duration_days * 24 * 60 * 60
            
            # Add temp ban data
            user_key = f"{guild.id}_{member.id}"
            if 'tempbans' not in self.warnings_data[user_key]:
                self.warnings_data[user_key]['tempbans'] = []
            
            self.warnings_data[user_key]['tempbans'].append({
                'unban_time': unban_time,
                'reason': f"Reached {threshold} warnings"
            })
            
            try:
                await guild.ban(member, reason=f"Auto-ban: Reached {threshold} warnings")
                
                # Clear warnings after ban
                self.warnings_data[user_key]['warns'] = []
                self.save_data("warnings.json", self.warnings_data)
                
                # Notify in channel
                embed = discord.Embed(
                    title="Auto-Ban Issued",
                    description=f"{member.mention} has been temporarily banned for {duration_days} days.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="Reason",
                    value=f"Reached {threshold} warnings",
                    inline=False
                )
                
                # Find a suitable channel to send notification
                channel = guild.system_channel or guild.text_channels[0] if guild.text_channels else None
                if channel:
                    try:
                        await channel.send(embed=embed)
                    except:
                        pass
                
                # Try to DM user
                try:
                    unban_date = datetime.datetime.fromtimestamp(unban_time).strftime('%Y-%m-%d %H:%M:%S UTC')
                    await member.send(f"You have been temporarily banned from {guild.name} until {unban_date} for reaching {threshold} warnings.")
                except:
                    pass
                
                logger.info(f"Auto-banned {member} from {guild.name} for {duration_days} days")
                
            except Exception as e:
                logger.error(f"Failed to auto-ban {member}: {e}")

    # ================== NEW COMMANDS ================== #
    
    @commands.command()
    async def dashboard(self, ctx):
        """Get the dashboard link for this server"""
        embed = discord.Embed(
            title="Server Dashboard",
            description=f"Manage your server settings with our web dashboard!",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Dashboard URL",
            value=f"[Click here to open dashboard](http://deka.wisp.uno:13526/server/{ctx.guild.id})",
            inline=False
        )
        embed.add_field(
            name="Features",
            value="• Configure welcome messages\n• Manage blacklisted words\n• Set up ticket systems\n• View warnings and moderation logs",
            inline=False
        )
        embed.set_footer(text="Login with Discord to access your server dashboard")
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def config(self, ctx):
        """Show current server configuration"""
        config = self.get_server_config(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"Server Configuration: {ctx.guild.name}",
            color=discord.Color.blue()
        )
        
        # Welcome settings
        welcome_channel = ctx.guild.get_channel(int(config.get('welcome_channel'))) if config.get('welcome_channel') else None
        join_role = ctx.guild.get_role(int(config.get('join_role'))) if config.get('join_role') else None
        
        embed.add_field(
            name="Welcome Settings",
            value=f"**Channel:** {welcome_channel.mention if welcome_channel else 'Not set'}\n"
                  f"**Message:** {config.get('welcome_message', 'Not set')[:50]}{'...' if len(config.get('welcome_message', '')) > 50 else ''}\n"
                  f"**Join Role:** {join_role.mention if join_role else 'Not set'}",
            inline=False
        )
        
        # Moderation settings
        embed.add_field(
            name="Moderation Settings",
            value=f"**Warning System:** {'Enabled' if config.get('warning_system_enabled', True) else 'Disabled'}\n"
                  f"**Spam Protection:** {'Enabled' if config.get('spam_protection_enabled', True) else 'Disabled'}\n"
                  f"**Auto-Mod:** {'Enabled' if config.get('auto_mod_enabled', True) else 'Disabled'}\n"
                  f"**Blacklisted Words:** {len(config.get('blacklisted_words', []))} words\n"
                  f"**Auto-ban Threshold:** {config.get('auto_ban_threshold', 5)} warnings",
            inline=False
        )
        
        # Ticket settings
        embed.add_field(
            name="Ticket Settings",
            value=f"**Categories:** {', '.join(config.get('ticket_categories', ['Support']))}\n"
                  f"**Panel Message:** {config.get('ticket_message', 'Default message')[:50]}{'...' if len(config.get('ticket_message', '')) > 50 else ''}",
            inline=False
        )
        
        embed.set_footer(text="Use the web dashboard for easy configuration!")
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def warningsystem(self, ctx, state: str):
        """Enable or disable the warning system"""
        if state.lower() not in ['on', 'off', 'enable', 'disable']:
            await ctx.send("Usage: `ss!warningsystem on/off`")
            return
        
        enabled = state.lower() in ['on', 'enable']
        config = self.get_server_config(ctx.guild.id)
        config['warning_system_enabled'] = enabled
        self.save_server_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="Warning System Updated",
            description=f"Warning system has been **{'enabled' if enabled else 'disabled'}**",
            color=discord.Color.green() if enabled else discord.Color.red()
        )
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def spamprevention(self, ctx, state: str):
        """Enable or disable spam prevention"""
        if state.lower() not in ['on', 'off', 'enable', 'disable']:
            await ctx.send("Usage: `ss!spamprevention on/off`")
            return
        
        enabled = state.lower() in ['on', 'enable']
        config = self.get_server_config(ctx.guild.id)
        config['spam_protection_enabled'] = enabled
        self.save_server_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            title="Spam Prevention Updated",
            description=f"Spam prevention has been **{'enabled' if enabled else 'disabled'}**",
            color=discord.Color.green() if enabled else discord.Color.red()
        )
        await ctx.send(embed=embed)

    # ================== BACKGROUND TASKS ================== #

    @tasks.loop(hours=1)
    async def check_temp_bans(self):
        """Check and process expired temp bans"""
        current_time = time.time()
        for user_key, data in list(self.warnings_data.items()):
            if 'tempbans' not in data:
                continue
                
            guild_id = data.get('guild_id')
            if not guild_id:
                continue
                
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
                
            user_id = user_key.split('_')[1]
            
            for tempban in data['tempbans'][:]:
                if tempban['unban_time'] <= current_time:
                    try:
                        await guild.unban(discord.Object(id=int(user_id)), reason="Temp ban expired")
                        data['tempbans'].remove(tempban)
                        
                        # Clean up empty tempbans list
                        if not data['tempbans']:
                            del data['tempbans']
                        
                        # Try to notify user
                        try:
                            user = await self.bot.fetch_user(int(user_id))
                            await user.send(f"You have been unbanned from {guild.name}. You can rejoin the server now.")
                        except:
                            pass
                            
                        logger.info(f"Auto-unbanned user {user_id} from {guild.name}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to unban {user_id} from {guild.name}: {e}")
                        
        self.save_data("warnings.json", self.warnings_data)

    @tasks.loop(hours=24)
    async def reset_warnings_weekly(self):
        """Reset warnings weekly (Sunday)"""
        if datetime.datetime.now().weekday() == 6:  # Sunday
            reset_count = 0
            for user_key in list(self.warnings_data.keys()):
                if 'warns' in self.warnings_data[user_key] and self.warnings_data[user_key]['warns']:
                    self.warnings_data[user_key]['warns'] = []
                    reset_count += 1
                    
            if reset_count > 0:
                self.save_data("warnings.json", self.warnings_data)
                logger.info(f"Weekly warning reset completed: {reset_count} users")

    @tasks.loop(minutes=30)
    async def cleanup_message_history(self):
        """Clean up old message history data"""
        current_time = time.time()
        for user_id in list(self.message_history.keys()):
            self.message_history[user_id] = [
                msg_time for msg_time in self.message_history[user_id]
                if current_time - msg_time < self.spam_timeframe * 2
            ]
            if not self.message_history[user_id]:
                del self.message_history[user_id]
        
        # Also clean up blacklist violations after 1 hour
        for key in list(self.blacklist_violations.keys()):
            # Reset violations after some time of no violations
            # This is a simple cleanup - you could make it more sophisticated
            if len(self.message_history.get(key.split('_')[1], [])) == 0:
                self.blacklist_violations[key] = max(0, self.blacklist_violations[key] - 1)
                if self.blacklist_violations[key] == 0:
                    del self.blacklist_violations[key]

    # ================== EXISTING COMMANDS ================== #

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Warn a user"""
        if member.bot:
            await ctx.send("Cannot warn bots.")
            return
            
        if member == ctx.author:
            await ctx.send("You cannot warn yourself.")
            return
            
        guild_config = self.get_server_config(ctx.guild.id)
        if not guild_config.get('warning_system_enabled', True):
            await ctx.send("Warning system is disabled in this server.")
            return

        warning_count = self.add_warning(member.id, ctx.guild.id, reason, ctx.author.name)
        
        embed = discord.Embed(
            title="Warning Issued",
            color=discord.Color.orange()
        )
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Total Warnings", value=str(warning_count), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        
        # Check for auto-ban
        await self.check_auto_ban(member, ctx.guild, warning_count, guild_config)
        
        logger.info(f"{ctx.author} warned {member} in {ctx.guild.name}: {reason}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warnlist(self, ctx, member: discord.Member):
        """List warnings for a user"""
        warnings = self.get_user_warnings(member.id, ctx.guild.id)
        
        if not warnings:
            await ctx.send(f"{member.mention} has no warnings.")
            return
            
        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            color=discord.Color.orange()
        )
        
        for i, warning in enumerate(warnings, 1):
            timestamp = datetime.datetime.fromtimestamp(warning['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
            embed.add_field(
                name=f"Warning #{i} - {timestamp}",
                value=f"**Reason:** {warning['reason']}\n**Moderator:** {warning.get('moderator', 'Unknown')}",
                inline=False
            )
            
        embed.set_footer(text=f"Total warnings: {len(warnings)}")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clearwarns(self, ctx, member: discord.Member):
        """Clear all warnings for a user"""
        warnings = self.get_user_warnings(member.id, ctx.guild.id)
        
        if not warnings:
            await ctx.send(f"{member.mention} has no warnings to clear.")
            return
            
        self.clear_warnings(member.id, ctx.guild.id)
        
        embed = discord.Embed(
            title="Warnings Cleared",
            description=f"Cleared {len(warnings)} warning(s) for {member.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        logger.info(f"{ctx.author} cleared {len(warnings)} warnings for {member} in {ctx.guild.name}")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Kick a member"""
        if member == ctx.author:
            await ctx.send("You cannot kick yourself.")
            return
            
        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot kick someone with a higher or equal role.")
            return

        try:
            await member.kick(reason=f"Kicked by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Member Kicked",
                color=discord.Color.red()
            )
            embed.add_field(name="User", value=str(member), inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} kicked {member} from {ctx.guild.name}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to kick {member}: {e}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Ban a member"""
        if member == ctx.author:
            await ctx.send("You cannot ban yourself.")
            return
            
        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot ban someone with a higher or equal role.")
            return

        try:
            await member.ban(reason=f"Banned by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Member Banned",
                color=discord.Color.red()
            )
            embed.add_field(name="User", value=str(member), inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} banned {member} from {ctx.guild.name}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to ban {member}: {e}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason="No reason provided"):
        """Unban a user by ID"""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"Unbanned by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="User Unbanned",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=str(user), inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} unbanned {user} in {ctx.guild.name}: {reason}")
            
        except discord.NotFound:
            await ctx.send("User not found or not banned.")
        except Exception as e:
            await ctx.send(f"Failed to unban user: {e}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason="No reason provided"):
        """Timeout a member (e.g., 10m, 1h, 1d)"""
        if member == ctx.author:
            await ctx.send("You cannot timeout yourself.")
            return
            
        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot timeout someone with a higher or equal role.")
            return

        # Parse duration
        time_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        duration_seconds = 0
        
        try:
            if duration[-1].lower() in time_units:
                duration_seconds = int(duration[:-1]) * time_units[duration[-1].lower()]
            else:
                duration_seconds = int(duration) * 60  # Default to minutes
                
            if duration_seconds > 2419200:  # Discord's 28-day limit
                await ctx.send("Timeout duration cannot exceed 28 days.")
                return
                
        except ValueError:
            await ctx.send("Invalid duration format. Use format like: 10m, 1h, 2d")
            return

        try:
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            await member.timeout(until, reason=f"Timed out by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Member Timed Out",
                color=discord.Color.orange()
            )
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Duration", value=duration, inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Until", value=until.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} timed out {member} in {ctx.guild.name} for {duration}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to timeout {member}: {e}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Remove timeout from a member"""
        try:
            await member.timeout(None, reason=f"Timeout removed by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Timeout Removed",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} removed timeout from {member} in {ctx.guild.name}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to remove timeout from {member}: {e}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        """Delete multiple messages"""
        if amount < 1 or amount > 100:
            await ctx.send("Amount must be between 1 and 100.")
            return
            
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)  # +1 for the command message
            
            embed = discord.Embed(
                title="Messages Purged",
                description=f"Deleted {len(deleted) - 1} messages",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Purged by {ctx.author}")
            
            msg = await ctx.send(embed=embed)
            await msg.delete(delay=5)
            
            logger.info(f"{ctx.author} purged {len(deleted) - 1} messages in {ctx.guild.name}")
            
        except Exception as e:
            await ctx.send(f"Failed to purge messages: {e}")

    # ================== DASHBOARD INTEGRATION ================== #

    def get_dashboard_data(self, guild_id):
        """Get moderation data for dashboard"""
        return {
            'warned_users': self.get_all_warned_users(guild_id),
            'config': self.get_server_config(guild_id)
        }

    def update_blacklist(self, guild_id, blacklisted_words):
        """Update blacklisted words for a guild"""
        config = self.get_server_config(guild_id)
        config['blacklisted_words'] = blacklisted_words
        self.save_server_config(guild_id, config)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
    
import discord
from discord.ext import commands, tasks
from collections import defaultdict
import re
import json
import os
import time
import datetime
import logging
import asyncio

logger = logging.getLogger('SSupportBot.moderation')

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Load all data
        self.warnings_data = self.load_data("warnings.json", {})
        self.config_data = self.load_data("config.json", {
            "warning_system_enabled": True, 
            "spam_protection_enabled": True,
            "auto_mod_enabled": True
        })
        
        # Spam protection
        self.message_history = defaultdict(list)
        self.spam_cooldown = defaultdict(float)
        self.spam_threshold = 5
        self.spam_timeframe = 5
        self.spam_warn_cooldown = 30
        
        # Start background tasks
        self.check_temp_bans.start()
        self.reset_warnings_weekly.start()
        self.cleanup_message_history.start()

    def load_data(self, filename, default):
        """Load JSON data from file"""
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            with open(path, 'w') as f:
                json.dump(default, f, indent=4)
            return default
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Error loading {filename}, using default")
            return default

    def save_data(self, filename, data):
        """Save JSON data to file"""
        path = os.path.join(self.data_dir, filename)
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")

    def get_server_config(self, guild_id):
        """Get server-specific configuration"""
        config_path = os.path.join(self.data_dir, f"{guild_id}", "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "blacklisted_words": [],
            "warning_system_enabled": True,
            "spam_protection_enabled": True,
            "auto_mod_enabled": True,
            "auto_ban_threshold": 5,
            "temp_ban_duration": 7
        }

    def save_server_config(self, guild_id, config):
        """Save server-specific configuration"""
        guild_dir = os.path.join(self.data_dir, str(guild_id))
        os.makedirs(guild_dir, exist_ok=True)
        config_path = os.path.join(guild_dir, "config.json")
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving server config for {guild_id}: {e}")

    def get_user_warnings(self, user_id, guild_id=None):
        """Get warnings for a specific user"""
        user_key = f"{guild_id}_{user_id}" if guild_id else str(user_id)
        return self.warnings_data.get(user_key, {}).get('warns', [])

    def add_warning(self, user_id, guild_id, reason, moderator):
        """Add a warning to a user"""
        user_key = f"{guild_id}_{user_id}"
        if user_key not in self.warnings_data:
            self.warnings_data[user_key] = {'warns': [], 'guild_id': guild_id}
        
        warning = {
            'reason': reason,
            'timestamp': time.time(),
            'moderator': moderator,
            'guild_id': guild_id
        }
        
        self.warnings_data[user_key]['warns'].append(warning)
        self.save_data("warnings.json", self.warnings_data)
        return len(self.warnings_data[user_key]['warns'])

    def clear_warnings(self, user_id, guild_id):
        """Clear all warnings for a user"""
        user_key = f"{guild_id}_{user_id}"
        if user_key in self.warnings_data:
            self.warnings_data[user_key]['warns'] = []
            self.save_data("warnings.json", self.warnings_data)

    def get_all_warned_users(self, guild_id):
        """Get all users with warnings in a guild"""
        warned_users = []
        for user_key, data in self.warnings_data.items():
            if data.get('guild_id') == str(guild_id) and data.get('warns'):
                user_id = user_key.split('_')[1]
                warned_users.append({
                    'id': user_id,
                    'warning_count': len(data['warns'])
                })
        return warned_users

    # ================== EVENT LISTENERS ================== #

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle message filtering and spam detection"""
        if message.author.bot or not message.guild:
            return

        guild_config = self.get_server_config(message.guild.id)
        
        # Blacklist word filtering
        if guild_config.get('auto_mod_enabled', True):
            await self.check_blacklisted_words(message, guild_config)
        
        # Spam detection
        if guild_config.get('spam_protection_enabled', True):
            await self.check_spam(message, guild_config)

    async def check_blacklisted_words(self, message, guild_config):
        """Check for blacklisted words and take action"""
        blacklisted_words = guild_config.get('blacklisted_words', [])
        if not blacklisted_words:
            return

        content_lower = message.content.lower()
        for word in blacklisted_words:
            pattern = r'\b' + re.escape(word.lower()) + r'\b'
            if re.search(pattern, content_lower):
                try:
                    await message.delete()
                    
                    # Auto-warn for blacklisted words
                    if guild_config.get('warning_system_enabled', True):
                        warning_count = self.add_warning(
                            message.author.id,
                            message.guild.id,
                            f"Used blacklisted word: {word}",
                            "AutoMod"
                        )
                        
                        # Send warning notification
                        embed = discord.Embed(
                            title="Message Deleted",
                            description=f"{message.author.mention}, your message contained a blacklisted word.",
                            color=discord.Color.orange()
                        )
                        embed.add_field(
                            name="Warning",
                            value=f"You now have {warning_count} warning(s).",
                            inline=False
                        )
                        
                        try:
                            await message.channel.send(embed=embed, delete_after=10)
                        except:
                            pass
                        
                        # Check for auto-ban
                        await self.check_auto_ban(message.author, message.guild, warning_count, guild_config)
                    
                    logger.info(f"Deleted message from {message.author} in {message.guild.name}: blacklisted word '{word}'")
                except discord.NotFound:
                    pass
                except Exception as e:
                    logger.error(f"Error deleting message: {e}")
                break

    async def check_spam(self, message, guild_config):
        """Check for spam and take action"""
        user_id = message.author.id
        current_time = time.time()
        
        # Clean old messages
        self.message_history[user_id] = [
            msg_time for msg_time in self.message_history[user_id]
            if current_time - msg_time < self.spam_timeframe
        ]
        
        # Add current message
        self.message_history[user_id].append(current_time)
        
        # Check if spam threshold exceeded
        if len(self.message_history[user_id]) >= self.spam_threshold:
            # Check cooldown
            if current_time - self.spam_cooldown[user_id] >= self.spam_warn_cooldown:
                self.spam_cooldown[user_id] = current_time
                
                # Auto-warn for spam
                if guild_config.get('warning_system_enabled', True):
                    warning_count = self.add_warning(
                        message.author.id,
                        message.guild.id,
                        "Spam detection",
                        "AutoMod"
                    )
                    
                    embed = discord.Embed(
                        title="Spam Detected",
                        description=f"{message.author.mention}, please slow down your messages.",
                        color=discord.Color.red()
                    )
                    embed.add_field(
                        name="Warning",
                        value=f"You now have {warning_count} warning(s).",
                        inline=False
                    )
                    
                    try:
                        await message.channel.send(embed=embed, delete_after=10)
                    except:
                        pass
                    
                    # Check for auto-ban
                    await self.check_auto_ban(message.author, message.guild, warning_count, guild_config)
                
                logger.info(f"Spam warning issued to {message.author} in {message.guild.name}")
                
                # Clear message history after warning
                self.message_history[user_id].clear()

    async def check_auto_ban(self, member, guild, warning_count, guild_config):
        """Check if user should be auto-banned"""
        threshold = guild_config.get('auto_ban_threshold', 5)
        if warning_count >= threshold:
            duration_days = guild_config.get('temp_ban_duration', 7)
            unban_time = time.time() + duration_days * 24 * 60 * 60
            
            # Add temp ban data
            user_key = f"{guild.id}_{member.id}"
            if 'tempbans' not in self.warnings_data[user_key]:
                self.warnings_data[user_key]['tempbans'] = []
            
            self.warnings_data[user_key]['tempbans'].append({
                'unban_time': unban_time,
                'reason': f"Reached {threshold} warnings"
            })
            
            try:
                await guild.ban(member, reason=f"Auto-ban: Reached {threshold} warnings")
                
                # Clear warnings after ban
                self.warnings_data[user_key]['warns'] = []
                self.save_data("warnings.json", self.warnings_data)
                
                # Notify in channel
                embed = discord.Embed(
                    title="Auto-Ban Issued",
                    description=f"{member.mention} has been temporarily banned for {duration_days} days.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="Reason",
                    value=f"Reached {threshold} warnings",
                    inline=False
                )
                
                # Find a suitable channel to send notification
                channel = guild.system_channel or guild.text_channels[0] if guild.text_channels else None
                if channel:
                    try:
                        await channel.send(embed=embed)
                    except:
                        pass
                
                # Try to DM user
                try:
                    unban_date = datetime.datetime.fromtimestamp(unban_time).strftime('%Y-%m-%d %H:%M:%S UTC')
                    await member.send(f"You have been temporarily banned from {guild.name} until {unban_date} for reaching {threshold} warnings.")
                except:
                    pass
                
                logger.info(f"Auto-banned {member} from {guild.name} for {duration_days} days")
                
            except Exception as e:
                logger.error(f"Failed to auto-ban {member}: {e}")

    # ================== BACKGROUND TASKS ================== #

    @tasks.loop(hours=1)
    async def check_temp_bans(self):
        """Check and process expired temp bans"""
        current_time = time.time()
        for user_key, data in list(self.warnings_data.items()):
            if 'tempbans' not in data:
                continue
                
            guild_id = data.get('guild_id')
            if not guild_id:
                continue
                
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
                
            user_id = user_key.split('_')[1]
            
            for tempban in data['tempbans'][:]:
                if tempban['unban_time'] <= current_time:
                    try:
                        await guild.unban(discord.Object(id=int(user_id)), reason="Temp ban expired")
                        data['tempbans'].remove(tempban)
                        
                        # Clean up empty tempbans list
                        if not data['tempbans']:
                            del data['tempbans']
                        
                        # Try to notify user
                        try:
                            user = await self.bot.fetch_user(int(user_id))
                            await user.send(f"You have been unbanned from {guild.name}. You can rejoin the server now.")
                        except:
                            pass
                            
                        logger.info(f"Auto-unbanned user {user_id} from {guild.name}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to unban {user_id} from {guild.name}: {e}")
                        
        self.save_data("warnings.json", self.warnings_data)

    @tasks.loop(hours=24)
    async def reset_warnings_weekly(self):
        """Reset warnings weekly (Sunday)"""
        if datetime.datetime.now().weekday() == 6:  # Sunday
            reset_count = 0
            for user_key in list(self.warnings_data.keys()):
                if 'warns' in self.warnings_data[user_key] and self.warnings_data[user_key]['warns']:
                    self.warnings_data[user_key]['warns'] = []
                    reset_count += 1
                    
            if reset_count > 0:
                self.save_data("warnings.json", self.warnings_data)
                logger.info(f"Weekly warning reset completed: {reset_count} users")

    @tasks.loop(minutes=30)
    async def cleanup_message_history(self):
        """Clean up old message history data"""
        current_time = time.time()
        for user_id in list(self.message_history.keys()):
            self.message_history[user_id] = [
                msg_time for msg_time in self.message_history[user_id]
                if current_time - msg_time < self.spam_timeframe * 2
            ]
            if not self.message_history[user_id]:
                del self.message_history[user_id]

    # ================== COMMANDS ================== #

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Warn a user"""
        if member.bot:
            await ctx.send("Cannot warn bots.")
            return
            
        if member == ctx.author:
            await ctx.send("You cannot warn yourself.")
            return
            
        guild_config = self.get_server_config(ctx.guild.id)
        if not guild_config.get('warning_system_enabled', True):
            await ctx.send("Warning system is disabled in this server.")
            return

        warning_count = self.add_warning(member.id, ctx.guild.id, reason, ctx.author.name)
        
        embed = discord.Embed(
            title="Warning Issued",
            color=discord.Color.orange()
        )
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Total Warnings", value=str(warning_count), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        
        # Check for auto-ban
        await self.check_auto_ban(member, ctx.guild, warning_count, guild_config)
        
        logger.info(f"{ctx.author} warned {member} in {ctx.guild.name}: {reason}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warnlist(self, ctx, member: discord.Member):
        """List warnings for a user"""
        warnings = self.get_user_warnings(member.id, ctx.guild.id)
        
        if not warnings:
            await ctx.send(f"{member.mention} has no warnings.")
            return
            
        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            color=discord.Color.orange()
        )
        
        for i, warning in enumerate(warnings, 1):
            timestamp = datetime.datetime.fromtimestamp(warning['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
            embed.add_field(
                name=f"Warning #{i} - {timestamp}",
                value=f"**Reason:** {warning['reason']}\n**Moderator:** {warning.get('moderator', 'Unknown')}",
                inline=False
            )
            
        embed.set_footer(text=f"Total warnings: {len(warnings)}")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clearwarns(self, ctx, member: discord.Member):
        """Clear all warnings for a user"""
        warnings = self.get_user_warnings(member.id, ctx.guild.id)
        
        if not warnings:
            await ctx.send(f"{member.mention} has no warnings to clear.")
            return
            
        self.clear_warnings(member.id, ctx.guild.id)
        
        embed = discord.Embed(
            title="Warnings Cleared",
            description=f"Cleared {len(warnings)} warning(s) for {member.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        logger.info(f"{ctx.author} cleared {len(warnings)} warnings for {member} in {ctx.guild.name}")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Kick a member"""
        if member == ctx.author:
            await ctx.send("You cannot kick yourself.")
            return
            
        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot kick someone with a higher or equal role.")
            return

        try:
            await member.kick(reason=f"Kicked by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Member Kicked",
                color=discord.Color.red()
            )
            embed.add_field(name="User", value=str(member), inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} kicked {member} from {ctx.guild.name}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to kick {member}: {e}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Ban a member"""
        if member == ctx.author:
            await ctx.send("You cannot ban yourself.")
            return
            
        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot ban someone with a higher or equal role.")
            return

        try:
            await member.ban(reason=f"Banned by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Member Banned",
                color=discord.Color.red()
            )
            embed.add_field(name="User", value=str(member), inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} banned {member} from {ctx.guild.name}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to ban {member}: {e}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason="No reason provided"):
        """Unban a user by ID"""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"Unbanned by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="User Unbanned",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=str(user), inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} unbanned {user} in {ctx.guild.name}: {reason}")
            
        except discord.NotFound:
            await ctx.send("User not found or not banned.")
        except Exception as e:
            await ctx.send(f"Failed to unban user: {e}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason="No reason provided"):
        """Timeout a member (e.g., 10m, 1h, 1d)"""
        if member == ctx.author:
            await ctx.send("You cannot timeout yourself.")
            return
            
        if member.top_role >= ctx.author.top_role:
            await ctx.send("You cannot timeout someone with a higher or equal role.")
            return

        # Parse duration
        time_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        duration_seconds = 0
        
        try:
            if duration[-1].lower() in time_units:
                duration_seconds = int(duration[:-1]) * time_units[duration[-1].lower()]
            else:
                duration_seconds = int(duration) * 60  # Default to minutes
                
            if duration_seconds > 2419200:  # Discord's 28-day limit
                await ctx.send("Timeout duration cannot exceed 28 days.")
                return
                
        except ValueError:
            await ctx.send("Invalid duration format. Use format like: 10m, 1h, 2d")
            return

        try:
            until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            await member.timeout(until, reason=f"Timed out by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Member Timed Out",
                color=discord.Color.orange()
            )
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Duration", value=duration, inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Until", value=until.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} timed out {member} in {ctx.guild.name} for {duration}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to timeout {member}: {e}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Remove timeout from a member"""
        try:
            await member.timeout(None, reason=f"Timeout removed by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="Timeout Removed",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} removed timeout from {member} in {ctx.guild.name}: {reason}")
            
        except Exception as e:
            await ctx.send(f"Failed to remove timeout from {member}: {e}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        """Delete multiple messages"""
        if amount < 1 or amount > 100:
            await ctx.send("Amount must be between 1 and 100.")
            return
            
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)  # +1 for the command message
            
            embed = discord.Embed(
                title="Messages Purged",
                description=f"Deleted {len(deleted) - 1} messages",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Purged by {ctx.author}")
            
            msg = await ctx.send(embed=embed)
            await msg.delete(delay=5)
            
            logger.info(f"{ctx.author} purged {len(deleted) - 1} messages in {ctx.guild.name}")
            
        except Exception as e:
            await ctx.send(f"Failed to purge messages: {e}")

    # ================== DASHBOARD INTEGRATION ================== #

    def get_dashboard_data(self, guild_id):
        """Get moderation data for dashboard"""
        return {
            'warned_users': self.get_all_warned_users(guild_id),
            'config': self.get_server_config(guild_id)
        }

    def update_blacklist(self, guild_id, blacklisted_words):
        """Update blacklisted words for a guild"""
        config = self.get_server_config(guild_id)
        config['blacklisted_words'] = blacklisted_words
        self.save_server_config(guild_id, config)

async def setup(bot):
    await bot.add_cog(Moderation(bot))