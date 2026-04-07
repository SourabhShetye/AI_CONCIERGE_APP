import { useState, useEffect, useCallback } from 'react'
import { Receipt, RefreshCw } from 'lucide-react'
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
}

interface BillData {
  table_number: string | null
  orders: Order[]
  total: number
  is_paid: boolean
}

export default function Bill() {
  const { user } = useAuth()
  const [bill, setBill] = useState<BillData | null>(null)
  const [loading, setLoading] = useState(true)
  const [paid, setPaid] = useState(false)

  const fetchBill = useCallback(async () => {
    try {
      const res = await api.get('/api/my-bill')
      setBill(res.data)
      // If no orders, table may have been closed
      if (!res.data.orders || res.data.orders.length === 0) {
        setPaid(true)
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
    // Auto-refresh every 15 seconds until paid
    const interval = setInterval(() => {
      if (!paid) fetchBill()
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchBill, paid])

  // Listen for table-closed WebSocket event
  useEffect(() => {
    const handler = (e: Event) => {
      const type = (e as CustomEvent).detail?.type
      if (type === 'table_closed') {
        setPaid(true)
        setBill(null)
        toast.success('Your bill has been processed. Thank you! 🙏')
      }
    }
    window.addEventListener('ws_event', handler)
    return () => window.removeEventListener('ws_event', handler)
  }, [])

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

  if (paid) {
    return (
      <div className="flex flex-col items-center justify-center h-64 p-4">
        <div className="text-6xl mb-4">✅</div>
        <h3 className="text-xl font-bold text-gray-800">Bill Paid</h3>
        <p className="text-gray-500 text-sm mt-2 text-center">
          Your table has been closed. Thank you for dining with us!
        </p>
      </div>
    )
  }

  if (!bill || bill.orders.length === 0) {
    return (
      <div className="p-4 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Receipt size={22} /> My Bill
          </h2>
          <button onClick={fetchBill} className="text-gray-400 hover:text-primary-500">
            <RefreshCw size={18} />
          </button>
        </div>
        <div className="card text-center py-12 text-gray-400">
          <p className="text-4xl mb-3">🧾</p>
          <p>No active orders yet.</p>
          <p className="text-sm mt-1">Orders will appear here once placed.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Receipt size={22} /> My Bill
        </h2>
        <div className="flex items-center gap-3">
          {bill.table_number && (
            <span className="badge bg-primary-100 text-primary-700">
              Table {bill.table_number}
            </span>
          )}
          <button
            onClick={fetchBill}
            className="text-gray-400 hover:text-primary-500"
            title="Refresh bill"
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </div>

      <div className="card">
        {bill.orders.map((order) => (
          <div key={order.id} className="mb-4 pb-4 border-b border-gray-100 last:border-0">
            <div className="flex justify-between items-center mb-2">
              <p className="text-xs font-semibold text-gray-500">
                {order.daily_order_number ? `Order #${order.daily_order_number}` : 'Order'}
                {' · '}{order.customer_name}
              </p>
              <span className={`status-${order.status} text-xs`}>{order.status}</span>
            </div>
            {order.items.map((item, i) => (
              <div key={i} className="flex justify-between text-sm py-0.5">
                <span className="text-gray-700">
                  {item.quantity}× {item.name}
                </span>
                <span className="text-gray-500">AED {item.total_price.toFixed(2)}</span>
              </div>
            ))}
            <div className="flex justify-between text-sm font-medium mt-1 pt-1 border-t border-gray-50">
              <span>Subtotal</span>
              <span>AED {order.price.toFixed(2)}</span>
            </div>
          </div>
        ))}

        <div className="flex justify-between font-bold text-xl mt-2 pt-3 border-t-2 border-gray-200">
          <span>Total</span>
          <span className="text-primary-600">AED {bill.total.toFixed(2)}</span>
        </div>

        <p className="text-xs text-gray-400 mt-4 text-center">
          Ask your server to process payment when ready.
          Your bill updates automatically as you order.
        </p>
      </div>
    </div>
  )
}
