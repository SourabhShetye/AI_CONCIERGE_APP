import { useState, useEffect } from 'react'
import { RefreshCw, X, Edit2, ChevronDown, ChevronUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { orderApi } from '@/services/api'
import type { Order } from '@/types'

const STATUS_LABELS: Record<string, string> = {
  pending:   '⏳ Pending',
  preparing: '👨‍🍳 Preparing',
  ready:     '✅ Ready',
  completed: '✔️ Completed',
  cancelled: '❌ Cancelled',
}

function groupOrdersByDate(orders: Order[]): Record<string, Order[]> {
  const groups: Record<string, Order[]> = {}
  for (const order of orders) {
    try {
      const d = new Date(order.created_at)
      const today = new Date()
      const yesterday = new Date()
      yesterday.setDate(today.getDate() - 1)

      let label: string
      if (d.toDateString() === today.toDateString()) {
        label = 'Today'
      } else if (d.toDateString() === yesterday.toDateString()) {
        label = 'Yesterday'
      } else {
        label = d.toLocaleDateString('en-GB', {
          weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
        })
      }
      if (!groups[label]) groups[label] = []
      groups[label].push(order)
    } catch {
      if (!groups['Other']) groups['Other'] = []
      groups['Other'].push(order)
    }
  }
  return groups
}

export default function MyOrders() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [modifyingId, setModifyingId] = useState<string | null>(null)
  const [modifyText, setModifyText] = useState('')
  const [collapsedDates, setCollapsedDates] = useState<Set<string>>(new Set())

  const fetchOrders = async () => {
    try {
      const res = await orderApi.getMyOrders()
      setOrders(res.data)
    } catch {
      toast.error('Failed to load orders')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchOrders()
    const interval = setInterval(fetchOrders, 5000)
    return () => clearInterval(interval)
  }, [])

  // Refresh immediately when user switches back to this tab
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') fetchOrders()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [])

  const handleCancel = async (id: string) => {
    try {
      await orderApi.cancelOrder(id)
      toast.success('Cancellation requested. Awaiting kitchen approval.')
      fetchOrders()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Cannot cancel this order')
    }
  }

  const handleModify = async (id: string) => {
    if (!modifyText.trim()) return
    try {
      const res = await orderApi.modifyOrder(id, modifyText)
      toast.success(res.data.detail)
      setModifyingId(null)
      setModifyText('')
      fetchOrders()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to modify order')
    }
  }

  const toggleDate = (dateLabel: string) => {
    setCollapsedDates(prev => {
      const next = new Set(prev)
      next.has(dateLabel) ? next.delete(dateLabel) : next.add(dateLabel)
      return next
    })
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">
      Loading orders...
    </div>
  )

  const grouped = groupOrdersByDate(orders)
  const dateKeys = Object.keys(grouped)

  // Separate active from past for display priority
  const activeStatuses = ['pending', 'preparing', 'ready']

  return (
    <div className="p-4 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">My Orders</h2>
        <button onClick={fetchOrders} className="text-gray-400 hover:text-primary-500">
          <RefreshCw size={18} />
        </button>
      </div>

      {orders.length === 0 && (
        <div className="card text-center py-12 text-gray-400">
          <p className="text-4xl mb-3">🍽️</p>
          <p>No orders yet. Start by ordering from the menu!</p>
        </div>
      )}

      {dateKeys.map((dateLabel) => {
        const dateOrders = grouped[dateLabel]
        const isCollapsed = collapsedDates.has(dateLabel)
        const hasActive = dateOrders.some(o => activeStatuses.includes(o.status))

        return (
          <div key={dateLabel}>
            {/* Date header */}
            <button
              onClick={() => toggleDate(dateLabel)}
              className="w-full flex items-center justify-between mb-2 group"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-gray-600">{dateLabel}</span>
                {hasActive && (
                  <span className="badge bg-green-100 text-green-700 text-xs">Active</span>
                )}
                <span className="text-xs text-gray-400">
                  {dateOrders.length} order{dateOrders.length > 1 ? 's' : ''}
                </span>
              </div>
              {isCollapsed
                ? <ChevronDown size={16} className="text-gray-400" />
                : <ChevronUp size={16} className="text-gray-400" />
              }
            </button>

            {/* Orders for this date */}
            {!isCollapsed && (
              <div className="space-y-3">
                {dateOrders.map((order) => (
                  <OrderCard
                    key={order.id}
                    order={order}
                    onCancel={handleCancel}
                    onModify={(id) => setModifyingId(id)}
                    modifyingId={modifyingId}
                    modifyText={modifyText}
                    setModifyText={setModifyText}
                    handleModify={handleModify}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function OrderCard({
  order, onCancel, onModify, modifyingId, modifyText, setModifyText, handleModify,
}: {
  order: Order
  onCancel: (id: string) => void
  onModify: (id: string) => void
  modifyingId: string | null
  modifyText: string
  setModifyText: (t: string) => void
  handleModify: (id: string) => void
}) {
  const canModify = ['pending', 'preparing'].includes(order.status)
  const canCancel = ['pending', 'preparing'].includes(order.status)
    && order.cancellation_status === 'none'
  const isModifying = modifyingId === order.id
  const isPast = ['completed', 'cancelled'].includes(order.status)

  return (
    <div className={`card mb-1 ${isPast ? 'opacity-70' : ''}`}>
      <div className="flex justify-between items-start mb-2">
        <div>
          <div className="flex items-center gap-2">
            {order.daily_order_number && (
              <span className="text-xs font-bold text-primary-600">
                #{order.daily_order_number}
              </span>
            )}
            <p className="text-sm font-semibold">Table {order.table_number}</p>
          </div>
          <p className="text-xs text-gray-400">
            {new Date(order.created_at).toLocaleTimeString([], {
              hour: '2-digit', minute: '2-digit'
            })}
          </p>
        </div>
        <span className={`status-${order.status}`}>{STATUS_LABELS[order.status]}</span>
      </div>

      {order.items.map((item, i) => (
        <div key={i} className="flex justify-between text-sm py-0.5">
          <span>{item.quantity}× {item.name}</span>
          <span className="text-gray-500">AED {item.total_price.toFixed(2)}</span>
        </div>
      ))}

      <div className="border-t border-gray-100 mt-2 pt-2 flex justify-between font-bold text-sm">
        <span>Total</span>
        <span>AED {order.price.toFixed(2)}</span>
      </div>

      {order.allergy_warnings?.length ? (
        <div className="mt-2 space-y-1">
          {order.allergy_warnings.map((w, i) => (
            <p key={i} className="text-xs text-orange-600">⚠️ {w}</p>
          ))}
        </div>
      ) : null}

      {order.cancellation_status === 'requested' && (
        <p className="text-xs text-yellow-600 mt-2">⏳ Cancellation requested — awaiting kitchen</p>
      )}
      {order.modification_status === 'requested' && (
        <p className="text-xs text-blue-600 mt-2">⏳ Modification requested — awaiting kitchen</p>
      )}

      {canModify && (
        <div className="mt-3">
          {isModifying ? (
            <div className="flex gap-2">
              <input
                className="input flex-1 text-sm"
                placeholder="e.g. Remove the fries"
                value={modifyText}
                onChange={(e) => setModifyText(e.target.value)}
              />
              <button onClick={() => handleModify(order.id)}
                className="btn-primary px-3 py-2 text-sm">OK</button>
              <button onClick={() => onModify('')}
                className="text-gray-400 px-2"><X size={16} /></button>
            </div>
          ) : (
            <div className="flex gap-3 mt-2">
              <button onClick={() => onModify(order.id)}
                className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
                <Edit2 size={12} /> Modify
              </button>
              {canCancel && (
                <button onClick={() => onCancel(order.id)}
                  className="text-xs text-red-500 hover:underline">
                  Cancel
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
