# FOODWISE API (Python + FastAPI)

Backend for the FOODWISE React app. It follows `API.md` in the project root,
so the frontend only needs `VITE_API_URL` set to this API's address.

```
backend/
  app/
    main.py        all API routes
    models.py      database tables (field names match the React app)
    households.py  create, join and leave households
    security.py    passwords (bcrypt) and login tokens (JWT)
    ai.py          photo scan and recipe ideas (Claude API)
    config.py      settings from environment variables
    database.py    database connection
  tests/           automated tests (pytest)
  requirements.txt
  render.yaml      optional Render setup
```

## 1. Run it on your laptop

You need Python 3.11 or newer.

```bash
cd backend
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Mac / Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs to see and try every endpoint.
Without `DATABASE_URL`, data is saved in a local file `foodwise.db`.

To connect the React app locally, create `.env` in the project root:
```
VITE_API_URL=http://localhost:8000
```
then run `npm run dev`.

Run the tests:
```bash
pip install -r requirements-dev.txt
python -m pytest
```

## 2. Create the database (Supabase, free)

The free database on Supabase does not expire, unlike some free hosts.

1. Go to https://supabase.com, sign in, click **New project**.
   Choose region **Southeast Asia (Singapore)** and set a database password. Save it.
2. When the project is ready, click **Connect** at the top.
3. Under **Session pooler**, copy the connection string. It looks like:
   `postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
4. Replace `[YOUR-PASSWORD]` with your database password.
   If the password has symbols like `@`, `#` or `/`, it is easier to reset it to letters and numbers only.

Use the **Session pooler** string, not "Direct connection": Render can't reach the direct one.
You don't need to create tables; the API creates them on first start.

## 3. Put the API online (Render, free)

1. Push this project (including the `backend` folder) to GitHub.
2. Go to https://render.com, sign in with GitHub, click **New > Web Service**, pick the `foodwise` repo.
3. Fill in:
   - **Root Directory:** `backend`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Region:** Singapore
   - **Instance type:** Free
4. Under **Environment Variables**, add:

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | the Supabase Session pooler string |
   | `JWT_SECRET` | a long random string (mash the keyboard, 40+ characters) |
   | `ALLOWED_ORIGINS` | `https://foodwise-murex.vercel.app,http://localhost:5173` |
   | `PYTHON_VERSION` | `3.12.8` |
   | `ANTHROPIC_API_KEY` | optional, for AI features (see step 5) |

5. Click **Create Web Service**. When it's live, open
   `https://<your-service>.onrender.com/health`. You should see `{"status":"ok"}`.

## 4. Connect the Vercel frontend

1. Vercel dashboard > your `foodwise` project > **Settings > Environment Variables**.
2. Add `VITE_API_URL` = `https://<your-service>.onrender.com` (no slash at the end).
3. **Deployments** > the latest one > **Redeploy**. Vite reads the variable at build time,
   so a redeploy is required.

Open https://foodwise-murex.vercel.app: the login screen now asks for a password,
and data is saved in the database.

## 5. AI features (optional, paid per use)

Photo scan and AI recipes call the Claude API. Create a key at https://console.anthropic.com
(add credit to your account), then set `ANTHROPIC_API_KEY` on Render.
Without a key the rest of the app works normally; the AI buttons show
"AI features are not set up yet."

## Good to know

- **Free Render services sleep after 15 minutes without visits**, and the first request
  then takes about a minute. Before a demo, open `/health` a few minutes early.
  To keep it awake, add a free monitor at https://cron-job.org that opens `/health` every 10 minutes.
- **Sign up and log in use the same endpoint.** The first login with a new email creates the
  account (password at least 6 characters).
- **Every user has a household.** New users get their own; joining with a code moves them into
  a housemate's household and shares all data live (refresh to see others' changes).
- Never put `.env` or real keys in GitHub. `.gitignore` already excludes `.env`.

## Deploy with Docker (DigitalOcean droplet)

`docker-compose.yml` runs the API and its own PostgreSQL. Both ports are bound to
`127.0.0.1` only, so they are reachable from Nginx on the droplet but not from the internet.

```bash
cd /opt/foodwise/backend
cp .env.docker.example .env   # then fill in the passwords
docker compose up -d --build
curl http://127.0.0.1:8001/health
```

Update after `git pull`: `docker compose up -d --build`
Backup: `docker compose exec -T db pg_dump -U foodwise foodwise > backup.sql`
Restore: `docker compose exec -T db psql -U foodwise foodwise < backup.sql`
