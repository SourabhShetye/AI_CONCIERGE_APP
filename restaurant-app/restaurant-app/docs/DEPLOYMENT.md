# 🚢 Deployment Guide

## Backend → Render.com

1. Push your code to GitHub

2. Go to [render.com](https://render.com) → New → Web Service

3. Connect your GitHub repo, set:
   - **Root directory:** `backend`
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

4. Add Environment Variables (from your `.env`):
   ```
   SUPABASE_URL
   SUPABASE_KEY
   GROQ_API_KEY
   JWT_SECRET
   DEFAULT_RESTAURANT_ID
   ALLOWED_ORIGINS=https://your-app.vercel.app
   ```

5. Deploy. Note your Render URL: `https://your-api.onrender.com`

---

## Frontend → Vercel

1. Go to [vercel.com](https://vercel.com) → New Project → Import your GitHub repo

2. Set:
   - **Root directory:** `frontend`
   - **Build command:** `npm run build`
   - **Output directory:** `dist`

3. Add Environment Variables:
   ```
   VITE_API_URL=https://your-api.onrender.com
   VITE_WS_URL=wss://your-api.onrender.com
   VITE_RESTAURANT_ID=your-restaurant-uuid
   ```
   > Note: Use `wss://` (secure WebSocket) for production, not `ws://`

4. Deploy. Your app is live at `https://your-app.vercel.app`

---

## Post-deployment checklist

- [ ] Update backend `ALLOWED_ORIGINS` to include your Vercel URL
- [ ] Re-deploy backend after updating CORS origins
- [ ] Test customer login from your phone
- [ ] Test staff kitchen display in a separate browser window
- [ ] Confirm WebSocket orders appear in real-time

---

## WebSocket on Render (important)

Render's free tier sleeps after 15 minutes of inactivity. This breaks WebSocket connections.
To prevent this:
- Upgrade to Render paid tier, **or**
- Use a cron service (e.g. cron-job.org) to ping `https://your-api.onrender.com/health` every 10 minutes
