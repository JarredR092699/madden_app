# Madden 26 Franchise Tracker

A web app that receives franchise data from the Madden 26 Companion App and displays player stats, team records, and schedules.

## Quick Start

### 1. Install dependencies

```bash
cd madden_app
pip install -r requirements.txt
```

### 2. Start the server

```bash
python run.py
```

The server starts at `http://localhost:5000`. Visit `http://localhost:5000/docs` for the API docs.

### 3. Set up ngrok (so your phone can reach the server)

Install ngrok if you haven't:
```bash
brew install ngrok
```

In a **second terminal**, run:
```bash
ngrok http 5000
```

Copy the public URL (e.g., `https://abc123.ngrok-free.app`).

### 4. Export from the Companion App

1. Open the **Madden NFL 26 Companion App** on your phone
2. Go to **Franchises** and select your franchise
3. Tap **Export**
4. Paste the ngrok URL (e.g., `https://abc123.ngrok-free.app`)
5. Tap each export category (League Info, Rosters, Schedules, Stats)
6. Data will appear at `http://localhost:5000`

## Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Overview with export status and quick links |
| Standings | `/standings` | Team records grouped by division |
| Schedule | `/schedule` | Weekly matchups and scores |
| Roster | `/roster` | Player rosters filterable by team |
| Stats | `/stats` | Player stats (passing, rushing, receiving, defense, kicking, punting) |
| Export Log | `/exports` | Debug view of raw JSON payloads received |
| API Docs | `/docs` | Auto-generated Swagger UI |

## Notes

- **ngrok URL changes** each time you restart ngrok (free tier). You'll need to re-paste the URL in the Companion App.
- **Raw JSON is saved** to the `data/` folder as a backup. If field names are wrong, you can inspect the actual payloads at `/exports`.
- **Database** is stored in `madden.db` (SQLite). Delete it to start fresh.
- The field names in the parser are based on previous Madden versions. After your first real export, check `/exports` to see if any field names need adjusting in `app/services/parser.py`.
