import { useState, useEffect, useCallback } from 'react'
import { Receipt, RefreshCw, ChevronDown, ChevronUp, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'

interface OrderItem {
  name: string
  quantity: number
  unit_price: number
  total_price: number
}

interface Order {
  id: string
  customer_name: string
  items: OrderItem[]
  price: number
  status: string
  daily_order_number?: number
  created_at: string
  table_number?: string
}

interface PastSession {
  date: string
  table_number: string
  orders: Order[]
  total: number
}

interface BillData {
  table_number: string | null
  active_orders: Order[]
  active_total: number
  is_paid: boolean
  past_sessions: PastSession[]
  lifetime_total: number
}

export default function Bill() {
  const { user } = useAuth()
  const [bill, setBill] = useState<BillData | null>(null)
  const [loading, setLoading] = useState(true)
  const [paid, setPaid] = useState(false)
  const [expandedSessions, setExpandedSessions] = useState<Set<string>>(new Set())

  const fetchBill = useCallback(async () => {
    try {
      const res = await api.get('/api/my-bill')
      setBill(res.data)
      if (res.data.is_paid && res.data.active_orders.length === 0) {
        // Don't auto-set paid — only set if explicitly closed via WebSocket
      }
    } catch (err: any) {
      if (err.response?.status === 404) {
        setPaid(true)
      } else {
        toast.error('Could not load bill')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchBill()
    const interval = setInterval(() => {
      if (!paid) fetchBill()
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchBill, paid])

  // Listen for table-closed WebSocket event
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.type === 'table_closed' || detail?.type === 'feedback_requested') {
        setPaid(true)
        fetchBill() // Refresh so past sessions update
        toast.success('Your bill has been processed. Thank you! 🙏')
      }
    }
    window.addEventListener('ws_event', handler)
    return () => window.removeEventListener('ws_event', handler)
  }, [fetchBill])

  const toggleSession = (key: string) => {
    setExpandedSessions(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm">Loading your bill...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-5">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Receipt size={22} /> My Bill
        </h2>
        <div className="flex items-center gap-2">
          {bill?.table_number && (
            <span className="badge bg-primary-100 text-primary-700">
              Table {bill.table_number}
            </span>
          )}
          <button onClick={fetchBill} className="text-gray-400 hover:text-primary-500">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* ── Current Active Bill ─────────────────────────────────────────── */}
      {paid ? (
        <div className="card text-center py-8">
          <div className="text-5xl mb-3">✅</div>
          <h3 className="font-bold text-gray-800">Bill Paid</h3>
          <p className="text-sm text-gray-500 mt-1">Thank you for dining with us!</p>
        </div>
      ) : bill && bill.active_orders.length > 0 ? (
        <div className="card border-primary-100">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-gray-800">Current Bill</h3>
            <span className="badge bg-green-100 text-green-700">Active</span>
          </div>

          {bill.active_orders.map((order) => (
            <div key={order.id} className="mb-3 pb-3 border-b border-gray-100 last:border-0">
              <div className="flex justify-between items-center mb-1">
                <p className="text-xs font-medium text-gray-500">
                  {order.daily_order_number ? `Order #${order.daily_order_number}` : 'Order'}
                  {' · '}{order.customer_name}
                </p>
                <span className={`status-${order.status} text-xs`}>{order.status}</span>
              </div>
              {order.items.map((item, i) => (
                <div key={i} className="flex justify-between text-sm py-0.5">
                  <span className="text-gray-700">{item.quantity}× {item.name}</span>
                  <span className="text-gray-500">AED {item.total_price.toFixed(2)}</span>
                </div>
              ))}
              <div className="flex justify-between text-xs font-medium text-gray-500 mt-1 pt-1 border-t border-gray-50">
                <span>Subtotal</span>
                <span>AED {order.price.toFixed(2)}</span>
              </div>
            </div>
          ))}

          <div className="flex justify-between font-bold text-xl pt-2 border-t-2 border-gray-200">
            <span>Total Due</span>
            <span className="text-primary-600">AED {bill.active_total.toFixed(2)}</span>
          </div>
          <p className="text-xs text-gray-400 mt-3 text-center">
            Ask your server to process payment · Updates automatically
          </p>
        </div>
      ) : (
        <div className="card text-center py-8 text-gray-400">
          <p className="text-4xl mb-3">🧾</p>
          <p className="font-medium">No active orders</p>
          <p className="text-sm mt-1">Orders will appear here once placed.</p>
        </div>
      )}

      {/* ── Past Bill History ───────────────────────────────────────────── */}
      {bill && bill.past_sessions.length > 0 && (
        <div>
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-gray-700 flex items-center gap-2">
              <Clock size={16} />
              Past Bills
            </h3>
            <span className="text-xs text-gray-500">
              Lifetime: AED {bill.lifetime_total.toFixed(2)}
            </span>
          </div>

          <div className="space-y-3">
            {bill.past_sessions.map((session, idx) => {
              const key = `${session.date}-${session.table_number}-${idx}`
              const isExpanded = expandedSessions.has(key)

              return (
                <div key={key} className="card border-gray-100">
                  {/* Session header — always visible */}
                  <button
                    onClick={() => toggleSession(key)}
                    className="w-full flex justify-between items-center"
                  >
                    <div className="text-left">
                      <p className="font-medium text-sm text-gray-800">{session.date}</p>
                      <p className="text-xs text-gray-500">
                        Table {session.table_number} · {session.orders.length} order{session.orders.length > 1 ? 's' : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-700">
                        AED {session.total.toFixed(2)}
                      </span>
                      {isExpanded
                        ? <ChevronUp size={16} className="text-gray-400" />
                        : <ChevronDown size={16} className="text-gray-400" />
                      }
                    </div>
                  </button>

                  {/* Session detail — expandable */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-gray-100 space-y-3">
                      {session.orders.map((order) => (
                        <div key={order.id}>
                          <p className="text-xs text-gray-400 mb-1">
                            {order.daily_order_number ? `Order #${order.daily_order_number}` : 'Order'}
                            {' · '}{new Date(order.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </p>
                          {order.items.map((item, i) => (
                            <div key={i} className="flex justify-between text-sm">
                              <span className="text-gray-600">{item.quantity}× {item.name}</span>
                              <span className="text-gray-500">AED {item.total_price.toFixed(2)}</span>
                            </div>
                          ))}
                        </div>
                      ))}
                      <div className="flex justify-between font-semibold text-sm pt-2 border-t border-gray-100">
                        <span>Session Total</span>
                        <span>AED {session.total.toFixed(2)}</span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
