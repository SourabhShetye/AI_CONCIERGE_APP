import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { UtensilsCrossed, CalendarDays, ClipboardList, Receipt, Star, LogOut } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '@/contexts/AuthContext'
import { createCustomerWS } from '@/services/websocket'
import Menu from './Menu'
import Booking from './Booking'
import MyOrders from './MyOrders'
import Bill from './Bill'
import Feedback from './Feedback'
import { useState } from 'react'

const TABS = [
  { path: '/customer/menu',     label: 'Order',    icon: UtensilsCrossed },
  { path: '/customer/book',     label: 'Book',     icon: CalendarDays },
  { path: '/customer/orders',   label: 'Orders',   icon: ClipboardList },
  { path: '/customer/bill',     label: 'Bill',     icon: Receipt },
  { path: '/customer/feedback', label: 'Feedback', icon: Star },
]

export default function CustomerApp() {
  const { user, logout } = useAuth()
  const [restaurantName, setRestaurantName] = useState('Restaurant')
  const restaurantId = user?.restaurant_id || import.meta.env.VITE_RESTAURANT_ID
  useEffect(() => {
    // Fetch the restaurant name to show in the header
    fetch(`${import.meta.env.VITE_API_URL}/api/restaurant/${restaurantId}`)
      .then(r => r.json())
      .then(data => { if (data.name) setRestaurantName(data.name) })
      .catch(() => {}) // silently fail — fallback stays as 'Restaurant'
  }, [restaurantId])
  const navigate = useNavigate()
  const location = useLocation()

  // Connect WebSocket for real-time order updates
  useEffect(() => {
    if (!user) return
    const ws = createCustomerWS(user.user_id)

    const unsubscribe = ws.on((event) => {
      switch (event.type) {
        case 'order_ready': {
          const msg = (event.data as any).chat_message || '🔔 Your order is ready! Please collect it.'
          toast.success(msg, { duration: 8000 })
          window.dispatchEvent(new CustomEvent('chat_notification', { detail: { message: msg } }))
          break
        }
        case 'order_cancelled': {
          const msg = (event.data as any).chat_message || '✅ Your cancellation was approved.'
          toast.success(msg, { duration: 6000 })
          window.dispatchEvent(new CustomEvent('chat_notification', { detail: { message: msg } }))
          break
        }
        case 'modification_approved': {
          const msg = (event.data as any).chat_message || '✅ Your modification was approved.'
          toast.success(msg, { duration: 6000 })
          window.dispatchEvent(new CustomEvent('chat_notification', { detail: { message: msg } }))
          break
        }
        case 'modification_rejected': {
          const msg = (event.data as any).chat_message || '❌ Modification rejected. Original order stands.'
          toast.error(msg, { duration: 6000 })
          window.dispatchEvent(new CustomEvent('chat_notification', { detail: { message: msg } }))
          break
        }
        case 'cancellation_rejected': {
          const msg = (event.data as any).chat_message || '❌ Cancellation rejected. Your order is being prepared.'
          toast.error(msg, { duration: 6000 })
          window.dispatchEvent(new CustomEvent('chat_notification', { detail: { message: msg } }))
          break
        }
        case 'feedback_requested':
          toast('🌟 Your table has been closed. Please leave feedback!', {
            icon: '⭐',
            duration: 10000,
          })
          navigate('/customer/feedback')
          break
      }
    })

    return () => {
      unsubscribe()
      ws.disconnect()
    }
  }, [user?.user_id])

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col max-w-2xl mx-auto">
      {/* Top header */}
      <header className="bg-white border-b border-gray-100 px-4 py-3 flex items-center justify-between sticky top-0 z-10">
        <div>
          <h1 className="font-bold text-gray-900">🍽️ {restaurantName}</h1>
          {user && (
            <p className="text-xs text-gray-500">
              Hi, {user.name}
              {user.tags?.length ? ` · ${user.tags[0]}` : ''}
            </p>
          )}
        </div>
        <button onClick={handleLogout} className="text-gray-400 hover:text-red-500 transition-colors p-2">
          <LogOut size={20} />
        </button>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto pb-20">
        <Routes>
          <Route path="menu"     element={<Menu />} />
          <Route path="book"     element={<Booking />} />
          <Route path="orders"   element={<MyOrders />} />
          <Route path="bill"     element={<Bill />} />
          <Route path="feedback" element={<Feedback />} />
          <Route path="*"        element={<Navigate to="menu" replace />} />
        </Routes>
      </main>

      {/* Bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 flex max-w-2xl mx-auto">
        {TABS.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              className={`flex-1 flex flex-col items-center gap-1 py-3 transition-colors ${
                active ? 'text-primary-600' : 'text-gray-400'
              }`}
            >
              <Icon size={20} />
              <span className="text-[10px] font-medium">{label}</span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
