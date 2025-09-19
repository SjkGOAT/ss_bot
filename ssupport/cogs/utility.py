import discord
from discord.ext import commands
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger('SSupportBot.utility')

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

    def get_server_config(self, guild_id):
        """Get server-specific configuration"""
        config_path = os.path.join(self.data_dir, str(guild_id), "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "welcome_channel": None,
            "welcome_message": "Welcome {ping} to {server}! We now have {members} members.",
            "join_role": None,
            "blacklisted_words": [],
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

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle member join events"""
        try:
            if member.bot:
                return
                
            config = self.get_server_config(member.guild.id)
            
            # Auto-role assignment
            join_role_id = config.get('join_role')
            if join_role_id:
                role = member.guild.get_role(int(join_role_id))
                if role:
                    try:
                        await member.add_roles(role, reason="Auto-role on join")
                        logger.info(f"Added role {role.name} to {member} in {member.guild.name}")
                    except Exception as e:
                        logger.error(f"Failed to add role to {member}: {e}")
            
            # Welcome message
            welcome_channel_id = config.get('welcome_channel')
            welcome_message = config.get('welcome_message', "Welcome {ping} to the server!")
            
            if welcome_channel_id and welcome_message:
                channel = member.guild.get_channel(int(welcome_channel_id))
                if channel:
                    # Format the welcome message
                    formatted_message = welcome_message.format(
                        ping=member.mention,
                        user=member.display_name,
                        server=member.guild.name,
                        members=member.guild.member_count
                    )
                    
                    # Create welcome embed
                    embed = discord.Embed(
                        title="Welcome!",
                        description=formatted_message,
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"Member #{member.guild.member_count}")
                    
                    try:
                        await channel.send(embed=embed)
                        logger.info(f"Sent welcome message for {member} in {member.guild.name}")
                    except Exception as e:
                        logger.error(f"Failed to send welcome message: {e}")
                        
        except Exception as e:
            logger.error(f"Error in on_member_join: {e}")

    @commands.command()
    async def ping(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="Pong!",
            description=f"Bot latency: {latency}ms",
            color=discord.Color.green() if latency < 100 else discord.Color.orange() if latency < 300 else discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def help(self, ctx, *, command_name=None):
        """Show help information"""
        if command_name:
            # Show help for specific command
            command = self.bot.get_command(command_name)
            if command:
                embed = discord.Embed(
                    title=f"Help: {command.name}",
                    description=command.help or "No description available",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Usage",
                    value=f"`{ctx.prefix}{command.name} {command.signature}`",
                    inline=False
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("Command not found!")
            return

        # Show general help
        embed = discord.Embed(
            title="SSupport Bot Commands",
            description="Here are all available commands:",
            color=discord.Color.blue()
        )
        
        # Group commands by cog
        cogs = {
            'Utility': ['ping', 'help', 'serverinfo', 'userinfo'],
            'Moderation': ['warn', 'warnlist', 'clearwarns', 'kick', 'ban', 'unban', 'timeout', 'untimeout', 'purge'],
            'Tickets': ['ticketpanel', 'ticket', 'closeticket', 'adduser'],
            'Fun': ['roll', 'choose', 'ship', 'flip', 'rps', 'magic8ball', 'joke']
        }
        
        for cog_name, commands in cogs.items():
            command_list = []
            for cmd_name in commands:
                cmd = self.bot.get_command(cmd_name)
                if cmd:
                    command_list.append(f"`{cmd.name}`")
            
            if command_list:
                embed.add_field(
                    name=f"{cog_name} Commands",
                    value=" • ".join(command_list),
                    inline=False
                )
        
        embed.set_footer(text=f"Use {ctx.prefix}help <command> for detailed help on a specific command")
        await ctx.send(embed=embed)

    @commands.command()
    async def serverinfo(self, ctx):
        """Show server information"""
        guild = ctx.guild
        embed = discord.Embed(
            title=f"Server Info: {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, 'D'), inline=True)
        
        embed.add_field(name="Text Channels", value=len(guild.text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=len(guild.voice_channels), inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        
        embed.add_field(name="Verification Level", value=str(guild.verification_level).title(), inline=True)
        embed.add_field(name="Boost Level", value=guild.premium_tier, inline=True)
        embed.add_field(name="Boosts", value=guild.premium_subscription_count or 0, inline=True)
        
        embed.set_footer(text=f"Server ID: {guild.id}")
        
        await ctx.send(embed=embed)

    @commands.command()
    async def userinfo(self, ctx, member: discord.Member = None):
        """Show user information"""
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"User Info: {member.display_name}",
            color=member.color if member.color.value else discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        embed.add_field(name="Username", value=str(member), inline=True)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, 'D'), inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, 'D'), inline=True)
        
        if member.premium_since:
            embed.add_field(name="Boosting Since", value=discord.utils.format_dt(member.premium_since, 'D'), inline=True)
        
        # Show roles (excluding @everyone)
        roles = [role.mention for role in reversed(member.roles) if role != ctx.guild.default_role]
        if roles:
            embed.add_field(
                name=f"Roles ({len(roles)})",
                value=" ".join(roles) if len(" ".join(roles)) <= 1024 else f"{len(roles)} roles",
                inline=False
            )
        
        # Show key permissions
        perms = member.guild_permissions
        key_perms = []
        if perms.administrator:
            key_perms.append("Administrator")
        if perms.manage_guild:
            key_perms.append("Manage Server")
        if perms.manage_channels:
            key_perms.append("Manage Channels")
        if perms.manage_messages:
            key_perms.append("Manage Messages")
        if perms.kick_members:
            key_perms.append("Kick Members")
        if perms.ban_members:
            key_perms.append("Ban Members")
        
        if key_perms:
            embed.add_field(name="Key Permissions", value=", ".join(key_perms), inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def config(self, ctx, setting=None, *, value=None):
        """Configure server settings"""
        if not setting:
            config = self.get_server_config(ctx.guild.id)
            embed = discord.Embed(
                title=f"Server Configuration: {ctx.guild.name}",
                color=discord.Color.blue()
            )
            
            welcome_channel = ctx.guild.get_channel(int(config.get('welcome_channel'))) if config.get('welcome_channel') else None
            join_role = ctx.guild.get_role(int(config.get('join_role'))) if config.get('join_role') else None
            
            embed.add_field(
                name="Welcome Channel",
                value=welcome_channel.mention if welcome_channel else "Not set",
                inline=False
            )
            embed.add_field(
                name="Welcome Message",
                value=config.get('welcome_message', 'Not set'),
                inline=False
            )
            embed.add_field(
                name="Join Role",
                value=join_role.mention if join_role else "Not set",
                inline=False
            )
            embed.add_field(
                name="Blacklisted Words",
                value=str(len(config.get('blacklisted_words', []))) + " words",
                inline=False
            )
            
            embed.set_footer(text="Use the web dashboard for easier configuration!")
            await ctx.send(embed=embed)
            return
        
        await ctx.send("Use the web dashboard to configure settings more easily!")

async def setup(bot):
    await bot.add_cog(Utility(bot))