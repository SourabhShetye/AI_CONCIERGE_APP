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

const TABS = [
  { path: '/customer/menu',     label: 'Order',    icon: UtensilsCrossed },
  { path: '/customer/book',     label: 'Book',     icon: CalendarDays },
  { path: '/customer/orders',   label: 'Orders',   icon: ClipboardList },
  { path: '/customer/bill',     label: 'Bill',     icon: Receipt },
  { path: '/customer/feedback', label: 'Feedback', icon: Star },
]

export default function CustomerApp() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // Connect WebSocket for real-time order updates
  useEffect(() => {
    if (!user) return
    const ws = createCustomerWS(user.user_id)

    const unsubscribe = ws.on((event) => {
      switch (event.type) {
        case 'order_ready':
          toast.success('🔔 Your order is ready! Please collect it.', { duration: 8000 })
          break
        case 'order_cancelled':
          toast.error('Your order cancellation was approved.')
          break
        case 'modification_approved':
          toast.success('✅ Your order modification was approved.')
          break
        case 'modification_rejected':
          toast.error('❌ Modification rejected. Original order stands.')
          break
        case 'cancellation_rejected':
          toast.error('❌ Cancellation rejected. Your order is being prepared.')
          break
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
          <h1 className="font-bold text-gray-900">🍽️ Restaurant</h1>
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
