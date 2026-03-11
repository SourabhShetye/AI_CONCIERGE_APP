import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { ChefHat, LayoutGrid, CalendarDays, UtensilsCrossed, Users, Settings, LogOut } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '@/contexts/AuthContext'
import { createKitchenWS } from '@/services/websocket'
import KitchenDisplay from './KitchenDisplay'
import LiveTables from './LiveTables'
import BookingsManager from './BookingsManager'
import MenuManager from './MenuManager'
import CRM from './CRM'
import SettingsPanel from './SettingsPanel'

const ALL_TABS = [
  { path: '/staff/kitchen',   label: 'Kitchen', icon: ChefHat,         roles: ['admin','chef','manager'] },
  { path: '/staff/tables',    label: 'Tables',  icon: LayoutGrid,      roles: ['admin','manager'] },
  { path: '/staff/bookings',  label: 'Bookings',icon: CalendarDays,    roles: ['admin','manager'] },
  { path: '/staff/menu',      label: 'Menu',    icon: UtensilsCrossed, roles: ['admin','manager'] },
  { path: '/staff/crm',       label: 'CRM',     icon: Users,           roles: ['admin','manager'] },
  { path: '/staff/settings',  label: 'Settings',icon: Settings,        roles: ['admin'] },
]

export default function StaffApp() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const tabs = ALL_TABS.filter((t) => t.roles.includes(user?.role ?? ''))

  // Kitchen WebSocket - broadcasts new orders
  useEffect(() => {
    if (!user) return
    const ws = createKitchenWS(user.restaurant_id || import.meta.env.VITE_RESTAURANT_ID)
    const unsub = ws.on((event) => {
      if (event.type === 'new_order') {
        toast(`🔔 New order — Table ${(event.data as any).table_number}`, { icon: '🍳', duration: 6000 })
      }
      if (event.type === 'modification_request') {
        toast(`✏️ Modification requested for order`, { duration: 6000 })
      }
      if (event.type === 'cancellation_request') {
        toast(`❌ Cancellation requested`, { duration: 6000 })
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
        <button onClick={() => { logout(); navigate('/') }} className="text-gray-400 hover:text-red-500 p-2">
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

      {/* Content */}
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
    </div>
  )
}
