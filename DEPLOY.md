# Deploying Cascade (GitHub + free hosting)

This walks you through: push to GitHub → deploy the backend → deploy the frontend →
set your secret key in the hosting dashboard (never in git).

Architecture: **frontend on Vercel** (static) + **backend on Render** (FastAPI).
Render is the reliable free choice for a Python web service. (A Vercel-only option for
the backend is noted at the end.)

---

## Part 1 — Push to GitHub

1. Create a new **empty** repo on github.com (no README), e.g. `cascade`.
2. From the project root (`SOP Project/`), run:

```bash
git init
git add .
git commit -m "Cascade: SOP-to-workflow compiler + deterministic runtime + agent"
git branch -M main
git remote add origin https://github.com/<your-username>/cascade.git
git push -u origin main
```

Your `.gitignore` already excludes secrets (`.env`), `node_modules/`, `.venv/`,
`__pycache__/`, and the local library data — so nothing sensitive is pushed.

---

## Part 2 — Deploy the backend (Render, free)

1. Go to https://render.com → sign in with GitHub.
2. **New + → Blueprint** → select your `cascade` repo. Render reads `backend/render.yaml`
   and creates the `cascade-backend` web service automatically.
   - (Or **New + → Web Service** manually: Root Directory `backend`,
     Build `pip install -r requirements.txt`,
     Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.)
3. In the service's **Environment** tab, add your secret:
   - `GEMINI_API_KEY = <your key>`  (get one free at https://aistudio.google.com/apikey)
   - `GEMINI_MODEL = gemini-2.5-flash`
   - `CORS_ORIGINS = *`  (or later, your frontend URL for tighter security)
4. Deploy. You'll get a URL like `https://cascade-backend.onrender.com`.
5. Test it: open `https://cascade-backend.onrender.com/health` — it should show
   `{"status":"ok","mode":"gemini"}` (or `mock` if you didn't set the key).

> Note: the free Render tier sleeps after inactivity; the first request after idle takes
> ~30s to wake. Fine for a demo.

---

## Part 3 — Deploy the frontend (Vercel, free)

1. Go to https://vercel.com → sign in with GitHub → **Add New → Project** → import `cascade`.
2. Set **Root Directory** = `frontend`.
3. Framework preset: **Vite** (auto-detected). Build `npm run build`, output `dist`.
4. Add an **Environment Variable**:
   - `VITE_API_URL = https://cascade-backend.onrender.com`  (your backend URL from Part 2)
5. Deploy. You'll get a URL like `https://cascade.vercel.app` — that's your shareable app.

> If you deploy the frontend before the backend, just redeploy after setting `VITE_API_URL`.

---

## Part 4 — Where the secret lives

- Your `GEMINI_API_KEY` is set **only in the Render dashboard** (Part 2, step 3), never in
  the code or git. The backend reads it via `get_settings()` → `os.getenv`.
- The frontend never sees the key — it only calls your backend.

---

## Alternative: backend on Vercel (Python serverless)

The repo includes `backend/vercel.json` + `backend/api/index.py` for this. In Vercel:
**Add New → Project → import repo → Root Directory `backend`**, then set `GEMINI_API_KEY`
in the project's env vars. Vercel serves the FastAPI app as a serverless function.
Use this only if you prefer everything on Vercel; Render is simpler for Python and avoids
serverless cold-start/timeout quirks.

---

## Quick post-deploy checklist
- [ ] `/health` on the backend returns `mode: gemini` (key is set).
- [ ] Frontend `VITE_API_URL` points at the backend URL.
- [ ] Compile a sample SOP → graph appears.
- [ ] Run a case → path highlights + trace shows.
- [ ] Toggle Agent mode → live think→act→observe loop runs.
