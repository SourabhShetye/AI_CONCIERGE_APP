# 🍽️ Restaurant AI Concierge — Web App v2.0

A full-stack, production-ready restaurant management system with AI-powered ordering.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Tailwind CSS |
| Backend | FastAPI (Python 3.11) |
| Database | Supabase (PostgreSQL) |
| AI | Groq API (Llama 3.3 70B) |
| Real-time | WebSocket |
| Auth | JWT + bcrypt |

## Quick Start

```bash
# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install
cp .env.example .env   # fill in your keys
npm run dev
```

See `docs/SETUP.md` for the full setup guide including database SQL.

## Portals

| Portal | URL | Who |
|--------|-----|-----|
| Landing | / | Everyone |
| Customer | /customer | Diners (PIN auth) |
| Staff | /staff | Kitchen · Manager · Admin |

## Features

**Customer Portal:**
- AI natural language ordering: *"2 burgers and a coffee"*
- Visual menu with cart
- Real-time order status via WebSocket
- Table booking with smart availability
- Bill view
- Feedback / ratings
- Allergy warnings
- Personalised greetings & milestone rewards

**Staff Portal:**
- Kitchen Display System (live order queue)
- Modification & cancellation approval workflow
- Live tables grouped by table number
- One-click table close & payment
- CRM with VIP / Frequent Diner / Big Spender / Churn Risk tags
- Menu CRUD (add/edit/delete/sold-out toggle)
- Booking management
- AI context injection via Settings

## Docs

- `docs/SETUP.md` — Installation & database setup
- `docs/DEPLOYMENT.md` — Deploy to Vercel + Render
- `docs/TROUBLESHOOTING.md` — Common errors with exact fixes
