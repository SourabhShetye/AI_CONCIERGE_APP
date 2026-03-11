import { useState, useEffect } from 'react'
import { RefreshCw, DollarSign } from 'lucide-react'
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
    if (!confirm(`Close Table ${tableNumber} and mark as paid?`)) return
    setClosing(tableNumber)
    try {
      await tableApi.closeTable(tableNumber)
      toast.success(`Table ${tableNumber} closed. Feedback requested from customers.`)
      fetchTables()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to close table')
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
        {tables.map((table) => (
          <div key={table.table_number} className="card">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-bold text-xl">Table {table.table_number}</h3>
              <span className="badge bg-green-100 text-green-700">{table.orders.length} order{table.orders.length > 1 ? 's' : ''}</span>
            </div>

            {table.orders.map((order) => (
              <div key={order.id} className="mb-3 pb-3 border-b border-gray-100 last:border-0">
                <p className="text-xs text-gray-400 mb-1">{order.customer_name} · <span className={`status-${order.status}`}>{order.status}</span></p>
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

            <button
              onClick={() => handleClose(table.table_number)}
              disabled={closing === table.table_number}
              className="btn-primary w-full mt-3 flex items-center justify-center gap-2"
            >
              <DollarSign size={16} />
              {closing === table.table_number ? 'Closing...' : 'Close Table & Request Payment'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
