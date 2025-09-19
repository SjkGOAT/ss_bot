import os
import json
import discord
from discord.ext import commands

# This script initializes the data directory structure for the dashboard
# Run this script once to set up the necessary files

def init_data_directory():
    print("Initializing data directory structure...")
    
    # Create main data directory if it doesn't exist
    if not os.path.exists("data"):
        os.makedirs("data")
        print("Created data directory")
    
    # Create a default warnings.json file
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

if __name__ == "__main__":
    init_data_directory()
    
    # You can add guild IDs here to create config files for them
    # For example:
    # create_test_guild_config("123456789012345678")
    
    print("\nTo create configs for specific guilds, edit this file and add:")
    print("create_test_guild_config(\"YOUR_GUILD_ID\")")