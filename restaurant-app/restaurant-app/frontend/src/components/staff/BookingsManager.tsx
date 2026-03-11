// BookingsManager.tsx
import { useState, useEffect } from 'react'
import { CheckCircle, X, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { bookingApi } from '@/services/api'
import type { Booking } from '@/types'
import { format, parseISO } from 'date-fns'

export default function BookingsManager() {
  const [bookings, setBookings] = useState<Booking[]>([])
  const [loading, setLoading] = useState(true)

  const fetch = async () => {
    try {
      const res = await bookingApi.getStaffBookings()
      setBookings(res.data)
    } catch { toast.error('Failed to load bookings') }
    finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [])

  const confirm = async (id: string) => {
    try { await bookingApi.confirmBooking(id); toast.success('Booking confirmed'); fetch() }
    catch (e: any) { toast.error(e.response?.data?.detail || 'Failed') }
  }

  const cancel = async (id: string) => {
    try { await bookingApi.staffCancelBooking(id); toast.success('Booking cancelled'); fetch() }
    catch (e: any) { toast.error(e.response?.data?.detail || 'Failed') }
  }

  const today = bookings.filter((b) => {
    const d = new Date(b.booking_time)
    const now = new Date()
    return d.toDateString() === now.toDateString()
  })
  const upcoming = bookings.filter((b) => new Date(b.booking_time) > new Date() && !today.includes(b))

  if (loading) return <div className="text-center py-20 text-gray-400">Loading bookings...</div>

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Bookings Manager</h2>
        <button onClick={fetch}><RefreshCw size={18} className="text-gray-400" /></button>
      </div>

      {[['Today', today], ['Upcoming', upcoming]].map(([label, list]) => (
        (list as Booking[]).length > 0 && (
          <div key={label as string}>
            <h3 className="font-semibold text-gray-600 mb-3">{label as string}</h3>
            <div className="space-y-3">
              {(list as Booking[]).map((b) => (
                <div key={b.id} className="card flex justify-between items-center">
                  <div>
                    <p className="font-semibold">{b.customer_name}</p>
                    <p className="text-sm text-gray-500">{format(parseISO(b.booking_time), 'EEE MMM d · h:mm a')} · {b.party_size} guests</p>
                    {b.special_requests && <p className="text-xs text-gray-400">{b.special_requests}</p>}
                    <span className={`badge mt-1 ${b.status === 'confirmed' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {b.status}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    {b.status !== 'confirmed' && (
                      <button onClick={() => confirm(b.id)} className="text-green-500 hover:text-green-700 p-2">
                        <CheckCircle size={20} />
                      </button>
                    )}
                    <button onClick={() => cancel(b.id)} className="text-red-400 hover:text-red-600 p-2">
                      <X size={20} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      ))}

      {bookings.length === 0 && (
        <div className="text-center py-16 text-gray-300"><p className="text-5xl mb-3">📅</p><p>No bookings yet.</p></div>
      )}
    </div>
  )
}
