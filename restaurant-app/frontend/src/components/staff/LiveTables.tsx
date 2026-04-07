import { useState, useEffect } from 'react'
import { RefreshCw, DollarSign, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import { tableApi } from '@/services/api'
import type { TableSummary } from '@/types'

export default function LiveTables() {
  const [tables, setTables] = useState<TableSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [closing, setClosing] = useState<string | null>(null)

  const fetchTables = async () => {
    try {
      const res = await tableApi.getLiveTables()
      setTables(res.data)
    } catch {
      toast.error('Failed to load tables')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTables()
    const interval = setInterval(fetchTables, 15000)
    return () => clearInterval(interval)
  }, [])

  const handleClose = async (tableNumber: string) => {
    if (!confirm(`Close Table ${tableNumber} and mark as paid?\n\nMake sure all orders are marked Ready first.`)) return
    setClosing(tableNumber)
    try {
      const res = await tableApi.closeTable(tableNumber)
      toast.success(res.data?.detail || `Table ${tableNumber} closed.`)
      fetchTables()
    } catch (err: any) {
      // Show the exact backend error — includes which orders are blocking
      const detail = err.response?.data?.detail || 'Failed to close table'
      toast.error(detail, { duration: 6000 })
    } finally {
      setClosing(null)
    }
  }

  if (loading) return <div className="text-center py-20 text-gray-400">Loading tables...</div>

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Live Tables & Billing</h2>
        <button onClick={fetchTables} className="text-gray-400 hover:text-primary-500">
          <RefreshCw size={18} />
        </button>
      </div>

      {tables.length === 0 && (
        <div className="text-center py-20 text-gray-300">
          <div className="text-6xl mb-4">🪑</div>
          <p>No active tables right now.</p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {tables.map((table) => {
          // Check if any orders are still pending/preparing (blocking close)
          const blockingOrders = table.orders.filter(
            (o: any) => o.status === 'pending' || o.status === 'preparing'
          )
          const canClose = blockingOrders.length === 0
          const allOrders = table.orders

          return (
            <div key={table.table_number} className="card">
              <div className="flex justify-between items-center mb-3">
                <h3 className="font-bold text-xl">Table {table.table_number}</h3>
                <span className="badge bg-green-100 text-green-700">
                  {allOrders.length} order{allOrders.length > 1 ? 's' : ''}
                </span>
              </div>

              {allOrders.map((order: any) => (
                <div key={order.id} className="mb-3 pb-3 border-b border-gray-100 last:border-0">
                  <p className="text-xs text-gray-400 mb-1">
                    {order.daily_order_number ? `#${order.daily_order_number} · ` : ''}
                    {order.customer_name} ·{' '}
                    <span className={`status-${order.status}`}>{order.status}</span>
                  </p>
                  {order.items.map((item: any, i: number) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span>{item.quantity}× {item.name}</span>
                      <span>AED {item.total_price.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              ))}

              <div className="flex justify-between font-bold text-lg mt-2 pt-2 border-t border-gray-200">
                <span>Total</span>
                <span>AED {table.total.toFixed(2)}</span>
              </div>

              {/* Warning if orders still in kitchen */}
              {!canClose && (
                <div className="mt-3 flex items-start gap-2 bg-yellow-50 border border-yellow-200 rounded-xl p-3">
                  <AlertTriangle size={16} className="text-yellow-600 mt-0.5 shrink-0" />
                  <p className="text-xs text-yellow-700">
                    {blockingOrders.length} order(s) still in kitchen ({blockingOrders.map((o: any) => o.status).join(', ')}).
                    Mark all as Ready before closing.
                  </p>
                </div>
              )}

              <button
                onClick={() => handleClose(table.table_number)}
                disabled={closing === table.table_number || !canClose}
                className={`w-full mt-3 flex items-center justify-center gap-2 py-3 rounded-xl font-semibold transition-all ${
                  canClose
                    ? 'btn-primary'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                }`}
                title={canClose ? 'Close table and process payment' : 'Mark all orders Ready first'}
              >
                <DollarSign size={16} />
                {closing === table.table_number
                  ? 'Closing...'
                  : canClose
                    ? 'Close Table & Process Payment'
                    : 'Mark All Ready First'
                }
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
