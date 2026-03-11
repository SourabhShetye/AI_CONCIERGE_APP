import { useState, useEffect } from 'react'
import { RefreshCw, X, Edit2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { orderApi } from '@/services/api'
import type { Order } from '@/types'

const STATUS_LABELS: Record<string, string> = {
  pending: '⏳ Pending',
  preparing: '👨‍🍳 Preparing',
  ready: '✅ Ready',
  completed: '✔️ Completed',
  cancelled: '❌ Cancelled',
}

export default function MyOrders() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [modifyingId, setModifyingId] = useState<string | null>(null)
  const [modifyText, setModifyText] = useState('')

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
    const interval = setInterval(fetchOrders, 10000) // Refresh every 10s
    return () => clearInterval(interval)
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

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading orders...</div>

  const active = orders.filter((o) => !['completed', 'cancelled'].includes(o.status))
  const past = orders.filter((o) => ['completed', 'cancelled'].includes(o.status))

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

      {active.length > 0 && (
        <div>
          <h3 className="font-semibold text-gray-600 mb-3">Active Orders</h3>
          {active.map((order) => (
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

      {past.length > 0 && (
        <div>
          <h3 className="font-semibold text-gray-600 mb-3">Past Orders</h3>
          {past.map((order) => (
            <OrderCard key={order.id} order={order} onCancel={() => {}} onModify={() => {}} modifyingId={null} modifyText="" setModifyText={() => {}} handleModify={() => {}} />
          ))}
        </div>
      )}
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
  const canCancel = ['pending', 'preparing'].includes(order.status) && order.cancellation_status === 'none'
  const isModifying = modifyingId === order.id

  return (
    <div className="card mb-3">
      <div className="flex justify-between items-start mb-3">
        <div>
          <p className="font-semibold">Table {order.table_number}</p>
          <p className="text-xs text-gray-500">{new Date(order.created_at).toLocaleString()}</p>
        </div>
        <span className={`status-${order.status}`}>{STATUS_LABELS[order.status]}</span>
      </div>

      {order.items.map((item, i) => (
        <div key={i} className="flex justify-between text-sm py-1">
          <span>{item.quantity}× {item.name}</span>
          <span className="text-gray-500">AED {item.total_price.toFixed(2)}</span>
        </div>
      ))}

      <div className="border-t border-gray-100 mt-2 pt-2 flex justify-between font-bold">
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
              <button onClick={() => handleModify(order.id)} className="btn-primary px-3 py-2 text-sm">OK</button>
              <button onClick={() => onModify('')} className="text-gray-400 px-2"><X size={16} /></button>
            </div>
          ) : (
            <div className="flex gap-2 mt-2">
              <button onClick={() => onModify(order.id)} className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
                <Edit2 size={12} /> Modify
              </button>
              {canCancel && (
                <button onClick={() => onCancel(order.id)} className="text-xs text-red-500 hover:underline">
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
