// Bill.tsx
import { useState } from 'react'
import { Receipt } from 'lucide-react'
import toast from 'react-hot-toast'
import { tableApi } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'

export default function Bill() {
  const { user } = useAuth()
  const storedTable = localStorage.getItem(`table_${user?.user_id}`) || ''
  const [tableNumber, setTableNumber] = useState(storedTable)
  const [bill, setBill] = useState<{ orders: any[]; total: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const restaurantId = import.meta.env.VITE_RESTAURANT_ID

  const fetchBill = async () => {
    if (!tableNumber) return toast.error('Enter your table number')
    setLoading(true)
    try {
      const res = await tableApi.getBill(tableNumber, restaurantId)
      setBill(res.data)
    } catch {
      toast.error('Could not load bill')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-4 space-y-4">
      <h2 className="text-xl font-bold flex items-center gap-2"><Receipt size={22} /> My Bill</h2>

      <div className="card flex gap-3">
        <input
          className="input flex-1"
          placeholder="Table number"
          value={tableNumber}
          onChange={(e) => setTableNumber(e.target.value)}
        />
        <button onClick={fetchBill} disabled={loading} className="btn-primary">
          {loading ? '...' : 'View'}
        </button>
      </div>

      {bill && (
        <div className="card">
          <h3 className="font-bold mb-3">Table {tableNumber}</h3>
          {bill.orders.map((order: any) => (
            <div key={order.id} className="mb-3 pb-3 border-b border-gray-100 last:border-0">
              <p className="text-xs text-gray-400 mb-1">{new Date(order.created_at).toLocaleTimeString()}</p>
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
            <span>AED {bill.total.toFixed(2)}</span>
          </div>
          <p className="text-xs text-gray-400 mt-3 text-center">
            Ask your server to process payment when ready
          </p>
        </div>
      )}
    </div>
  )
}
