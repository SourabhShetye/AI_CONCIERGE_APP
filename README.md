# 🍽️ Restaurant AI Concierge System

> A production-ready, multi-tenant restaurant management platform with AI-powered ordering, real-time kitchen display, and intelligent CRM — built as a complete alternative to human-operated POS systems.

<div align="center">

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Visit%20App-6366f1?style=for-the-badge)](https://ai-concierge-app-frontend-git-fe-ceb024-sourabhshetyes-projects.vercel.app/)
[![Backend API](https://img.shields.io/badge/Backend%20API-Render-22c55e?style=for-the-badge)](https://ai-concierge-app-backend.onrender.com)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

**[Customer Portal](https://ai-concierge-app-frontend-git-fe-ceb024-sourabhshetyes-projects.vercel.app/customer/login) · [Staff Portal](https://ai-concierge-app-frontend-git-fe-ceb024-sourabhshetyes-projects.vercel.app/staff/login) · [API Docs](https://ai-concierge-app-backend.onrender.com/docs)**

</div>

---

## 🎯 What This Is

A **full-stack SaaS restaurant platform** supporting multiple restaurants from a single deployment. Customers scan a QR code unique to their table, order food in natural language, track their order in real time, and pay — all without staff involvement until the food is ready. Staff get a live kitchen display, smart billing, booking management, and an AI operations assistant.

**This is not a prototype.** It handles concurrent multi-tenant data isolation, deterministic AI conversation flows, real-time WebSocket broadcasting, and production-grade authentication.

---

## ✨ Key Features

### Customer Experience
- 🤖 **Natural Language Ordering** — "2 burgers and a lemonade" → structured order → kitchen in ~3 seconds
- 📅 **Smart Table Booking** — Bin-packing algorithm assigns smallest available table that fits party
- 📊 **Live Order Tracking** — Real-time status via WebSocket (pending → preparing → ready)
- 🧾 **Automatic Bill** — Loads from session, no table number input needed, shows full history
- ⭐ **Feedback System** — One submission per session, updates CRM instantly

### Staff Portal
- 👨‍🍳 **Kitchen Display System** — Live order queue, modification/cancellation approval workflow
- 💰 **Live Tables & Billing** — Close table only when all orders marked ready (prevents premature close)
- 📋 **Bookings Manager** — Calendar view, confirm/cancel reservations
- 🍕 **Menu Manager** — CRUD, sold-out toggle, real-time availability
- 👥 **CRM with ARPU** — VIP/Frequent Diner/Big Spender/Churn Risk/Brand Ambassador tags, star ratings, revenue per visit
- 🤖 **Operations AI (Staff-only)** — Ask about delayed orders, busy dates, priority customers; send messages directly to customer tables
- ⚙️ **Table Inventory** — Configure physical tables with capacities for smart booking allocation
- 🔲 **QR Code Generator** — Per-restaurant, per-table QR codes for customer portal access

### Architecture
- 🏢 **True Multi-Tenancy** — 3-layer isolation: JWT scoping + application filtering + Supabase RLS
- ⚡ **Real-Time** — WebSocket channels per customer + per restaurant kitchen
- 🔒 **Secure** — bcrypt PINs, signed JWTs, service-role DB access, tab-isolated sessionStorage
- 📱 **Responsive** — Mobile-first, works on customer phones and staff tablets

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Vercel (Frontend)                     │
│  React 18 + TypeScript + Tailwind CSS + React Router    │
│                                                          │
│  /customer/*     Customer Portal (PIN auth)              │
│  /staff/*        Staff Portal (username/password)        │
│  ChatWidget      Floating AI bot (customer)              │
│  StaffChatWidget Floating AI bot (staff, purple)         │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTPS / WSS
┌──────────────────────────▼──────────────────────────────┐
│                   Render (Backend)                       │
│              FastAPI (Python 3.11) + Uvicorn            │
│                                                          │
│  /api/chat          Customer AI state machine           │
│  /api/staff/chat    Staff operational AI                │
│  /api/orders        Order CRUD + kitchen broadcast      │
│  /api/bookings      Smart table allocation              │
│  /ws/customer/{id}  Per-customer WebSocket              │
│  /ws/kitchen/{id}   Per-restaurant kitchen WebSocket    │
└──────┬───────────────────────────────┬──────────────────┘
       │                               │
┌──────▼──────┐               ┌────────▼────────┐
│  Supabase   │               │   Groq API      │
│ PostgreSQL  │               │                 │
│             │               │ Llama 3.3 70B   │
│ RLS enabled │               │ (ordering/chat) │
│ 10 tables   │               │                 │
│ Service key │               │                 │
│ for backend │               │                 │
└─────────────┘               └─────────────────┘
```

---

## 🗄️ Database Schema

```sql
restaurants         (id, name)
menu_items          (id, restaurant_id, name, description, price, category, sold_out, allergens[])
user_sessions       (id, restaurant_id, name, pin_hash, allergies[], visit_count,
                     total_spend, tags[], average_rating, last_feedback_comment)
staff_users         (id, restaurant_id, username, password_hash, role)
orders              (id, restaurant_id, user_id, table_number, items JSONB, price,
                     status, cancellation_status, modification_status,
                     daily_order_number, modification_text)
bookings            (id, restaurant_id, user_id, party_size, booking_time,
                     status, assigned_table_id, assigned_table_number)
feedback            (id, restaurant_id, user_id, overall_rating, comments)
restaurant_policies (id, restaurant_id, wifi_password, opening_hours, ai_context,
                     table_count, max_party_size)
tables_inventory    (id, restaurant_id, table_number, capacity, is_active)
order_number_sequences (id, restaurant_id, date, last_number)  -- resets daily
```

---

## 🧠 AI Architecture

### Two-Call Ordering Pipeline
```
User: "2 burgers and a lemonade"
        │
        ├─ Call 1 (temp=0.7): Conversational response
        │   "Great choice! 2 Full Stack Burgers + Fresh Lemonade = AED 108. Anything else?"
        │
        └─ Call 2 (temp=0.1): Structured extraction
            {"items": [{"name": "Full Stack Burger", "quantity": 2, ...}], "total": 108.0}
                │
                └─ Price OVERRIDDEN from DB (AI cannot hallucinate prices)
```

### Chat State Machine (Cancel/Modify Flows)
```
Customer: "cancel order"
        │
[State: null] → Detect intent → Show order list
        │         (no AI)
[State: cancel_selection] → Customer picks order
        │
[State: cancel_type_selection] → "full" or "partial"?
        │
[State: cancel_item_selection] → Which items to remove?
        │
→ Send to kitchen for approval → WebSocket notifies customer of decision
```
*The AI is bypassed entirely for cancel/modify flows — deterministic logic only.*

### Bin-Packing Table Allocation
```python
# Party of 3 arrives. Tables: [2-seat, 4-seat, 6-seat, 8-seat]
# Find smallest table >= party_size that isn't already booked
available.sort(key=lambda t: t["capacity"])  # [4, 6, 8]
best_table = available[0]  # Assigns 4-seat, not 6 or 8
```

---

## 📁 Project Structure

```
restaurant-app/
├── backend/
│   ├── app/
│   │   ├── main.py              # All API routes + WebSocket endpoints
│   │   ├── chat_service.py      # Customer AI state machine
│   │   ├── staff_chat_service.py # Staff operational AI
│   │   ├── order_service.py     # Groq AI order parsing + fuzzy matching
│   │   ├── booking_service.py   # Smart table allocation + validation
│   │   ├── auth.py              # JWT + bcrypt
│   │   ├── crm.py               # Tag computation + ARPU
│   │   └── websocket.py         # Real-time connection manager
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── customer/        # Login, Menu, Orders, Booking, Bill, Feedback
│       │   └── staff/           # Kitchen, Tables, Bookings, Menu, CRM, Settings
│       ├── contexts/            # AuthContext, CartContext
│       └── services/            # api.ts (Axios), websocket.ts
└── docs/
    ├── SETUP.md                 # Full install + SQL guide
    ├── DEPLOYMENT.md            # Vercel + Render steps
    └── TROUBLESHOOTING.md       # Common errors + exact fixes
```

---

## 🔐 Demo Credentials

> **Live Demo:** [your-app.vercel.app]([https://your-app.vercel.app](https://ai-concierge-app-frontend-git-fe-ceb024-sourabhshetyes-projects.vercel.app)

| Portal | Credentials |
|--------|-------------|
| Customer | Register with any name + 4-digit PIN at the login page |
| Staff (Admin) | Username: `admin` · Password: `12345` |

**Test restaurants available:**
- My Restaurant - Default Option
- 🍔 The Tech Bistro 
- 🌯 Cloud Kitchen Dubai
- 🏙️ The Rooftop Grill

---

## 🛠️ Technical Decisions & Trade-offs

| Decision | Why | Trade-off |
|----------|-----|-----------|
| Groq over OpenAI | 10x faster inference via LPUs | Fewer model options |
| sessionStorage over localStorage | Tab isolation (customer + staff in separate tabs) | Cleared on tab close |
| Two AI calls per order | Separates conversation from data extraction | 2x Groq API cost |
| State machine for cancel/modify | 100% deterministic, AI bypassed | More code to maintain |
| Service role key for backend | Bypasses RLS for flexibility | Must trust all backend code |
| Daily order numbers | Human-readable for kitchen staff | Race condition at high concurrency |

---

## 📊 Performance Characteristics

- **Order placement** (chatbot → kitchen notification): ~1-3 seconds
- **WebSocket latency** (order ready → customer notification): <100ms
- **Concurrent users**: Tested with 3 restaurants, multiple tables simultaneously
- **AI response time**: ~800ms-1.5s (Groq LPU inference)

---

## 🗺️ Roadmap

- [ ] PostgreSQL advisory locks for booking race condition (production fix)
- [ ] pgvector semantic search for per-restaurant AI context
- [ ] Payment gateway integration (Stripe)
- [ ] Analytics dashboard (revenue charts, peak hours)
- [ ] Multi-language support
- [ ] Mobile app (React Native)

---

## 👨‍💻 Author

**Sourabh Shetye** — Final Year CS Student

Built as a complete ground-up rebuild of a Telegram-based restaurant bot prototype, demonstrating full-stack AI engineering with production-grade architecture.

[![GitHub](https://img.shields.io/badge/GitHub-SourabhShetye-181717?style=flat&logo=github)](https://github.com/SourabhShetye)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat&logo=linkedin)](https://www.linkedin.com/in/sourabh-shetye-36b9282b4)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
<sub>Built with FastAPI · React · Supabase · Groq AI · WebSockets</sub>
</div>
