import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import json
import os
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger('SSupportBot.tickets')

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = 'data'
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.tickets_file = os.path.join(self.data_dir, 'tickets.json')
        self.panel_messages_file = os.path.join(self.data_dir, 'panel_messages.json')
        
        self.tickets_data = self.load_data(self.tickets_file, {})
        self.panel_messages = self.load_data(self.panel_messages_file, {})

    def load_data(self, filepath, default):
        """Load JSON data from file"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error loading {filepath}: {e}")
        return default

    def save_data(self, filepath, data):
        """Save JSON data to file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving {filepath}: {e}")

    def get_server_config(self, guild_id):
        """Get server-specific configuration"""
        config_path = os.path.join(self.data_dir, str(guild_id), 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            'ticket_categories': ['Support', 'Bug Report', 'Feature Request', 'Other'],
            'ticket_message': 'Click a button below to create a ticket!',
            'support_role_id': None,
            'ticket_logs_channel': None,
            'auto_close_inactive': False,
            'inactive_hours': 24
        }

    def get_next_ticket_number(self, guild_id, category):
        """Get the next ticket number for a category"""
        guild_data = self.tickets_data.get(str(guild_id), {})
        category_tickets = guild_data.get(category, [])
        return len([t for t in category_tickets if not t.get('closed', False)]) + 1

    def create_ticket_data(self, guild_id, category, channel_id, creator_id):
        """Create and store ticket data"""
        guild_id = str(guild_id)
        
        if guild_id not in self.tickets_data:
            self.tickets_data[guild_id] = {}
        
        if category not in self.tickets_data[guild_id]:
            self.tickets_data[guild_id][category] = []
        
        ticket_number = self.get_next_ticket_number(guild_id, category)
        
        ticket_data = {
            'number': ticket_number,
            'channel_id': channel_id,
            'creator_id': creator_id,
            'category': category,
            'created_at': datetime.now().isoformat(),
            'status': 'open',
            'assigned_staff': [],
            'participants': [creator_id],
            'closed': False,
            'close_reason': None,
            'closed_by': None,
            'closed_at': None
        }
        
        self.tickets_data[guild_id][category].append(ticket_data)
        self.save_data(self.tickets_file, self.tickets_data)
        return ticket_data

    def close_ticket_data(self, guild_id, channel_id, closed_by, reason="No reason provided"):
        """Mark ticket as closed in data"""
        guild_id = str(guild_id)
        
        if guild_id in self.tickets_data:
            for category in self.tickets_data[guild_id]:
                for ticket in self.tickets_data[guild_id][category]:
                    if ticket['channel_id'] == channel_id and not ticket.get('closed', False):
                        ticket['closed'] = True
                        ticket['status'] = 'closed'
                        ticket['closed_by'] = closed_by
                        ticket['close_reason'] = reason
                        ticket['closed_at'] = datetime.now().isoformat()
                        self.save_data(self.tickets_file, self.tickets_data)
                        return ticket
        return None

    def get_open_tickets(self, guild_id):
        """Get all open tickets for a guild"""
        guild_id = str(guild_id)
        open_tickets = []
        
        if guild_id in self.tickets_data:
            for category in self.tickets_data[guild_id]:
                for ticket in self.tickets_data[guild_id][category]:
                    if not ticket.get('closed', False):
                        open_tickets.append(ticket)
        
        return open_tickets

    def get_ticket_by_channel(self, guild_id, channel_id):
        """Get ticket data by channel ID"""
        guild_id = str(guild_id)
        
        if guild_id in self.tickets_data:
            for category in self.tickets_data[guild_id]:
                for ticket in self.tickets_data[guild_id][category]:
                    if ticket['channel_id'] == channel_id:
                        return ticket
        return None

    class TicketCategorySelect(Select):
        def __init__(self, categories, cog):
            self.cog = cog
            options = []
            
            category_emojis = {
                'Support': '🎧',
                'Bug Report': '🐛', 
                'Feature Request': '💡',
                'General': '💬',
                'Technical': '⚙️',
                'Billing': '💳',
                'Other': '📩'
            }
            
            for category in categories:
                emoji = category_emojis.get(category, '🎫')
                options.append(discord.SelectOption(
                    label=category,
                    description=f"Create a {category.lower()} ticket",
                    emoji=emoji,
                    value=category
                ))
            
            super().__init__(
                placeholder="Select ticket category...",
                options=options,
                custom_id="ticket_category_select"
            )

        async def callback(self, interaction):
            await self.cog.create_ticket(interaction, self.values[0])

    class CloseTicketButton(Button):
        def __init__(self, cog):
            self.cog = cog
            super().__init__(
                label="Close Ticket",
                style=discord.ButtonStyle.danger,
                emoji="🔒",
                custom_id="close_ticket_button"
            )

        async def callback(self, interaction):
            await self.cog.close_ticket(interaction)

    class TicketControlView(View):
        def __init__(self, cog):
            super().__init__(timeout=None)
            self.cog = cog
            self.add_item(self.CloseTicketButton(cog))

        class CloseTicketButton(Button):
            def __init__(self, cog):
                self.cog = cog
                super().__init__(
                    label="Close Ticket",
                    style=discord.ButtonStyle.danger,
                    emoji="🔒"
                )

            async def callback(self, interaction):
                await self.cog.close_ticket(interaction)

    async def create_ticket(self, interaction, category):
        """Create a new ticket"""
        try:
            guild_id = interaction.guild.id
            creator = interaction.user
            
            # Check if user already has an open ticket
            open_tickets = self.get_open_tickets(guild_id)
            user_tickets = [t for t in open_tickets if t['creator_id'] == creator.id]
            
            if len(user_tickets) >= 3:  # Limit to 3 open tickets per user
                await interaction.response.send_message(
                    "You already have 3 open tickets. Please close some before creating new ones.",
                    ephemeral=True
                )
                return

            # Get or create category
            category_name = f"Tickets - {category}"
            category_channel = discord.utils.get(interaction.guild.categories, name=category_name)
            
            if not category_channel:
                try:
                    category_channel = await interaction.guild.create_category(
                        category_name,
                        reason=f"Created ticket category for {category}"
                    )
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "I don't have permission to create categories!",
                        ephemeral=True
                    )
                    return

            # Create ticket channel
            ticket_number = self.get_next_ticket_number(guild_id, category)
            channel_name = f"{category.lower().replace(' ', '-')}-{ticket_number:04d}"
            
            # Set up permissions
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(
                    read_messages=False,
                    send_messages=False
                ),
                creator: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True
                )
            }
            
            # Add support role if configured
            config = self.get_server_config(guild_id)
            support_role_id = config.get('support_role_id')
            if support_role_id:
                support_role = interaction.guild.get_role(support_role_id)
                if support_role:
                    overwrites[support_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        manage_messages=True,
                        attach_files=True,
                        embed_links=True,
                        read_message_history=True
                    )

            try:
                ticket_channel = await category_channel.create_text_channel(
                    channel_name,
                    overwrites=overwrites,
                    topic=f"{category} ticket created by {creator.display_name}",
                    reason=f"Ticket created by {creator}"
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "I don't have permission to create channels!",
                    ephemeral=True
                )
                return

            # Store ticket data
            ticket_data = self.create_ticket_data(
                guild_id,
                category,
                ticket_channel.id,
                creator.id
            )

            # Create ticket embed
            embed = discord.Embed(
                title=f"🎫 {category} Ticket #{ticket_number:04d}",
                description=f"Welcome {creator.mention}! Thank you for creating a ticket.\n\n"
                           f"**Category:** {category}\n"
                           f"**Created:** {discord.utils.format_dt(datetime.now())}\n\n"
                           f"Please describe your issue in detail. Support staff will be with you shortly!",
                color=0x00ff00
            )
            embed.set_footer(text=f"Ticket ID: {ticket_data['number']} | Created by {creator.display_name}")
            embed.set_thumbnail(url=creator.display_avatar.url)

            # Create control view
            view = View(timeout=None)
            view.add_item(self.CloseTicketButton(self))
            
            # Send initial message
            await ticket_channel.send(
                content=f"{creator.mention}" + (f" <@&{support_role_id}>" if support_role_id else ""),
                embed=embed,
                view=view
            )

            # Log ticket creation
            logs_channel_id = config.get('ticket_logs_channel')
            if logs_channel_id:
                logs_channel = interaction.guild.get_channel(logs_channel_id)
                if logs_channel:
                    log_embed = discord.Embed(
                        title="📝 Ticket Created",
                        color=0x00ff00,
                        timestamp=datetime.now()
                    )
                    log_embed.add_field(name="User", value=f"{creator.mention} ({creator})", inline=True)
                    log_embed.add_field(name="Category", value=category, inline=True)
                    log_embed.add_field(name="Channel", value=ticket_channel.mention, inline=True)
                    log_embed.add_field(name="Ticket ID", value=f"#{ticket_number:04d}", inline=True)
                    
                    try:
                        await logs_channel.send(embed=log_embed)
                    except:
                        pass

            await interaction.response.send_message(
                f"✅ Ticket created! Please check {ticket_channel.mention}",
                ephemeral=True
            )
            
            logger.info(f"Ticket #{ticket_number:04d} created by {creator} in {interaction.guild.name} - {category}")

        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating your ticket. Please try again or contact an administrator.",
                ephemeral=True
            )

    async def close_ticket(self, interaction):
        """Close a ticket"""
        try:
            ticket_data = self.get_ticket_by_channel(interaction.guild.id, interaction.channel.id)
            
            if not ticket_data:
                await interaction.response.send_message(
                    "❌ This doesn't appear to be a valid ticket channel!",
                    ephemeral=True
                )
                return

            if ticket_data.get('closed', False):
                await interaction.response.send_message(
                    "❌ This ticket is already closed!",
                    ephemeral=True
                )
                return

            # Check permissions
            has_permission = (
                interaction.user.guild_permissions.manage_channels or
                interaction.user.id == ticket_data['creator_id'] or
                any(role.id == self.get_server_config(interaction.guild.id).get('support_role_id') 
                    for role in interaction.user.roles)
            )

            if not has_permission:
                await interaction.response.send_message(
                    "❌ You don't have permission to close this ticket!",
                    ephemeral=True
                )
                return

            # Close ticket in data
            self.close_ticket_data(
                interaction.guild.id,
                interaction.channel.id,
                interaction.user.id,
                "Closed via button"
            )

            # Create closure embed
            embed = discord.Embed(
                title="🔒 Ticket Closed",
                description=f"This ticket has been closed by {interaction.user.mention}.\n"
                           f"The channel will be deleted in 10 seconds.",
                color=0xff0000,
                timestamp=datetime.now()
            )
            
            await interaction.response.send_message(embed=embed)

            # Log ticket closure
            config = self.get_server_config(interaction.guild.id)
            logs_channel_id = config.get('ticket_logs_channel')
            if logs_channel_id:
                logs_channel = interaction.guild.get_channel(logs_channel_id)
                if logs_channel:
                    creator = interaction.guild.get_member(ticket_data['creator_id'])
                    log_embed = discord.Embed(
                        title="🔒 Ticket Closed",
                        color=0xff0000,
                        timestamp=datetime.now()
                    )
                    log_embed.add_field(
                        name="Creator", 
                        value=f"{creator.mention if creator else 'Unknown'} ({creator or 'Unknown'})", 
                        inline=True
                    )
                    log_embed.add_field(name="Closed by", value=f"{interaction.user.mention} ({interaction.user})", inline=True)
                    log_embed.add_field(name="Category", value=ticket_data['category'], inline=True)
                    log_embed.add_field(name="Ticket ID", value=f"#{ticket_data['number']:04d}", inline=True)
                    log_embed.add_field(name="Duration", value=self.format_duration(ticket_data['created_at']), inline=True)
                    
                    try:
                        await logs_channel.send(embed=log_embed)
                    except:
                        pass

            # Delete channel after delay
            await asyncio.sleep(10)
            try:
                await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
            except:
                pass
                
            logger.info(f"Ticket #{ticket_data['number']:04d} closed by {interaction.user} in {interaction.guild.name}")

        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while closing the ticket!",
                ephemeral=True
            )

    def format_duration(self, created_at):
        """Format ticket duration"""
        try:
            created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            duration = datetime.now() - created
            
            days = duration.days
            hours, remainder = divmod(duration.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        except:
            return "Unknown"

    @commands.Cog.listener()
    async def on_ready(self):
        """Restore ticket views on bot restart"""
        logger.info("Restoring ticket panel views...")
        
        for guild_id, panel_data in self.panel_messages.items():
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue

                channel = guild.get_channel(panel_data['channel_id'])
                if not channel:
                    continue

                try:
                    message = await channel.fetch_message(panel_data['message_id'])
                    config = self.get_server_config(guild_id)
                    categories = config.get('ticket_categories', ['Support'])
                    
                    # Recreate view
                    view = View(timeout=None)
                    if len(categories) <= 5:  # Use buttons for few categories
                        for category in categories:
                            button = Button(
                                label=category,
                                style=discord.ButtonStyle.primary,
                                custom_id=f"ticket_{category.lower().replace(' ', '_')}"
                            )
                            button.callback = lambda i, cat=category: self.create_ticket(i, cat)
                            view.add_item(button)
                    else:  # Use select menu for many categories
                        select = self.TicketCategorySelect(categories, self)
                        view.add_item(select)
                    
                    await message.edit(view=view)
                    logger.info(f"Restored ticket panel in {guild.name}")
                    
                except discord.NotFound:
                    # Message was deleted, remove from data
                    del self.panel_messages[guild_id]
                    self.save_data(self.panel_messages_file, self.panel_messages)
                    
            except Exception as e:
                logger.error(f"Failed to restore panel for guild {guild_id}: {e}")

    @commands.command(name='ticketpanel')
    @commands.has_permissions(manage_channels=True)
    async def create_ticket_panel(self, ctx, *, title="🎫 Support Tickets"):
        """Create a ticket panel with category selection"""
        try:
            config = self.get_server_config(ctx.guild.id)
            categories = config.get('ticket_categories', ['Support', 'Bug Report', 'Feature Request', 'Other'])
            message_text = config.get('ticket_message', 'Click below to create a support ticket!')

            embed = discord.Embed(
                title=title,
                description=message_text,
                color=0x00aaff
            )
            embed.add_field(
                name="📋 Available Categories",
                value="\n".join([f"🎫 {cat}" for cat in categories]),
                inline=False
            )
            embed.set_footer(text="SSupport Bot - Ticket System")

            # Create view with appropriate UI elements
            view = View(timeout=None)
            
            if len(categories) <= 5:  # Use buttons for few categories
                category_emojis = {
                    'Support': '🎧',
                    'Bug Report': '🐛',
                    'Feature Request': '💡', 
                    'General': '💬',
                    'Technical': '⚙️',
                    'Billing': '💳',
                    'Other': '📩'
                }
                
                for category in categories:
                    emoji = category_emojis.get(category, '🎫')
                    button = Button(
                        label=category,
                        style=discord.ButtonStyle.primary,
                        emoji=emoji,
                        custom_id=f"ticket_{category.lower().replace(' ', '_')}"
                    )
                    button.callback = lambda i, cat=category: self.create_ticket(i, cat)
                    view.add_item(button)
            else:  # Use select menu for many categories
                select = self.TicketCategorySelect(categories, self)
                view.add_item(select)

            panel_message = await ctx.send(embed=embed, view=view)
            
            # Store panel message for persistence
            self.panel_messages[str(ctx.guild.id)] = {
                'channel_id': ctx.channel.id,
                'message_id': panel_message.id,
                'created_by': ctx.author.id,
                'created_at': datetime.now().isoformat()
            }
            self.save_data(self.panel_messages_file, self.panel_messages)
            
            # Delete command message
            try:
                await ctx.message.delete()
            except:
                pass
                
            logger.info(f"Ticket panel created by {ctx.author} in {ctx.guild.name}")
            
        except Exception as e:
            logger.error(f"Error creating ticket panel: {e}")
            await ctx.send(f"❌ Error creating ticket panel: {e}")

    @commands.command()
    async def ticket(self, ctx, action=None, *, args=None):
        """Ticket management commands"""
        if not action:
            embed = discord.Embed(
                title="🎫 Ticket Commands",
                color=0x00aaff
            )
            embed.add_field(
                name="User Commands",
                value="`ticket close` - Close current ticket\n"
                      "`ticket info` - Show ticket information",
                inline=False
            )
            if ctx.author.guild_permissions.manage_channels:
                embed.add_field(
                    name="Staff Commands", 
                    value="`ticket add <user>` - Add user to ticket\n"
                          "`ticket remove <user>` - Remove user from ticket\n"
                          "`ticket claim` - Claim ticket\n"
                          "`ticket rename <name>` - Rename ticket",
                    inline=False
                )
            await ctx.send(embed=embed)
            return

        ticket_data = self.get_ticket_by_channel(ctx.guild.id, ctx.channel.id)
        if not ticket_data:
            await ctx.send("❌ This command can only be used in ticket channels!")
            return

        if action == "close":
            # Create a mock interaction for the close function
            class MockInteraction:
                def __init__(self, user, channel, guild):
                    self.user = user
                    self.channel = channel
                    self.guild = guild
                    self.response = MockResponse(channel)
                    
                class MockResponse:
                    def __init__(self, channel):
                        self.channel = channel
                    
                    async def send_message(self, *args, **kwargs):
                        return await self.channel.send(*args, **kwargs)
                        
            mock_interaction = MockInteraction(ctx.author, ctx.channel, ctx.guild)
            await self.close_ticket(mock_interaction)
            
        elif action == "info":
            creator = ctx.guild.get_member(ticket_data['creator_id'])
            embed = discord.Embed(
                title=f"🎫 Ticket #{ticket_data['number']:04d}",
                color=0x00aaff
            )
            embed.add_field(name="Category", value=ticket_data['category'], inline=True)
            embed.add_field(name="Creator", value=creator.mention if creator else "Unknown", inline=True)
            embed.add_field(name="Status", value=ticket_data['status'].title(), inline=True)
            embed.add_field(name="Created", value=discord.utils.format_dt(
                datetime.fromisoformat(ticket_data['created_at'])), inline=True)
            embed.add_field(name="Duration", value=self.format_duration(ticket_data['created_at']), inline=True)
            await ctx.send(embed=embed)

    # ================== DASHBOARD INTEGRATION ================== #
    
    def get_dashboard_data(self, guild_id):
        """Get ticket data for dashboard"""
        open_tickets = self.get_open_tickets(guild_id)
        
        dashboard_tickets = []
        for ticket in open_tickets:
            dashboard_tickets.append({
                'number': ticket['number'],
                'category': ticket['category'],
                'channel_id': ticket['channel_id'],
                'creator_id': ticket['creator_id'],
                'created_at': ticket['created_at'],
                'status': ticket['status']
            })
            
        return {'tickets': dashboard_tickets}

    def create_panel_from_dashboard(self, guild_id, channel_id, message_content, categories):
        """Create ticket panel from dashboard"""
        # This would be called by your Flask API
        # Implementation depends on how you want to handle async operations from Flask
        pass

async def setup(bot):
    await bot.add_cog(Tickets(bot))