# SSupport Bot Dashboard

A Discord bot with an integrated web dashboard for server management, moderation, and ticket systems.

## Features

- **Server Management**: Configure welcome messages and auto-roles
- **Moderation**: Manage bans, timeouts, and warnings
- **Ticket System**: Create and manage support tickets
- **Utility Commands**: Various utility features for server management

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Configure your Discord Bot Token and OAuth2 credentials in `main.py`:
   ```python
   DISCORD_CLIENT_ID = "your-client-id"
   DISCORD_CLIENT_SECRET = "your-client-secret"
   DISCORD_REDIRECT_URI = "http://your-domain:13526/callback"
   BOT_TOKEN = "your-bot-token"
   ```

3. Make sure your bot has the following OAuth2 scopes:
   - `bot`
   - `identify`
   - `guilds`

4. Ensure your bot has the following intents enabled in the Discord Developer Portal:
   - Server Members Intent
   - Message Content Intent
   - Presence Intent

5. Run the bot:
   ```
   python main.py
   ```

6. Access the dashboard at: `http://your-domain:13526`

## Dashboard Usage

1. Log in with your Discord account
2. Select a server where you have administrator permissions
3. Configure settings using the different tabs in the dashboard:
   - Overview
   - Moderation
   - Tickets
   - Utility
   - Warnings

## Bot Commands

The bot uses the prefix `ss!` for commands:

- `ss!help` - Display help information
- `ss!warn <user> <reason>` - Warn a user
- `ss!ban <user> <reason>` - Ban a user
- `ss!kick <user> <reason>` - Kick a user
- `ss!ticket` - Create a new support ticket

Check `ss!help` for a complete list of commands.

## Directory Structure

```
/
├── cogs/               # Bot command modules
│   ├── fun.py         # Fun commands
│   ├── moderation.py  # Moderation commands
│   ├── tickets.py     # Ticket system
│   └── utility.py     # Utility commands
├── data/              # Bot data storage
├── static/            # Dashboard static files
│   ├── script.js      # Dashboard JavaScript
│   └── style.css      # Dashboard styles
├── templates/         # Dashboard HTML templates
├── main.py            # Main application file
└── requirements.txt   # Dependencies
```

## Contributing

Contributions are welcome! Feel free to submit pull requests or open issues for bugs and feature requests.

## License

This project is licensed under the MIT License.