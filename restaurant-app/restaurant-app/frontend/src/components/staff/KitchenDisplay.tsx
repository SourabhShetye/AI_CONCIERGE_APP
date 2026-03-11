import { useState, useEffect } from 'react'
import { RefreshCw, CheckCircle, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { orderApi } from '@/services/api'
import type { Order } from '@/types'
import { formatDistanceToNow } from 'date-fns'

export default function KitchenDisplay() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  const fetchOrders = async () => {
    try {
      const res = await orderApi.getKitchenOrders()
      setOrders(res.data)
    } catch {
      toast.error('Failed to load orders')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchOrders()
    const interval = setInterval(fetchOrders, 10000)
    return () => clearInterval(interval)
  }, [])

  const action = async (fn: () => Promise<any>, successMsg: string) => {
    try {
      await fn()
      toast.success(successMsg)
      fetchOrders()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Action failed')
    }
  }

  if (loading) return <div className="text-center py-20 text-gray-400">Loading kitchen queue...</div>

  const pending = orders.filter((o) => o.status === 'pending')
  const preparing = orders.filter((o) => o.status === 'preparing')
  const modRequests = orders.filter((o) => o.modification_status === 'requested')
  const cancelRequests = orders.filter((o) => o.cancellation_status === 'requested')

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Kitchen Display</h2>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">Auto-refreshes every 10s</span>
          <button onClick={fetchOrders} className="text-gray-400 hover:text-primary-500">
            <RefreshCw size={18} />
          </button>
        </div>
      </div>

      {/* Action required: modifications */}
      {modRequests.length > 0 && (
        <div>
          <h3 className="font-semibold text-blue-700 mb-3">✏️ Modification Requests ({modRequests.length})</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {modRequests.map((o) => (
              <OrderCard
                key={o.id}
                order={o}
                accentClass="border-blue-300 bg-blue-50"
                actions={
                  <div className="flex gap-2">
                    <button onClick={() => action(() => orderApi.approveModification(o.id), 'Modification approved')} className="btn-primary flex-1 py-2 text-sm">
                      ✅ Approve
                    </button>
                    <button onClick={() => action(() => orderApi.rejectModification(o.id), 'Modification rejected')} className="flex-1 py-2 rounded-xl border-2 border-red-400 text-red-600 text-sm font-semibold hover:bg-red-50">
                      ❌ Reject
                    </button>
                  </div>
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* Action required: cancellations */}
      {cancelRequests.length > 0 && (
        <div>
          <h3 className="font-semibold text-red-700 mb-3">🚫 Cancellation Requests ({cancelRequests.length})</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cancelRequests.map((o) => (
              <OrderCard
                key={o.id}
                order={o}
                accentClass="border-red-300 bg-red-50"
                actions={
                  <div className="flex gap-2">
                    <button onClick={() => action(() => orderApi.approveCancellation(o.id), 'Cancellation approved')} className="btn-primary flex-1 py-2 text-sm bg-red-500 hover:bg-red-600">
                      ✅ Approve
                    </button>
                    <button onClick={() => action(() => orderApi.rejectCancellation(o.id), 'Cancellation rejected')} className="flex-1 py-2 rounded-xl border-2 border-gray-300 text-gray-600 text-sm font-semibold hover:bg-gray-50">
                      ❌ Reject
                    </button>
                  </div>
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* Pending orders */}
      {pending.length > 0 && (
        <div>
          <h3 className="font-semibold text-yellow-700 mb-3">⏳ New Orders ({pending.length})</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {pending.map((o) => (
              <OrderCard
                key={o.id}
                order={o}
                accentClass="border-yellow-300 bg-yellow-50"
                actions={
                  <button onClick={() => action(() => orderApi.markReady(o.id), 'Order marked ready!')} className="btn-primary w-full py-2 text-sm">
                    ✅ Mark Ready
                  </button>
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* Preparing */}
      {preparing.length > 0 && (
        <div>
          <h3 className="font-semibold text-blue-700 mb-3">👨‍🍳 Preparing ({preparing.length})</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {preparing.map((o) => (
              <OrderCard
                key={o.id}
                order={o}
                accentClass="border-blue-200"
                actions={
                  <button onClick={() => action(() => orderApi.markReady(o.id), 'Order ready!')} className="btn-primary w-full py-2 text-sm">
                    ✅ Mark Ready
                  </button>
                }
              />
            ))}
          </div>
        </div>
      )}

      {orders.length === 0 && (
        <div className="text-center py-20 text-gray-300">
          <div className="text-6xl mb-4">✅</div>
          <p className="text-lg">All caught up! No pending orders.</p>
        </div>
      )}
    </div>
  )
}

function OrderCard({ order, accentClass, actions }: { order: Order; accentClass: string; actions: React.ReactNode }) {
  return (
    <div className={`card border-2 ${accentClass} space-y-3`}>
      <div className="flex justify-between items-start">
        <div>
          <p className="font-bold text-lg">Table {order.table_number}</p>
          <p className="text-sm text-gray-600">{order.customer_name}</p>
        </div>
        <span className="text-xs text-gray-400">
          {formatDistanceToNow(new Date(order.created_at), { addSuffix: true })}
        </span>
      </div>

      <div className="space-y-1">
        {order.items.map((item, i) => (
          <div key={i} className="flex justify-between text-sm">
            <span><strong>{item.quantity}×</strong> {item.name}</span>
            <span className="text-gray-500">AED {item.total_price.toFixed(2)}</span>
          </div>
        ))}
        <div className="border-t border-gray-200 pt-1 flex justify-between font-bold text-sm">
          <span>Total</span>
          <span>AED {order.price.toFixed(2)}</span>
        </div>
      </div>

      {order.allergy_warnings?.length ? (
        <div className="bg-orange-100 rounded-lg p-2">
          {order.allergy_warnings.map((w, i) => (
            <p key={i} className="text-xs text-orange-700">⚠️ {w}</p>
          ))}
        </div>
      ) : null}

      {actions}
    </div>
  )
}
