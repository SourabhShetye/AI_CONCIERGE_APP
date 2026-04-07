import { useState, useEffect } from 'react'
import { RefreshCw, Search, Star } from 'lucide-react'
import toast from 'react-hot-toast'
import { crmApi } from '@/services/api'
import type { CustomerInsight } from '@/types'

const TAG_COLORS: Record<string, string> = {
  'VIP':              'bg-purple-100 text-purple-700',
  'Frequent Diner':   'bg-blue-100 text-blue-700',
  'Big Spender':      'bg-green-100 text-green-700',
  'Churn Risk':       'bg-red-100 text-red-700',
  'Brand Ambassador': 'bg-yellow-100 text-yellow-700',
  'Needs Attention':  'bg-orange-100 text-orange-700',
}

const ALL_TAGS = [
  'VIP', 'Frequent Diner', 'Big Spender',
  'Churn Risk', 'Brand Ambassador', 'Needs Attention',
]

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5">
      {[1,2,3,4,5].map(n => (
        <Star
          key={n}
          size={12}
          className={n <= Math.round(rating) ? 'text-yellow-400 fill-yellow-400' : 'text-gray-200 fill-gray-200'}
        />
      ))}
    </div>
  )
}

export default function CRM() {
  const [customers, setCustomers] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterTag, setFilterTag] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'spend' | 'visits' | 'rating'>('spend')

  const fetch = async () => {
    try {
      const res = await crmApi.getCustomers()
      setCustomers(res.data)
    } catch { toast.error('Failed to load CRM') }
    finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [])

  const filtered = customers
    .filter((c) => {
      const matchesSearch = c.name.toLowerCase().includes(search.toLowerCase())
      const matchesTag = !filterTag || c.tags?.includes(filterTag)
      return matchesSearch && matchesTag
    })
    .sort((a, b) => {
      if (sortBy === 'spend') return (b.total_spend || 0) - (a.total_spend || 0)
      if (sortBy === 'visits') return (b.visit_count || 0) - (a.visit_count || 0)
      if (sortBy === 'rating') return (b.average_rating || 0) - (a.average_rating || 0)
      return 0
    })

  if (loading) return <div className="text-center py-20 text-gray-400">Loading CRM...</div>

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Customer Insights</h2>
        <button onClick={fetch}><RefreshCw size={18} className="text-gray-400" /></button>
      </div>

      {/* Stats summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {ALL_TAGS.map((tag) => {
          const count = customers.filter((c) => c.tags?.includes(tag)).length
          return (
            <button
              key={tag}
              onClick={() => setFilterTag(filterTag === tag ? null : tag)}
              className={`card text-center cursor-pointer transition-all hover:shadow-md ${filterTag === tag ? 'ring-2 ring-primary-500' : ''}`}
            >
              <p className="text-2xl font-bold text-primary-600">{count}</p>
              <p className="text-xs text-gray-500 mt-1 leading-tight">{tag}</p>
            </button>
          )
        })}
      </div>

      {/* Sort + Search */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input pl-9"
            placeholder="Search customers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
          {[
            { key: 'spend', label: 'Spend' },
            { key: 'visits', label: 'Visits' },
            { key: 'rating', label: 'Rating' },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setSortBy(key as any)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                sortBy === key ? 'bg-white shadow text-primary-600' : 'text-gray-500'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Customer list */}
      <div className="space-y-3">
        {filtered.map((customer) => (
          <div key={customer.id} className="card">
            <div className="flex justify-between items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold truncate">{customer.name}</p>
                  {customer.average_rating > 0 && (
                    <div className="flex items-center gap-1">
                      <StarRating rating={customer.average_rating} />
                      <span className="text-xs text-gray-500">
                        {Number(customer.average_rating).toFixed(1)}
                        {customer.total_feedback_count > 0 && ` (${customer.total_feedback_count})`}
                      </span>
                    </div>
                  )}
                </div>

                {customer.phone && (
                  <p className="text-xs text-gray-400">{customer.phone}</p>
                )}

                <div className="flex gap-3 mt-1 flex-wrap">
                  <span className="text-sm text-gray-600">
                    {customer.visit_count} visit{customer.visit_count !== 1 ? 's' : ''}
                  </span>
                  <span className="text-sm text-gray-600">
                    AED {Number(customer.total_spend || 0).toFixed(2)} total
                  </span>
                  {customer.last_visit && (
                    <span className="text-xs text-gray-400">
                      Last: {new Date(customer.last_visit).toLocaleDateString()}
                    </span>
                  )}
                </div>

                {/* Feedback summary */}
                {customer.last_feedback_comment && (
                  <div className="mt-2 bg-gray-50 rounded-lg px-3 py-2">
                    <p className="text-xs text-gray-500 italic">
                      "{customer.last_feedback_comment}"
                    </p>
                  </div>
                )}

                {customer.allergies?.length > 0 && (
                  <p className="text-xs text-orange-500 mt-1">
                    ⚠️ Allergies: {customer.allergies.join(', ')}
                  </p>
                )}
              </div>

              {/* Tags */}
              <div className="flex flex-col gap-1 items-end shrink-0">
                {customer.tags?.map((tag: string) => (
                  <span
                    key={tag}
                    className={`badge text-xs ${TAG_COLORS[tag] || 'bg-gray-100 text-gray-600'}`}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="text-center py-10 text-gray-300">No customers found.</div>
        )}
      </div>
    </div>
  )
}
