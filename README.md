# Middleman Bot (FLUXX Escrow Service)

A Telegram escrow bot that helps users safely buy and sell items or services by acting as a trusted middleman. The bot is built with Python using the `python-telegram-bot` library and FastAPI for webhook handling.

---

## Features

- Start and manage escrow deals between buyers and sellers in Telegram groups.
- Supports P2P and Buy & Sell deal types.
- Automatic timer and moderator involvement for dispute resolution.
- Payment integration with Oxapay.
- User reviews and feedback system.
- Admin commands for managing fees, deals, and bot operation.
- Group creation and management via Telethon client.

---

## Prerequisites

- Python 3.9 or higher
- A VPS or server with internet access
- Telegram Bot Token (from [BotFather](https://t.me/BotFather))
- Oxapay API key (for payment integration)
- API ID and API Hash from [my.telegram.org](https://my.telegram.org) for Telethon client
- Required Python packages (see [requirements.txt](requirements.txt))

---

## Installation

1. **Clone the repository**

```bash
git clone <repository-url>
cd middleman
```

2. **Create and activate a virtual environment**

```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On Linux/macOS
source venv/bin/activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Configure the bot**

- Rename `.env.example` to `.env` (if provided) or create a `.env` file.
- Set the following environment variables or update `config.py` and `config.json` accordingly:

| Variable       | Description                          |
|----------------|------------------------------------|
| `TOKEN`        | Your Telegram bot token             |
| `API_ID`       | Telegram API ID for Telethon client |
| `API_HASH`     | Telegram API Hash for Telethon client |
| `ADMIN_ID`     | Telegram user ID of the bot admin   |
| `OXAPAY_API_KEY` | API key for Oxapay payment gateway |

- Update `config.json` for fees and other settings:

```json
{
  "p2p_fee": 1.5,
  "bs_fee": 2.0,
  "allfee": 1.0,
  "profileurl": "https://example.com/profile.jpg",
  "success_sticker_id": "CAACAgIAAxkBAAEB..."
}
```

---

## Running the Bot

### Running on a VPS

1. **Start the bot**

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
or 

```bash
python main.py
```
- This will start the FastAPI server and the Telegram bot concurrently.
- Make sure port 8000 is open on your VPS firewall.

2. **Keep the bot running**

- Use a process manager like `screen`, `tmux`, or `systemd` to keep the bot running in the background.
- Example using `screen`:

```bash
screen -S middleman_bot
uvicorn main:app --host 0.0.0.0 --port 8000
# Press Ctrl+A then D to detach
```

---

### Running on Render

Render is a cloud platform that can host your bot easily.

1. **Create a new Web Service on Render**

- Go to [Render](https://render.com) and sign up or log in.
- Click "New" > "Web Service".
- Connect your GitHub repository containing the bot code.
- Set the build command to:

```bash
pip install -r requirements.txt
```

- Set the start command to:

```bash
uvicorn main:app --host 0.0.0.0 --port 10000
```

- Set the environment variables (`TOKEN`, `API_ID`, `API_HASH`, `ADMIN_ID`, `OXAPAY_API_KEY`) in the Render dashboard under the "Environment" tab.
- Set the port to `10000` (Render requires this port).
- Deploy the service.

2. **Access and logs**

- Render will provide a public URL for your bot.
- You can view logs and restart the service from the Render dashboard.

---

### Running on Heroku

Heroku is another popular platform for hosting bots.

1. **Create a new app on Heroku**

- Go to [Heroku](https://heroku.com) and sign up or log in.
- Click "New" > "Create new app".
- Choose a unique app name and region.

2. **Prepare your app for Heroku**

- Create a `Procfile` in your project root with the following content:

```
web: uvicorn main:app --host 0.0.0.0 --port=${PORT:-8000}
```

- Commit and push your code to a GitHub repository or Heroku Git.

3. **Deploy the app**

- Connect your GitHub repo to Heroku or push via Heroku Git.
- Set the required environment variables (`TOKEN`, `API_ID`, `API_HASH`, `ADMIN_ID`, `OXAPAY_API_KEY`) in the Heroku dashboard under "Settings" > "Config Vars".
- Deploy the app.

4. **Run and monitor**

- Heroku will assign a dynamic port accessible via the `PORT` environment variable.
- Use the Heroku dashboard to view logs and manage the app.

---

## Bot Usage

### Basic Commands

- `/start` - Show welcome message and main menu.
- `/form` - Create a deal form in a group.
- `/sdeal` - Start a new deal in a group.
- `/p2pfee <percentage>` - Set P2P fee (admin only).
- `/bsfee <percentage>` - Set Buy & Sell fee (admin only).
- `/setfee <percentage>` - Set general fee (admin only).
- `/trades` - Get all trades (admin only).
- `/enddeal` - End a deal (admin only).
- `/endall` - End all active deals (admin only).
- `/setsticker` - Set success sticker (admin only).
- `/getdeal` - Get current deal info in group.
- `/refund` - Initiate refund process.
- `/login` - Admin login.
- `/logout` - Admin logout.
- `/create` - Create a new escrow group.
- `/fetch` - Fetch bot's group list.
- `/on` - Turn on Telethon client listener (admin only).
- `/off` - Turn off Telethon client listener (admin only).

### Deal Workflow

1. Add the bot to your Telegram group.
2. Use `/form` command in the group to create a deal form.
3. Fill the form with buyer, seller, deal description, price, and optional time.
4. Both buyer and seller confirm the deal.
5. Buyer selects deal type and timer duration.
6. Buyer enters deposit amount and completes payment via provided link.
7. Seller confirms payment received.
8. Both parties can leave reviews.
9. Moderator can be involved if disputes arise.

### Form Format Example

```
Buyer: @buyerusername
Seller: @sellerusername
Deal: Selling PS4 console
Price: $200
Time: 2 hours
```

---

## Configuration Details

- Fees are configurable in `config.json` and can be updated via admin commands.
- The bot uses Telethon client for advanced group management.
- Payment integration is handled via Oxapay with webhook callbacks.
- Admin ID must be set for privileged commands.
- Success sticker can be set by replying to a sticker with `/setsticker`.

---

## Troubleshooting

- Ensure the bot has admin rights in groups for full functionality.
- Make sure the admin user has logged in via `/login` command.
- Check that API keys and tokens are correctly set.
- Use logs to debug errors; the bot prints errors to console.
- For payment issues, verify Oxapay API key and webhook URL.

---

## Contributing

Contributions are welcome! Please fork the repository and submit pull requests.

---

## License

This project is licensed under the MIT License.

---

## Contact

For support or questions, contact the bot admin at [Telegram](https://t.me/echofluxxx).
