import { useState, useEffect } from 'react'
import { RefreshCw, Search, Star, TrendingUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { crmApi } from '@/services/api'

const TAG_COLORS: Record<string, string> = {
  'VIP':              'bg-purple-100 text-purple-700',
  'Frequent Diner':   'bg-blue-100 text-blue-700',
  'Big Spender':      'bg-green-100 text-green-700',
  'Churn Risk':       'bg-red-100 text-red-700',
  'Brand Ambassador': 'bg-yellow-100 text-yellow-800',
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
        <Star key={n} size={11}
          className={n <= Math.round(rating)
            ? 'text-yellow-400 fill-yellow-400'
            : 'text-gray-200 fill-gray-200'
          }
        />
      ))}
    </div>
  )
}

export default function CRM() {
  const [data, setData] = useState<{ customers: any[]; summary: any } | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterTag, setFilterTag] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'spend' | 'visits' | 'rating' | 'arpu'>('spend')

  const fetch = async () => {
    try {
      const res = await crmApi.getCustomers()
      // Handle both old format (array) and new format (object with customers + summary)
      if (Array.isArray(res.data)) {
        setData({ customers: res.data, summary: null })
      } else {
        setData(res.data)
      }
    } catch { toast.error('Failed to load CRM') }
    finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [])

  const customers = data?.customers || []
  const summary = data?.summary || null

  const filtered = customers
    .filter(c => {
      const matchSearch = c.name.toLowerCase().includes(search.toLowerCase())
      const matchTag = !filterTag || c.tags?.includes(filterTag)
      return matchSearch && matchTag
    })
    .sort((a, b) => {
      if (sortBy === 'spend') return (b.total_spend || 0) - (a.total_spend || 0)
      if (sortBy === 'visits') return (b.visit_count || 0) - (a.visit_count || 0)
      if (sortBy === 'rating') return (b.average_rating || 0) - (a.average_rating || 0)
      if (sortBy === 'arpu') return (b.revenue_per_visit || 0) - (a.revenue_per_visit || 0)
      return 0
    })

  if (loading) return <div className="text-center py-20 text-gray-400">Loading CRM...</div>

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Customer Insights</h2>
        <button onClick={fetch}><RefreshCw size={18} className="text-gray-400" /></button>
      </div>

      {/* ── ARPU Summary Card ──────────────────────────────────────────── */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="card text-center">
            <p className="text-2xl font-bold text-primary-600">
              AED {summary.arpu}
            </p>
            <p className="text-xs text-gray-500 mt-1 flex items-center justify-center gap-1">
              <TrendingUp size={11} /> ARPU
            </p>
            <p className="text-xs text-gray-400">avg revenue/user</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-green-600">
              AED {summary.total_revenue.toLocaleString()}
            </p>
            <p className="text-xs text-gray-500 mt-1">Total Revenue</p>
            <p className="text-xs text-gray-400">{summary.paying_customers} paying customers</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-blue-600">{summary.total_customers}</p>
            <p className="text-xs text-gray-500 mt-1">Total Customers</p>
            <p className="text-xs text-gray-400">all time</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-purple-600">{summary.average_visits}</p>
            <p className="text-xs text-gray-500 mt-1">Avg Visits</p>
            <p className="text-xs text-gray-400">per customer</p>
          </div>
        </div>
      )}

      {/* Tag filter pills */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {ALL_TAGS.map(tag => {
          const count = customers.filter(c => c.tags?.includes(tag)).length
          return (
            <button
              key={tag}
              onClick={() => setFilterTag(filterTag === tag ? null : tag)}
              className={`card text-center cursor-pointer transition-all hover:shadow-md py-2 ${
                filterTag === tag ? 'ring-2 ring-primary-500' : ''
              }`}
            >
              <p className="text-xl font-bold text-primary-600">{count}</p>
              <p className="text-xs text-gray-500 mt-0.5 leading-tight">{tag}</p>
            </button>
          )
        })}
      </div>

      {/* Search + Sort */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input className="input pl-9" placeholder="Search customers..."
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
          {[
            { key: 'spend', label: 'Spend' },
            { key: 'visits', label: 'Visits' },
            { key: 'rating', label: 'Rating' },
            { key: 'arpu', label: 'ARPU' },
          ].map(({ key, label }) => (
            <button key={key}
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
        {filtered.map(customer => (
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

                <div className="flex gap-3 mt-1 flex-wrap text-sm text-gray-600">
                  <span>{customer.visit_count} visit{customer.visit_count !== 1 ? 's' : ''}</span>
                  <span>AED {Number(customer.total_spend || 0).toFixed(2)} total</span>
                  {customer.revenue_per_visit > 0 && (
                    <span className="text-primary-600 font-medium flex items-center gap-0.5">
                      <TrendingUp size={11} />
                      AED {customer.revenue_per_visit}/visit
                    </span>
                  )}
                  {customer.last_visit && (
                    <span className="text-gray-400 text-xs">
                      Last: {new Date(customer.last_visit).toLocaleDateString()}
                    </span>
                  )}
                </div>

                {customer.last_feedback_comment && (
                  <div className="mt-2 bg-gray-50 rounded-lg px-3 py-1.5">
                    <p className="text-xs text-gray-500 italic">
                      "{customer.last_feedback_comment}"
                    </p>
                  </div>
                )}

                {customer.allergies?.length > 0 && (
                  <p className="text-xs text-orange-500 mt-1">
                    ⚠️ {customer.allergies.join(', ')}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-1 items-end shrink-0">
                {customer.tags?.map((tag: string) => (
                  <span key={tag}
                    className={`badge text-xs ${TAG_COLORS[tag] || 'bg-gray-100 text-gray-600'}`}>
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
