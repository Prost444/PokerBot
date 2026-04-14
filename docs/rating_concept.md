# YSDA Poker Club Rating System Concept

## 1. Problem Statement

When the game is played with chips that carry no consequences, players have no incentive to make thoughtful decisions. Going broke in two hands costs nothing — you can just take new chips or leave. This creates a cascade of problems: experienced players get bored playing against chaotic all-ins, newcomers don't learn, and attendance drops.

What's needed is a system that creates **reputational consequences** for every decision at the table, while remaining friendly and not turning the club into a casino.

---

## 2. Overview of Researched Approaches

### 2.1. League Point Systems

Used in bar and club leagues (World Tavern Poker, Atlanta Poker Club, The Nuts Poker League). The idea: points are awarded each evening based on finishing position. Typical formula:

```
Points(k, N) = base + (N - k) * step + bonus_final_table
```

Pros: simplicity, clarity. Cons: doesn't account for opponent strength, doesn't adapt to player level, weakly distinguishes luck from skill.

### 2.2. Global Poker Index (GPI)

Professional ranking system for 450,000+ tournament players. Each result is scored as a product of three factors:

```
Score = FPF × BIF × AF
```

Where FPF is the percentage of players beaten, BIF is the buy-in factor (logarithmic), AF is the aging factor. Final ranking is the sum of the best 5 results per half-year period.

Pros: accounts for result aging, scalability. Cons: designed for buy-in tournaments, difficult to adapt to a free format.

### 2.3. Adapted Elo System for Multiplayer Poker

The classic Elo system (chess) generalized for N players. Key idea: each session is a set of pairwise comparisons between all participants.

```
S_i = (N - k_i) / (N - 1)       — actual result for player i (position k_i out of N)
E_i = avg(1 / (1 + 10^((R_j - R_i) / 400)))   — expected result based on ratings
R_new = R_old + K × (S_i - E_i)  — rating update
```

Pros: self-correcting, accounts for field strength, proven over decades. Cons: sensitive to K-factor choice, requires enough sessions to stabilize.

### 2.4. Bounty Chips

In bounty tournaments, part of the prize pool is "attached" to each player. Eliminate an opponent — take their bounty chip. Variants exist: fixed bounty, progressive (part of the defeated player's bounty adds to yours), mystery bounty (random rewards).

Pros: add excitement and extra objectives. Cons: can incentivize hunting weak players. In a free format, bounty value needs to be tied to rating points.

---

## 3. Proposed System: "YSDA Poker Rating"

A hybrid system combining **adapted Elo** as the core with **bounty bonuses** and **seasonal structure** for long-term engagement.

### 3.1. Evening Structure

Each Thursday, one or more tournament sessions are held. Depending on the number of players:

| Players | Tables | Format |
|---------|--------|--------|
| 9 or fewer | 1 | Single final table |
| 10–18 | 2 | Two tables → separate rating per table |
| 19–27 | 3 | Three tables → separate rating per table |

Each player receives an equal starting stack (e.g., 5000 chips). **No rebuys** — this is the key rule that makes every chip valuable.

Tables are created automatically with a maximum of 9 players each. When a table is closed, ratings are recalculated for that table's participants. Late-arriving players are assigned to the table with the fewest players, or a new table is created if all are full.

### 3.2. Elo Rating: System Core

**Starting rating:** 1200 for all new players.

**After each session:**

1. All N participants at a table are ranked by elimination order (or final chip count).
2. Actual result for player i at position k:

```
S_i = (N - k) / (N - 1)
```

Examples: 1st of 10 → S = 1.0, 5th of 10 → S = 0.556, 10th of 10 → S = 0.0.

3. Expected result — mean pairwise probability:

```
E_i = (1 / (N - 1)) × Σ_{j≠i} [1 / (1 + 10^((R_j - R_i) / 400))]
```

4. Rating update:

```
R_new = R_old + K × (N - 1) × (S_i - E_i)
```

The (N-1) multiplier normalizes update scale across different participant counts.

**K-factor (rate of rating change):**

| Condition | K |
|-----------|---|
| Player's first 10 sessions | 40 |
| Rating < 1400 | 30 |
| Rating ≥ 1400 | 20 |

High K for newcomers allows quick determination of their actual level. Then the rating stabilizes.

### 3.3. Bounty System: "Scalps" (Tournament Mode Only)

Bounty chips are only used in tournament mode. In our free format, bounty chips have no monetary equivalent — instead, they convert into **rating bonuses**.

**Mechanics:**

- Each player at seating receives one named bounty chip (different color from playing chips).
- When a player eliminates another (takes all their chips), they receive the eliminated player's bounty chip.
- At the end of the evening, bounties convert to Elo bonus:

```
bounty_bonus = Σ (2 + (R_victim - R_hunter) / 200)
```

Eliminating a player stronger than yourself is more valuable (up to +4 rating per scalp), while eliminating a weaker player yields little (+1..+2). This **protects newcomers** from targeted hunting and rewards bravery against strong opponents.

Minimum bonus per scalp is 1 point (cannot go negative from bounty).

**Why this normalizes behavior:** a reckless all-in means risking your bounty chip, and with it — rating points for another player. This creates a "cost" of losing that was missing in free play.

**In regular (non-tournament) games**, bounty chips are not used and no bounty bonus is applied to rating changes.

### 3.4. Chip Performance Factor

The rating system accounts for how many chips a player accumulates, not just their finishing position. Every player starts with 5000 chips (small blind 50, big blind 100). Before closing a table, the admin records chip counts for surviving players using `/chips @player amount`. Eliminated players automatically have 0 chips.

**Formula:**

```
avg_chips = total_chips_of_survivors / number_of_survivors
chip_factor = 1.0 + chip_weight × (player_chips / avg_chips - 1.0)
```

Where `chip_weight = 0.3` (configurable). The chip_factor is clamped to [0.5, 1.5] and applied as a multiplier to the base Elo change.

**Examples (with avg = 10000):**
- Player with 15000 chips: factor = 1.0 + 0.3 × (1.5 - 1.0) = 1.15 → +15% Elo change
- Player with 5000 chips: factor = 1.0 + 0.3 × (0.5 - 1.0) = 0.85 → -15% Elo change
- Player with avg chips: factor = 1.0 → no modification
- Eliminated players: factor = 1.0 → position-based Elo only

**Why this matters:** Without chip tracking, a player who barely survives with 500 chips gets the same positional credit as one who dominates with 20000. The chip factor rewards aggressive, profitable play and penalizes passive survival, encouraging players to protect their stack and extract value.

### 3.5. Attendance Bonus: "Table Loyalty"

To encourage regular attendance:

```
attendance_multiplier = min(1.0 + 0.05 × streak, 1.25)
```

Where streak is the number of consecutively attended Thursdays (max bonus x1.25 for 5+ weeks in a row). The multiplier applies to the base Elo change (only to positive changes). Missing resets the streak.

This is a soft incentive: it doesn't punish for missing, but rewards regularity.

### 3.6. Table Seating

Two seating modes are available, chosen when creating a game evening:

**Snake draft** (default) — seating by rating using a zigzag pattern:

1. Sort players by Elo.
2. Distribute across tables: 1→A, 2→B, 3→C, 4→C, 5→B, 6→A, 7→A, 8→B, ...

This ensures **balanced tables** by strength: each table has roughly equal average rating. Strong and weak players are mixed.

**Divisional seating** — for special evenings (strong with strong):

1. Sort players by Elo.
2. Fill tables sequentially: table 1 gets the top tier, table 2 the next, etc.

This gives newcomers a chance to play in a comfortable environment. In standard mode, snake is preferred — it teaches newcomers faster.

### 3.7. Late Registration

Players can join even after the game has started. Late arrivals are assigned to the table with the fewest players. If all tables are full (9 players each), a new table is created automatically.

### 3.8. Seasonal Structure

Each **season = 8 weeks** (~2 months). This fits well with academic periods.

**During the season:**
- Elo rating is cumulative, not reset.
- A leaderboard with current ratings is maintained.
- For seasonal standings, the **best 6 of 8 evenings** count (you can miss 2 without penalty — for studies/illness).

**End of season:**
- Top 3 by Elo — "Season Champions" (symbolic awards: trophy, certificate, special seat at the next final table).
- Best progress (greatest Elo gain during the season) — "Season Breakthrough".
- Most scalps during the season — "Season Hunter".

**Between seasons:** Elo is NOT reset, but a soft regression to the mean is applied:

```
R_new_season = R_old × 0.8 + 1200 × 0.2
```

This gives trailing players hope and leaders a challenge. A 1500 rating becomes 1440, a 1000 rating becomes 1040.

---

## 4. Calculation Example

Evening: 10 players. Player Alexey (Elo 1350) finishes 2nd and eliminated 2 players (Elo 1180 and 1420).

**Base Elo:**
- S = (10 - 2) / (10 - 1) = 0.889
- E = calculated pairwise with all 9 opponents (assume E = 0.62 based on ratings)
- K = 30 (rating < 1400, but > 10 sessions)
- ΔR = 30 × 9 × (0.889 - 0.62) = 30 × 9 × 0.269 = **+72.6**

**Bounty bonus (tournament mode):**
- Scalp 1 (Elo 1180): 2 + (1180 - 1350)/200 = 2 + (-0.85) = 1.15
- Scalp 2 (Elo 1420): 2 + (1420 - 1350)/200 = 2 + 0.35 = 2.35
- Total bounty: **+3.50**

**Attendance:** Alexey is attending his 3rd Thursday in a row → multiplier = 1 + 0.05×3 = 1.15
- Applied to base ΔR: 72.6 × 1.15 = **83.5**

**Total:** Alexey gains +83.5 + 3.50 ≈ **+87 Elo**. New rating: 1437.

---

## 5. System Requirements

| Element | Input Data |
|---------|-----------|
| Player registration | Name / nickname |
| Evening start | Date, participant list, game type (regular/tournament), seating type (snake/divisional) |
| Seating | Automatic by rating (snake or divisional) |
| Tournament play | Elimination order, who eliminated whom |
| Evening end | Final ranking (by chips or elimination order) |
| Calculation | Automatic recalculation of Elo, bounty, multipliers |

---

## 6. Why This Combination

1. **Elo as the core** — proven 60+ years in chess, Go, esports. Self-correcting: an inflated rating quickly drops with poor results. For an audience of mathematicians and CS specialists — a natural and intuitive choice.

2. **Bounty as incentive** — creates value for every hand. A reckless all-in = high risk of losing your scalp, which hurts your rating. Bounties are tied to rating difference, protecting newcomers.

3. **No rebuys** — one life per evening. This is the main behavior "normalizer": every chip is valuable because there won't be new ones.

4. **Seasons with soft reset** — prevent ratings from "ossifying", maintain intrigue, give newcomers a chance. The best-6-of-8 formula removes the pressure of mandatory attendance.

5. **Snake seating** — balances tables, prevents "table of death" and "table for the weak" situations.

6. **Multi-table with per-table rating** — each table is an independent unit for rating purposes. Ratings update when a table closes, allowing flexible evening management.

---

## 7. Sources and Inspiration

- Elo rating system — [Wikipedia](https://en.wikipedia.org/wiki/Elo_rating_system)
- Generalized Elo for multiplayer games — [Towards Data Science](https://towardsdatascience.com/developing-a-generalized-elo-rating-system-for-multiplayer-games-b9b495e87802)
- Poker World Tour PSR/Elo — [PWT](http://poker.rheiagames.com/en/psr)
- Global Poker Index methodology — [GPI](https://www.globalpokerindex.com/about/)
- Bounty tournaments — [Upswing Poker](https://upswingpoker.com/knockout-bounty-tournaments-progressive-ko/)
- League point systems — [Home Poker Tourney](https://homepokertourney.org/poker-league-points-systems.htm)
- Recreational Elo for poker — [Medium / Mike Fowlds](https://mikefowlds.medium.com/a-rating-system-for-poker-508bb2ae3282)
