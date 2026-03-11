# 🐛 Troubleshooting Guide

This guide shows the exact error, what caused it, and the exact code/config fix.

---

## Backend Errors

### ❌ `ValidationError: SUPABASE_URL field required`

**Cause:** `.env` file missing or not loaded.

**Fix:** Ensure `.env` exists in the `backend/` directory (not in `backend/app/`).
```bash
cd backend
cp .env.example .env
# Then fill in your values
```

---

### ❌ `groq.APIConnectionError: Connection error`

**Cause:** Invalid or missing `GROQ_API_KEY`.

**Fix:** Check your `.env`:
```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxx  # must start with gsk_
```
Get a free key at: https://console.groq.com

---

### ❌ `supabase.lib.errors.APIError: relation "user_sessions" does not exist`

**Cause:** Database tables not created yet.

**Fix:** Run the SQL from `docs/SETUP.md` Step 1 in your Supabase SQL Editor.

---

### ❌ `jose.exceptions.JWTError: Signature verification failed`

**Cause:** `JWT_SECRET` changed between token issuance and verification.

**Fix:** Keep `JWT_SECRET` consistent. In development, set it to any fixed string.
```env
JWT_SECRET=my-super-secret-dev-key-123
```
All existing tokens will be invalidated when you change this — users need to log in again.

---

### ❌ `fastapi.exceptions.RequestValidationError` on `/api/orders`

**Cause:** Customer not logged in (no JWT token in request), or request body missing fields.

**Fix - Frontend:** Ensure customer is logged in before placing order:
```typescript
// In api.ts, the interceptor reads from localStorage
// Make sure login() stores the token:
localStorage.setItem('token', authUser.access_token)
```

---

### ❌ CORS error: `Access to fetch blocked by CORS policy`

**Cause:** Frontend origin not in `ALLOWED_ORIGINS`.

**Fix:** In backend `.env`:
```env
ALLOWED_ORIGINS=http://localhost:5173,https://your-app.vercel.app
```
Restart the backend after changing `.env`.

---

### ❌ `TypeError: object is not subscriptable` in `order_service.py`

**Cause:** Groq returned an unexpected response format.

**Fix:** This is handled by `extract_json_from_text()`. If it still fails, check your Groq quota at console.groq.com. You may have hit the rate limit.

---

## Frontend Errors

### ❌ White screen / `ReferenceError: process is not defined`

**Cause:** Using `process.env` instead of `import.meta.env` in Vite.

**Fix:** In any frontend file, replace:
```typescript
// ❌ Wrong (CRA style)
process.env.REACT_APP_API_URL

// ✅ Correct (Vite style)
import.meta.env.VITE_API_URL
```

---

### ❌ `Failed to load menu` (network error)

**Cause:** Backend not running, or `VITE_API_URL` is wrong.

**Fix:**
1. Confirm backend is running: `curl http://localhost:8000/health`
2. Check `frontend/.env`:
   ```env
   VITE_API_URL=http://localhost:8000
   ```
3. Restart Vite dev server after changing `.env`: `npm run dev`

---

### ❌ WebSocket keeps disconnecting

**Cause:** Backend sleeping (Render free tier) or network issue.

**Fix - Dev:** Make sure backend is running: `uvicorn app.main:app --reload`

**Fix - Production:** Either upgrade Render tier or use polling fallback.
The WS client in `services/websocket.ts` already implements exponential backoff reconnection — it will keep trying automatically.

---

### ❌ Orders placed but not showing in kitchen

**Cause:** WebSocket for kitchen not connected, or wrong `restaurant_id`.

**Fix:** In `StaffApp.tsx`, the kitchen WS connects using:
```typescript
const restaurantId = user.restaurant_id || import.meta.env.VITE_RESTAURANT_ID
```
Ensure `VITE_RESTAURANT_ID` in `frontend/.env` matches `DEFAULT_RESTAURANT_ID` in `backend/.env`.

---

### ❌ "Name already registered" when trying to register

**Cause:** Customer with that name already exists in your restaurant.

**Fix:** Either:
- Use a different name
- Log in instead of registering
- Delete the existing row in Supabase `user_sessions` table for testing

---

### ❌ Booking error: "Bookings must be made at least 2 hours in advance"

**Cause:** The booking time you selected is less than 2 hours from now.

**Fix:** Select a time at least 2 hours from the current Dubai time (UTC+4). This is intentional business logic from `booking_service.py`.

---

## Database / Supabase Errors

### ❌ `duplicate key value violates unique constraint "staff_users_username_restaurant_id_key"`

**Cause:** Trying to create a staff user with a username that already exists for that restaurant.

**Fix:** Use a different username, or delete the existing user from Supabase dashboard.

---

### ❌ Orders returning `items: "[]"` (string instead of array)

**Cause:** Items stored as JSON string in DB, not parsed on retrieval.

**Fix:** Already handled in `main.py`:
```python
for o in orders:
    if isinstance(o.get("items"), str):
        o["items"] = json.loads(o["items"])
```
If you're seeing this issue, ensure you're using the latest `main.py`.
