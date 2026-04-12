import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState, useRef } from 'react'
import { ChefHat, LayoutGrid, CalendarDays, UtensilsCrossed, Users, Settings, LogOut, Bot, X, Send, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '@/contexts/AuthContext'
import { createKitchenWS } from '@/services/websocket'
import { api } from '@/services/api'
import KitchenDisplay from './KitchenDisplay'
import LiveTables from './LiveTables'
import BookingsManager from './BookingsManager'
import MenuManager from './MenuManager'
import CRM from './CRM'
import SettingsPanel from './SettingsPanel'

// ── Staff AI floating chat ────────────────────────────────────────────────────

interface StaffMessage {
  role: 'user' | 'assistant'
  content: string
}

const QUICK_PROMPTS = [
  'Which orders are delayed?',
  'Who are priority customers?',
  'Busiest booking dates?',
  'Which dishes are sold out?',
  "Send Table 5: Kitchen closes in 30 mins",
]

function StaffChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<StaffMessage[]>([{
    role: 'assistant',
    content: "Hi! I'm your operations assistant. Ask me about orders, bookings, customers, or send table messages.",
  }])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text: string) => {
    if (!text.trim() || loading) return
    const userMsg: StaffMessage = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    try {
      const res = await api.post('/api/staff/chat', {
        message: text,
        conversation_history: messages.slice(-8),
      })
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }])
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: err.response?.data?.detail || 'Something went wrong. Please try again.',
      }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Floating button — bottom right, above page content */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-purple-600 to-purple-800 text-white shadow-lg hover:shadow-xl hover:scale-105 transition-all flex items-center justify-center"
          title="Operations AI Assistant"
        >
          <Bot size={22} />
        </button>
      )}

      {/* Chat panel — side drawer on desktop, bottom sheet on mobile */}
      {open && (
        <div className="fixed inset-0 z-50 pointer-events-none">
          {/* Backdrop for mobile only */}
          <div
            className="absolute inset-0 bg-black/20 sm:hidden pointer-events-auto"
            onClick={() => setOpen(false)}
          />

          {/* Panel — right side on desktop, bottom on mobile */}
          <div className="
            absolute pointer-events-auto
            bottom-0 right-0
            w-full sm:w-[400px] sm:bottom-4 sm:right-4
            h-[85vh] sm:h-[calc(100vh-80px)] sm:max-h-[680px]
            bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl
            flex flex-col
            sm:border sm:border-gray-100
          ">
            {/* Header */}
            <div className="bg-gradient-to-r from-purple-600 to-purple-800 text-white px-5 py-4 rounded-t-3xl sm:rounded-t-2xl flex justify-between items-center flex-shrink-0">
              <div className="flex items-center gap-2">
                <Bot size={18} />
                <div>
                  <p className="font-bold text-sm">Operations AI</p>
                  <p className="text-xs text-white/70">Real-time restaurant intelligence</p>
                </div>
              </div>
              <div className="flex gap-3 items-center">
                <button
                  onClick={() => setMessages([{ role: 'assistant', content: "Chat cleared. How can I help?" }])}
                  className="text-xs text-white/60 hover:text-white"
                >
                  <RefreshCw size={14} />
                </button>
                <button onClick={() => setOpen(false)} className="hover:opacity-70">
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Quick prompts */}
            <div className="flex gap-2 px-3 py-2 overflow-x-auto border-b border-gray-100 flex-shrink-0 scrollbar-hide">
              {QUICK_PROMPTS.map((p, i) => (
                <button
                  key={i}
                  onClick={() => send(p)}
                  disabled={loading}
                  className="px-3 py-1.5 bg-purple-50 hover:bg-purple-100 text-purple-700 rounded-xl text-xs font-medium whitespace-nowrap flex-shrink-0 transition-all border border-purple-100"
                >
                  {p}
                </button>
              ))}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && (
                    <div className="w-6 h-6 rounded-md bg-purple-100 flex items-center justify-center mr-2 mt-1 flex-shrink-0">
                      <Bot size={12} className="text-purple-600" />
                    </div>
                  )}
                  <div className={`max-w-[85%] px-3 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-line ${
                    msg.role === 'user'
                      ? 'bg-purple-600 text-white rounded-br-sm'
                      : 'bg-gray-100 text-gray-800 rounded-bl-sm'
                  }`}>
                    {msg.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="w-6 h-6 rounded-md bg-purple-100 flex items-center justify-center mr-2 mt-1">
                    <Bot size={12} className="text-purple-600" />
                  </div>
                  <div className="bg-gray-100 px-4 py-3 rounded-2xl rounded-bl-sm flex gap-1">
                    {[0,1,2].map(i => (
                      <div key={i} className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${i * 150}ms` }} />
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t border-gray-100 flex gap-2 flex-shrink-0">
              <input
                className="input flex-1 text-sm"
                placeholder="Ask about orders, bookings, or send table messages..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && send(input)}
              />
              <button
                onClick={() => send(input)}
                disabled={loading}
                className="w-10 h-10 rounded-xl bg-purple-600 text-white flex items-center justify-center hover:bg-purple-700 transition-colors flex-shrink-0"
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ── Main Staff App ─────────────────────────────────────────────────────────────

const ALL_TABS = [
  { path: '/staff/kitchen',   label: 'Kitchen',  icon: ChefHat,         roles: ['admin','chef','manager'] },
  { path: '/staff/tables',    label: 'Tables',   icon: LayoutGrid,      roles: ['admin','manager'] },
  { path: '/staff/bookings',  label: 'Bookings', icon: CalendarDays,    roles: ['admin','manager'] },
  { path: '/staff/menu',      label: 'Menu',     icon: UtensilsCrossed, roles: ['admin','manager'] },
  { path: '/staff/crm',       label: 'CRM',      icon: Users,           roles: ['admin','manager'] },
  { path: '/staff/settings',  label: 'Settings', icon: Settings,        roles: ['admin'] },
  // No AI tab — AI is the floating button
]

export default function StaffApp() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const tabs = ALL_TABS.filter(t => t.roles.includes(user?.role ?? ''))

  // Kitchen WebSocket — broadcasts new orders
  useEffect(() => {
    if (!user) return
    const ws = createKitchenWS(user.restaurant_id || import.meta.env.VITE_RESTAURANT_ID)
    const unsub = ws.on((event) => {
      if (event.type === 'new_order') {
        toast(`🔔 New order — Table ${(event.data as any).table_number}`, { icon: '🍳', duration: 6000 })
      }
      if (event.type === 'modification_request') {
        toast('✏️ Modification requested', { duration: 6000 })
      }
      if (event.type === 'cancellation_request') {
        toast('❌ Cancellation requested', { duration: 6000 })
      }
    })
    return () => { unsub(); ws.disconnect() }
  }, [user?.user_id])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top header */}
      <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🍽️</span>
          <div>
            <h1 className="font-bold text-gray-900 text-sm">Restaurant Staff</h1>
            <p className="text-xs text-gray-500 capitalize">{user?.role} · {user?.name}</p>
          </div>
        </div>
        <button
          onClick={() => { logout(); navigate('/') }}
          className="text-gray-400 hover:text-red-500 p-2"
        >
          <LogOut size={20} />
        </button>
      </header>

      {/* Tab bar */}
      <div className="bg-white border-b border-gray-100 px-2 flex gap-1 overflow-x-auto sticky top-[57px] z-10">
        {tabs.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-all ${
                active
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <Icon size={16} />
              {label}
            </button>
          )
        })}
      </div>

      {/* Content — right padding on desktop to make room for chat panel when open */}
      <main className="p-4 md:p-6 max-w-7xl mx-auto">
        <Routes>
          <Route path="kitchen"  element={<KitchenDisplay />} />
          <Route path="tables"   element={<LiveTables />} />
          <Route path="bookings" element={<BookingsManager />} />
          <Route path="menu"     element={<MenuManager />} />
          <Route path="crm"      element={<CRM />} />
          <Route path="settings" element={<SettingsPanel />} />
          <Route path="*"        element={<Navigate to="kitchen" replace />} />
        </Routes>
      </main>

      {/* Staff AI floating button — purple to distinguish from customer bot */}
      <StaffChatWidget />
    </div>
  )
}
