import discord
from discord.ext import commands
import random
import hashlib
import logging
import aiohttp
import json
from typing import Optional, Union

logger = logging.getLogger('SSupportBot.fun')

class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        """Initialize aiohttp session when cog loads"""
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Clean up aiohttp session when cog unloads"""
        if self.session:
            await self.session.close()

    @commands.command()
    async def roll(self, ctx: commands.Context, dice: str = "1d6"):
        """Roll dice in NdN format (e.g., 2d6, 3d20)"""
        try:
            if 'd' not in dice.lower():
                await ctx.send("Format has to be in NdN! (e.g., `2d6`, `1d20`, `3d10`)")
                return

            rolls, limit = map(int, dice.lower().split('d'))
            
            if rolls < 1 or rolls > 50:
                await ctx.send("Number of dice must be between 1 and 50!")
                return
                
            if limit < 1 or limit > 1000:
                await ctx.send("Die size must be between 1 and 1000!")
                return

            results = [random.randint(1, limit) for _ in range(rolls)]
            total = sum(results)
            
            if len(results) <= 20:  # Show individual rolls for small amounts
                result_str = ', '.join(str(r) for r in results)
                embed = discord.Embed(
                    title="Dice Roll",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name=f"{ctx.author.display_name} rolled {dice}",
                    value=f"**Results:** {result_str}\n**Total:** {total}",
                    inline=False
                )
            else:  # Just show total for large amounts
                embed = discord.Embed(
                    title="Dice Roll",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name=f"{ctx.author.display_name} rolled {dice}",
                    value=f"**Total:** {total}",
                    inline=False
                )
            
            embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/🎲.png")
            await ctx.send(embed=embed)
            
            logger.info(f"{ctx.author} rolled {dice} in {ctx.guild.name}: total {total}")
            
        except ValueError:
            await ctx.send("Invalid format! Use NdN (e.g., `2d6`, `1d20`)")
        except Exception as e:
            logger.error(f"Error in roll command: {e}")
            await ctx.send("An error occurred while rolling the dice.")

    @commands.command()
    async def choose(self, ctx: commands.Context, *choices: str):
        """Choose between multiple options"""
        try:
            if not choices:
                embed = discord.Embed(
                    title="Choose Command",
                    description="Provide choices to choose from!\n\n**Example:** `ss!choose pizza burger tacos`",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            if len(choices) == 1:
                await ctx.send("You need to provide at least 2 choices!")
                return
            
            choice = random.choice(choices)
            
            embed = discord.Embed(
                title="Choice Made!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Options:",
                value=", ".join(choices),
                inline=False
            )
            embed.add_field(
                name="I choose:",
                value=f"**{choice}**",
                inline=False
            )
            embed.set_footer(text=f"Chosen for {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} used choose in {ctx.guild.name}: {choices} -> {choice}")
            
        except Exception as e:
            logger.error(f"Error in choose command: {e}")
            await ctx.send("An error occurred while choosing.")

    @commands.command()
    async def ship(self, ctx: commands.Context, user1: Union[discord.Member, str], user2: Union[discord.Member, str] = None):
        """Ship two users or names together with a compatibility rating"""
        try:
            # If only one input, ship with command author
            if user2 is None:
                user2 = ctx.author
            
            # Convert inputs to proper format
            name1, member1 = await self._resolve_ship_input(ctx, user1)
            name2, member2 = await self._resolve_ship_input(ctx, user2)
            
            if not name1 or not name2:
                await ctx.send("Please provide valid users or names!")
                return

            # Prevent bot shipping
            if (member1 and member1.bot) or (member2 and member2.bot):
                await ctx.send("Bots can't participate in romance! Try shipping real users.")
                return

            # Prevent self-shipping for members
            if member1 and member2 and member1 == member2:
                await ctx.send("You can't ship someone with themselves!")
                return

            # Calculate compatibility
            love_percent = self._calculate_compatibility(name1, name2, member1, member2)
            
            # Create ship name
            ship_name = self._create_ship_name(name1, name2)
            
            # Get status and color based on compatibility
            status, color, emoji = self._get_compatibility_status(love_percent)
            
            # Create embed
            embed = discord.Embed(
                title=f"{emoji} Ship Results",
                description=f"**{name1}** + **{name2}** = **{ship_name}**",
                color=color
            )
            
            # Create progress bar
            filled_hearts = "❤️" * (love_percent // 10)
            empty_hearts = "🤍" * (10 - (love_percent // 10))
            progress_bar = filled_hearts + empty_hearts
            
            embed.add_field(
                name="Compatibility Rating",
                value=f"**{love_percent}%**\n{progress_bar}\n{status}",
                inline=False
            )
            
            # Add bonus info for members
            if member1 and member2:
                embed.add_field(
                    name="Ship Details",
                    value=f"👤 **{member1.display_name}** & **{member2.display_name}**\n🎭 Ship Name: **{ship_name}**",
                    inline=False
                )
            
            embed.set_footer(text=f"Shipped by {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} shipped {name1} + {name2} in {ctx.guild.name}: {love_percent}%")
            
        except Exception as e:
            logger.error(f"Error in ship command: {e}")
            await ctx.send("An error occurred while shipping.")

    @commands.command()
    async def flip(self, ctx: commands.Context):
        """Flip a coin"""
        result = random.choice(["Heads", "Tails"])
        embed = discord.Embed(
            title="Coin Flip",
            description=f"**{result}!**",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://i.imgur.com/coin.png" if result == "Heads" else "https://i.imgur.com/coin2.png")
        await ctx.send(embed=embed)

    @commands.command()
    async def rps(self, ctx: commands.Context, choice: str = None):
        """Play Rock Paper Scissors with the bot"""
        if not choice:
            embed = discord.Embed(
                title="Rock Paper Scissors",
                description="Choose: `rock`, `paper`, or `scissors`\n\nExample: `ss!rps rock`",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return
        
        user_choice = choice.lower()
        valid_choices = ["rock", "paper", "scissors"]
        
        if user_choice not in valid_choices:
            await ctx.send("Invalid choice! Choose `rock`, `paper`, or `scissors`")
            return
        
        bot_choice = random.choice(valid_choices)
        
        # Determine winner
        if user_choice == bot_choice:
            result = "It's a tie!"
            color = discord.Color.orange()
        elif (user_choice == "rock" and bot_choice == "scissors") or \
             (user_choice == "paper" and bot_choice == "rock") or \
             (user_choice == "scissors" and bot_choice == "paper"):
            result = "You win!"
            color = discord.Color.green()
        else:
            result = "I win!"
            color = discord.Color.red()
        
        embed = discord.Embed(
            title="Rock Paper Scissors",
            color=color
        )
        embed.add_field(name="You chose", value=user_choice.title(), inline=True)
        embed.add_field(name="I chose", value=bot_choice.title(), inline=True)
        embed.add_field(name="Result", value=result, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def magic8ball(self, ctx: commands.Context, *, question: str = None):
        """Ask the magic 8-ball a question"""
        if not question:
            await ctx.send("You need to ask a question! Example: `ss!magic8ball Will it rain tomorrow?`")
            return
        
        responses = [
            "It is certain", "Reply hazy, try again", "Don't count on it",
            "It is decidedly so", "Ask again later", "My reply is no",
            "Without a doubt", "Better not tell you now", "My sources say no",
            "Yes definitely", "Cannot predict now", "Outlook not so good",
            "You may rely on it", "Concentrate and ask again", "Very doubtful",
            "As I see it, yes", "Most likely", "Outlook good",
            "Yes", "Signs point to yes"
        ]
        
        answer = random.choice(responses)
        
        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            color=discord.Color.purple()
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=f"**{answer}**", inline=False)
        embed.set_footer(text=f"Asked by {ctx.author.display_name}")
        
        await ctx.send(embed=embed)

    @commands.command()
    async def joke(self, ctx: commands.Context):
        """Get a random joke"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Try to get a joke from an API
            try:
                async with self.session.get("https://official-joke-api.appspot.com/random_joke") as response:
                    if response.status == 200:
                        joke_data = await response.json()
                        setup = joke_data.get("setup", "")
                        punchline = joke_data.get("punchline", "")
                        
                        embed = discord.Embed(
                            title="😂 Random Joke",
                            description=f"**{setup}**\n\n||{punchline}||",
                            color=discord.Color.yellow()
                        )
                        embed.set_footer(text="Click the spoiler to reveal the punchline!")
                        await ctx.send(embed=embed)
                        return
            except:
                pass
            
            # Fallback to built-in jokes
            jokes = [
                ("Why don't scientists trust atoms?", "Because they make up everything!"),
                ("What do you call a fake noodle?", "An impasta!"),
                ("Why did the scarecrow win an award?", "He was outstanding in his field!"),
                ("What do you call a bear with no teeth?", "A gummy bear!"),
                ("Why don't programmers like nature?", "It has too many bugs!"),
                ("What's the best thing about Switzerland?", "I don't know, but the flag is a big plus!"),
                ("Why do we tell actors to break a leg?", "Because every play has a cast!"),
                ("What did the ocean say to the beach?", "Nothing, it just waved!"),
                ("Why don't eggs tell jokes?", "They'd crack each other up!"),
                ("What do you call a dinosaur that crashes his car?", "Tyrannosaurus Wrecks!")
            ]
            
            setup, punchline = random.choice(jokes)
            
            embed = discord.Embed(
                title="😂 Random Joke",
                description=f"**{setup}**\n\n||{punchline}||",
                color=discord.Color.yellow()
            )
            embed.set_footer(text="Click the spoiler to reveal the punchline!")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in joke command: {e}")
            await ctx.send("I couldn't think of a good joke right now!")

    async def _resolve_ship_input(self, ctx, input_value):
        """Resolve input to name and member (if applicable)"""
        try:
            # If it's already a member
            if isinstance(input_value, discord.Member):
                return input_value.display_name, input_value
            
            # If it's a string, try to find member
            if isinstance(input_value, str):
                # Try to find by mention
                if input_value.startswith('<@') and input_value.endswith('>'):
                    user_id = input_value[2:-1].replace('!', '')
                    try:
                        member = ctx.guild.get_member(int(user_id))
                        if member:
                            return member.display_name, member
                    except ValueError:
                        pass
                
                # Try to find by ID
                try:
                    user_id = int(input_value)
                    member = ctx.guild.get_member(user_id)
                    if member:
                        return member.display_name, member
                except ValueError:
                    pass
                
                # Try to find by name/nick
                member = discord.utils.get(ctx.guild.members, name=input_value)
                if not member:
                    member = discord.utils.get(ctx.guild.members, display_name=input_value)
                
                if member:
                    return member.display_name, member
                
                # Return as string if not found as member
                return input_value, None
                
        except Exception as e:
            logger.error(f"Error resolving ship input {input_value}: {e}")
            return str(input_value), None
        
        return str(input_value), None

    def _calculate_compatibility(self, name1, name2, member1, member2):
        """Calculate compatibility percentage"""
        # Create deterministic hash
        if member1 and member2:
            # Use user IDs for consistency
            combo = f"{min(member1.id, member2.id)}-{max(member1.id, member2.id)}"
        else:
            # Use names
            names = sorted([name1.lower(), name2.lower()])
            combo = f"{names[0]}-{names[1]}"
        
        hash_val = int(hashlib.sha256(combo.encode()).hexdigest(), 16)
        love_percent = hash_val % 101
        
        # Add bonus for shared roles (members only)
        if member1 and member2:
            common_roles = set(member1.roles) & set(member2.roles)
            if len(common_roles) > 1:  # More than @everyone
                love_percent = min(100, love_percent + (len(common_roles) - 1) * 2)
        
        return love_percent

    def _create_ship_name(self, name1, name2):
        """Create a ship name from two names"""
        # Take first half of first name and second half of second name
        split1 = max(2, len(name1) // 2)
        split2 = max(1, len(name2) // 2)
        return name1[:split1] + name2[split2:]

    def _get_compatibility_status(self, percentage):
        """Get status message and color based on compatibility"""
        if percentage >= 90:
            return "Perfect soulmates!", discord.Color.from_rgb(255, 20, 147), "💖"
        elif percentage >= 70:
            return "Great match!", discord.Color.from_rgb(255, 105, 180), "💕"
        elif percentage >= 50:
            return "Could work out!", discord.Color.from_rgb(255, 165, 0), "💛"
        elif percentage >= 30:
            return "Might be worth a try", discord.Color.from_rgb(255, 215, 0), "💙"
        else:
            return "Not looking promising...", discord.Color.from_rgb(128, 128, 128), "💔"

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))