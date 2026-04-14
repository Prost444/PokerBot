# 🃏 Poker Bot

Telegram bot for running poker evenings. Tracks player ratings using an adapted Elo system with chip performance, bounty bonuses, and attendance rewards.

> **Disclaimer:** This is a purely recreational, non-gambling activity. No real money, bets, or prizes of monetary value are involved. The rating system exists solely to encourage thoughtful play and regular attendance. All chips are play chips with no cash equivalent.

## How It Works

Every evening, the admin creates a game via the bot. Players register, get seated at tables automatically, and play poker with play chips (5000 starting stack, 50/100 blinds). The bot tracks eliminations, chip counts, and calculates Elo rating changes at the end.

### For Players

1. **Register once:** `/register YourName`
2. **Join a game:** `/join` (during registration) or `/join 2` (late join, pick table 2)
3. **Check your stats:** `/stats`
4. **See the leaderboard:** `/rating`
5. **View tables:** `/tables`

### For Admins

1. **Create a game evening:** `/new_game` (defaults: regular, snake seating)
   - Tournament with bounty: `/new_game tournament`
   - Divisional seating: `/new_game regular divisional`
2. **Start the game:** `/go` — generates table seating automatically
3. **Record knockouts:** `/ko @eliminated @eliminator`
4. **Record chip counts:** `/chips @player 12500` (for surviving players before closing a table)
5. **Close a table:** `/close_table 1` — calculates ratings for that table
6. **Finish the evening:** `/finish` — closes remaining tables, updates streaks, shows results

### Final Table

To run a final table, simply finish the current game (`/finish`) and start a new one (`/new_game`) with only the qualifying players joining. The bot handles each game independently.

## Commands Reference

| Command | Who | Description |
|---------|-----|-------------|
| `/register Name` | Everyone | One-time registration |
| `/join [N]` | Everyone | Join game; N = table number for late arrivals |
| `/rating` | Everyone | Top 20 leaderboard |
| `/stats` | Everyone | Personal stats and recent history |
| `/game` | Everyone | Current game status |
| `/tables` | Everyone | Table seating and alive status |
| `/new_game [type] [seating]` | Admin | Create game (regular/tournament, snake/divisional) |
| `/go` | Admin | Start game, generate seating |
| `/ko @out @by` | Admin | Record elimination |
| `/chips @player N` | Admin | Record chip count for a player |
| `/close_table N` | Admin | Close table N, calculate ratings |
| `/finish` | Admin | End evening, show results |
| `/cancel` | Admin | Cancel current game |

## Game Types

- **Regular** — Elo changes based on finishing position and chip performance. No bounty bonuses.
- **Tournament** — Same as regular, plus bounty chips. Each knockout awards bonus rating points scaled by the rating difference between hunter and victim.

## Seating Types

- **Snake** (default) — Players sorted by Elo are distributed in a zigzag across tables, balancing average rating per table. Best for mixed-skill evenings.
- **Divisional** — Players sorted by Elo fill tables sequentially (top tier together, next tier together). Gives newcomers a more comfortable environment.

Max 9 players per table. Late arrivals choose which table to join.

## Rating System

### Elo (core)

Generalized Elo formula for N players. The actual score `S = (N - k) / (N - 1)` is compared against the expected score (mean pairwise win probability). K-factor adapts to experience: 40 for newcomers (< 10 games), 30 for developing (< 1400 Elo), 20 for established players.

### Chip Performance

Players' final chip counts influence their Elo change. A player who accumulated significantly more chips than average gets a rating boost (up to +50%), while a player barely surviving gets a slight penalty (down to -50%). Eliminated players are unaffected — their position already reflects elimination. Use `/chips @player amount` before closing a table.

### Bounty (tournament only)

Each knockout awards: `bounty = 2 + (victim_Elo - hunter_Elo) / 200` (minimum 1.0). Knocking out stronger opponents is more rewarding, which protects newcomers from targeted hunting.

### Attendance Bonus

Multiplier `min(1.0 + 0.05 * streak, 1.25)` applied to positive Elo changes. Maximum x1.25 for 5+ consecutive evenings. Missing resets the streak but doesn't penalize.

### Seasons

Each season is 8 weeks. Between seasons, ratings softly regress toward 1200: `R_new = R_old * 0.8 + 1200 * 0.2`.

For the full design rationale, see [docs/rating_concept.md](docs/rating_concept.md).

## Setup

```bash
git clone https://github.com/Prost444/PokerBot.git
cd PokerBot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BOT_TOKEN and ADMIN_IDS
python -m shad_poker_bot.main
```

## Testing

```bash
pip install -r requirements-test.txt
pytest --cov=shad_poker_bot --cov-report=term-missing
```

## Project Structure

```
shad_poker_bot/
├── main.py              # Entry point, bot initialization
├── config.py             # Configuration via dataclasses
├── bot/
│   ├── filters.py        # IsAdmin filter
│   ├── formatting.py     # Message formatting
│   └── handlers/
│       ├── common.py     # /start, /help, /rating, /game, /tables
│       ├── player.py     # /register, /join, /stats
│       └── admin.py      # /new_game, /go, /ko, /chips, /close_table, /finish, /cancel
├── db/
│   ├── models.py         # SQL schema and init_db()
│   └── repository.py     # Data access layer (async SQLite)
└── services/
    ├── game.py           # Game session orchestrator
    ├── rating.py         # Rating engine (Elo + bounty + chips)
    └── seating.py        # Table seating algorithms
```

## License

MIT

## Authors

Student passionate about math, CS, and Thursday poker nights.
