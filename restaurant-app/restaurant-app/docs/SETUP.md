# 🚀 Setup Guide - Restaurant AI Concierge

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | python.org |
| Node.js | 18+ | nodejs.org |
| Supabase account | Free tier | supabase.com |
| Groq API key | Free tier | console.groq.com |

---

## 1. Clone & Structure

```
restaurant-app/
├── backend/    ← FastAPI Python app
├── frontend/   ← React TypeScript app
└── docs/       ← Documentation
```

---

## 2. Supabase Database Setup

Log in to [supabase.com](https://supabase.com) → New Project → SQL Editor.
Run these SQL statements in order:

### Step 1: Create tables

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Restaurants
CREATE TABLE restaurants (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Menu items
CREATE TABLE menu_items (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  price NUMERIC(10,2) NOT NULL,
  category TEXT NOT NULL DEFAULT 'Mains',
  sold_out BOOLEAN DEFAULT FALSE,
  allergens TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Customer sessions (replaces Telegram user_sessions)
CREATE TABLE user_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  phone TEXT,
  pin_hash TEXT NOT NULL,
  allergies TEXT[] DEFAULT '{}',
  visit_count INTEGER DEFAULT 0,
  total_spend NUMERIC(10,2) DEFAULT 0,
  tags TEXT[] DEFAULT '{}',
  table_number TEXT,
  last_visit TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Staff users (new table for web app)
CREATE TABLE staff_users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
  username TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'chef', 'manager')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(username, restaurant_id)
);

-- Orders
CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
  user_id UUID REFERENCES user_sessions(id),
  customer_name TEXT,
  table_number TEXT,
  items JSONB NOT NULL DEFAULT '[]',
  price NUMERIC(10,2) DEFAULT 0,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending','preparing','ready','completed','cancelled')),
  cancellation_status TEXT DEFAULT 'none' CHECK (cancellation_status IN ('none','requested','approved','rejected')),
  modification_status TEXT DEFAULT 'none' CHECK (modification_status IN ('none','requested','approved','rejected')),
  allergy_warnings TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bookings
CREATE TABLE bookings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
  user_id UUID REFERENCES user_sessions(id),
  customer_name TEXT,
  party_size INTEGER NOT NULL,
  booking_time TIMESTAMPTZ NOT NULL,
  status TEXT DEFAULT 'confirmed' CHECK (status IN ('confirmed','cancelled','completed')),
  special_requests TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Feedback
CREATE TABLE feedback (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  restaurant_id UUID REFERENCES restaurants(id) ON DELETE CASCADE,
  user_id UUID REFERENCES user_sessions(id),
  ratings JSONB DEFAULT '{}',
  overall_rating INTEGER CHECK (overall_rating BETWEEN 1 AND 5),
  comments TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Restaurant policies / settings
CREATE TABLE restaurant_policies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  restaurant_id UUID UNIQUE REFERENCES restaurants(id) ON DELETE CASCADE,
  wifi_password TEXT,
  opening_hours TEXT,
  parking_info TEXT,
  ai_context TEXT,
  table_count INTEGER DEFAULT 20,
  max_party_size INTEGER DEFAULT 10,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Step 2: Seed your restaurant

```sql
-- Insert your restaurant (save the ID that gets generated!)
INSERT INTO restaurants (name) VALUES ('My Restaurant') RETURNING id;

-- Copy the UUID from the result, then insert a first staff admin user
-- You'll need to hash the password first using Python:
--   from passlib.context import CryptContext
--   pwd = CryptContext(schemes=["bcrypt"])
--   print(pwd.hash("your-admin-password"))

INSERT INTO staff_users (restaurant_id, username, password_hash, role)
VALUES ('<restaurant-uuid>', 'admin', '<bcrypt-hash>', 'admin');
```

> **Tip:** To generate the bcrypt hash quickly:
> ```bash
> cd backend
> pip install passlib[bcrypt]
> python -c "from passlib.context import CryptContext; c=CryptContext(schemes=['bcrypt']); print(c.hash('yourpassword'))"
> ```

### Step 3: Add sample menu items

```sql
INSERT INTO menu_items (restaurant_id, name, description, price, category) VALUES
('<restaurant-uuid>', 'Full Stack Burger', 'Double beef patty, cheese, pickles', 45.00, 'Mains'),
('<restaurant-uuid>', 'Caesar Salad', 'Romaine, parmesan, croutons', 35.00, 'Starters'),
('<restaurant-uuid>', 'Margherita Pizza', 'Tomato, mozzarella, basil', 55.00, 'Mains'),
('<restaurant-uuid>', 'Coca Cola', '330ml can', 12.00, 'Drinks'),
('<restaurant-uuid>', 'Chocolate Lava Cake', 'Warm chocolate cake with vanilla ice cream', 30.00, 'Desserts'),
('<restaurant-uuid>', 'Fish & Chips', 'Beer-battered cod, fries, tartar sauce', 65.00, 'Mains');
```

---

## 3. Backend Setup

```bash
cd backend

# Copy environment file
cp .env.example .env

# Edit .env with your credentials:
#   SUPABASE_URL=https://xxxxx.supabase.co
#   SUPABASE_KEY=eyJhbGci...  (use the "anon public" key from Supabase)
#   GROQ_API_KEY=gsk_xxxxx
#   JWT_SECRET=any-long-random-string-here
#   DEFAULT_RESTAURANT_ID=the-uuid-from-step-2
#   ALLOWED_ORIGINS=http://localhost:5173

# Create virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the backend
uvicorn app.main:app --reload --port 8000
```

✅ Backend is running at: `http://localhost:8000`
✅ API docs available at: `http://localhost:8000/docs`

---

## 4. Frontend Setup

```bash
cd frontend

# Copy environment file
cp .env.example .env

# Edit .env:
#   VITE_API_URL=http://localhost:8000
#   VITE_WS_URL=ws://localhost:8000
#   VITE_RESTAURANT_ID=your-restaurant-uuid

# Install dependencies
npm install

# Run development server
npm run dev
```

✅ Frontend is running at: `http://localhost:5173`

---

## 5. First Login Test

1. Open `http://localhost:5173`
2. Click **"I'm a Customer"** → Register with your name + PIN
3. Order something: *"I want 2 burgers and a coffee"*
4. Open a second tab → **"Staff Login"** → admin / your-password
5. Check **Kitchen Display** — your order should appear!

---

## Common Errors

### `SUPABASE_KEY` error on startup
Make sure you're using the **anon public** key, not the service role key.

### `groq.APIConnectionError`
Check your `GROQ_API_KEY` in `.env`. Get a free key at console.groq.com.

### CORS error in browser
Add `http://localhost:5173` to `ALLOWED_ORIGINS` in your backend `.env`.

### WebSocket not connecting
Make sure the backend is running. In production, use `wss://` not `ws://`.
