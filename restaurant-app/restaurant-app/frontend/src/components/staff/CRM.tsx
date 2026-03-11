import { useState, useEffect } from 'react'
import { RefreshCw, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { crmApi } from '@/services/api'
import type { CustomerInsight } from '@/types'

const TAG_COLORS: Record<string, string> = {
  'VIP': 'bg-purple-100 text-purple-700',
  'Frequent Diner': 'bg-blue-100 text-blue-700',
  'Big Spender': 'bg-green-100 text-green-700',
  'Churn Risk': 'bg-red-100 text-red-700',
}

const ALL_TAGS = ['VIP', 'Frequent Diner', 'Big Spender', 'Churn Risk']

export default function CRM() {
  const [customers, setCustomers] = useState<CustomerInsight[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterTag, setFilterTag] = useState<string | null>(null)

  const fetch = async () => {
    try {
      const res = await crmApi.getCustomers()
      setCustomers(res.data)
    } catch { toast.error('Failed to load CRM') }
    finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [])

  const filtered = customers.filter((c) => {
    const matchesSearch = c.name.toLowerCase().includes(search.toLowerCase())
    const matchesTag = !filterTag || c.tags?.includes(filterTag)
    return matchesSearch && matchesTag
  })

  if (loading) return <div className="text-center py-20 text-gray-400">Loading CRM...</div>

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Customer Insights</h2>
        <button onClick={fetch}><RefreshCw size={18} className="text-gray-400" /></button>
      </div>

      {/* Stats summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {ALL_TAGS.map((tag) => {
          const count = customers.filter((c) => c.tags?.includes(tag)).length
          return (
            <button
              key={tag}
              onClick={() => setFilterTag(filterTag === tag ? null : tag)}
              className={`card text-center cursor-pointer transition-all hover:shadow-md ${filterTag === tag ? 'ring-2 ring-primary-500' : ''}`}
            >
              <p className="text-2xl font-bold text-primary-600">{count}</p>
              <p className="text-xs text-gray-500 mt-1">{tag}</p>
            </button>
          )
        })}
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input className="input pl-9" placeholder="Search customers..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      {/* Customer list */}
      <div className="space-y-3">
        {filtered.map((customer) => (
          <div key={customer.id} className="card">
            <div className="flex justify-between items-start">
              <div>
                <p className="font-semibold">{customer.name}</p>
                {customer.phone && <p className="text-xs text-gray-400">{customer.phone}</p>}
                <p className="text-sm text-gray-500 mt-1">
                  {customer.visit_count} visit{customer.visit_count !== 1 ? 's' : ''} · AED {customer.total_spend?.toFixed(2) || '0.00'} total
                </p>
                {customer.last_visit && (
                  <p className="text-xs text-gray-400">Last visit: {new Date(customer.last_visit).toLocaleDateString()}</p>
                )}
                {customer.allergies?.length ? (
                  <p className="text-xs text-orange-500 mt-1">⚠️ Allergies: {customer.allergies.join(', ')}</p>
                ) : null}
              </div>
              <div className="flex flex-col gap-1 items-end">
                {customer.tags?.map((tag) => (
                  <span key={tag} className={`badge text-xs ${TAG_COLORS[tag] || 'bg-gray-100 text-gray-600'}`}>{tag}</span>
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
