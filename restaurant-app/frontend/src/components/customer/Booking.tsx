import { useState, useEffect } from 'react'
import { CalendarDays, Clock, Users, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { bookingApi } from '@/services/api'
import type { Booking } from '@/types'
import { useAuth } from '@/contexts/AuthContext'
import { format, addDays, parseISO } from 'date-fns'

export default function Booking() {
  const [bookings, setBookings] = useState<Booking[]>([])
  const [partySize, setPartySize] = useState(2)
  const [date, setDate] = useState(format(addDays(new Date(), 1), 'yyyy-MM-dd'))
  const [time, setTime] = useState('19:00')
  const [specialRequests, setSpecialRequests] = useState('')
  const [loading, setLoading] = useState(false)
  const { user } = useAuth()
  const restaurantId = user?.restaurant_id || import.meta.env.VITE_RESTAURANT_ID

  const fetchBookings = async () => {
    try {
      const res = await bookingApi.getMyBookings()
      setBookings(res.data)
    } catch {}
  }

  useEffect(() => { fetchBookings() }, [])

  const handleBook = async () => {
    const booking_time = `${date}T${time}:00`
    setLoading(true)
    try {
      await bookingApi.createBooking({
        party_size: partySize,
        booking_time,
        special_requests: specialRequests || undefined,
        restaurant_id: restaurantId,
      })
      toast.success('Table booked! See you soon 🎉')
      setSpecialRequests('')
      fetchBookings()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Booking failed')
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = async (id: string) => {
    try {
      await bookingApi.cancelBooking(id)
      toast.success('Booking cancelled.')
      fetchBookings()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Cannot cancel')
    }
  }

  const upcoming = bookings.filter((b) => b.status === 'confirmed' && new Date(b.booking_time) > new Date())
  const past = bookings.filter((b) => b.status !== 'confirmed' || new Date(b.booking_time) <= new Date())

  return (
    <div className="p-4 space-y-5">
      <h2 className="text-xl font-bold">Book a Table</h2>

      {/* Booking form */}
      <div className="card space-y-4">
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
            <Users size={14} /> Party Size
          </label>
          <div className="flex gap-2 flex-wrap">
            {[1,2,3,4,5,6,7,8].map((n) => (
              <button
                key={n}
                onClick={() => setPartySize(n)}
                className={`w-10 h-10 rounded-xl font-semibold text-sm transition-all ${
                  partySize === n ? 'bg-primary-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
            <CalendarDays size={14} /> Date
          </label>
          <input
            type="date"
            className="input"
            value={date}
            min={format(addDays(new Date(), 1), 'yyyy-MM-dd')}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
            <Clock size={14} /> Time
          </label>
          <input
            type="time"
            className="input"
            value={time}
            onChange={(e) => setTime(e.target.value)}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">Special Requests (optional)</label>
          <textarea
            className="input resize-none h-20"
            placeholder="e.g. High chair needed, birthday celebration..."
            value={specialRequests}
            onChange={(e) => setSpecialRequests(e.target.value)}
          />
        </div>

        <button onClick={handleBook} disabled={loading} className="btn-primary w-full">
          {loading ? 'Booking...' : 'Reserve Table'}
        </button>
      </div>

      {/* Upcoming bookings */}
      {upcoming.length > 0 && (
        <div>
          <h3 className="font-semibold text-gray-700 mb-3">Upcoming Reservations</h3>
          {upcoming.map((b) => (
            <div key={b.id} className="card mb-3 flex justify-between items-center">
              <div>
                <p className="font-semibold">{format(parseISO(b.booking_time), 'EEE, MMM d · h:mm a')}</p>
                <p className="text-sm text-gray-500">{b.party_size} guests</p>
                {b.special_requests && <p className="text-xs text-gray-400">{b.special_requests}</p>}
              </div>
              <button onClick={() => handleCancel(b.id)} className="text-red-400 hover:text-red-600 p-2">
                <X size={18} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Past bookings */}
      {past.length > 0 && (
        <div>
          <h3 className="font-semibold text-gray-500 mb-2 text-sm">Past Bookings</h3>
          {past.map((b) => (
            <div key={b.id} className="card mb-2 opacity-60">
              <p className="font-medium text-sm">{format(parseISO(b.booking_time), 'EEE, MMM d · h:mm a')}</p>
              <div className="flex gap-2 mt-1">
                <span className="text-xs text-gray-500">{b.party_size} guests</span>
                <span className={`text-xs ${b.status === 'cancelled' ? 'text-red-500' : 'text-green-600'}`}>
                  {b.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
