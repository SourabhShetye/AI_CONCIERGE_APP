import { useState, useEffect } from 'react'
import { Plus, Edit2, Trash2, ToggleLeft, ToggleRight, X, Check } from 'lucide-react'
import toast from 'react-hot-toast'
import { menuApi } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'
import type { MenuItem } from '@/types'

const CATEGORIES = ['Starters', 'Mains', 'Drinks', 'Desserts']

const emptyForm = {
  name: '', description: '', price: '', category: 'Mains', sold_out: false, allergens: [] as string[],
}

export default function MenuManager() {
  const [items, setItems] = useState<MenuItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({ ...emptyForm })
  const { user } = useAuth()
  const restaurantId = user?.restaurant_id || import.meta.env.VITE_RESTAURANT_ID

  const fetch = async () => {
    try {
      const res = await menuApi.getMenu(restaurantId)
      setItems(res.data)
    } catch { toast.error('Failed to load menu') }
    finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [])

  const handleSubmit = async () => {
    if (!form.name || !form.price) return toast.error('Name and price are required')
    try {
      const data = { ...form, price: parseFloat(form.price) }
      if (editingId) {
        await menuApi.updateItem(editingId, data)
        toast.success('Item updated')
      } else {
        await menuApi.createItem({ ...data, restaurant_id: restaurantId })
        toast.success('Item added')
      }
      setShowForm(false)
      setEditingId(null)
      setForm({ ...emptyForm })
      fetch()
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to save')
    }
  }

  const handleEdit = (item: MenuItem) => {
    setForm({ name: item.name, description: item.description || '', price: String(item.price), category: item.category, sold_out: item.sold_out, allergens: item.allergens || [] })
    setEditingId(item.id)
    setShowForm(true)
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this item?')) return
    try { await menuApi.deleteItem(id); toast.success('Deleted'); fetch() }
    catch { toast.error('Failed to delete') }
  }

  const toggleSoldOut = async (item: MenuItem) => {
    try {
      await menuApi.updateItem(item.id, { sold_out: !item.sold_out })
      toast.success(`Marked as ${!item.sold_out ? 'sold out' : 'available'}`)
      fetch()
    } catch { toast.error('Failed to update') }
  }

  if (loading) return <div className="text-center py-20 text-gray-400">Loading menu...</div>

  const grouped = CATEGORIES.reduce((acc, cat) => {
    const catItems = items.filter((i) => i.category === cat)
    if (catItems.length) acc[cat] = catItems
    return acc
  }, {} as Record<string, MenuItem[]>)

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Menu Manager</h2>
        <button onClick={() => { setEditingId(null); setForm({ ...emptyForm }); setShowForm(true) }} className="btn-primary flex items-center gap-2">
          <Plus size={16} /> Add Item
        </button>
      </div>

      {/* Form modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-lg p-6 space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="font-bold text-lg">{editingId ? 'Edit Item' : 'Add Menu Item'}</h3>
              <button onClick={() => setShowForm(false)}><X size={20} /></button>
            </div>
            <input className="input" placeholder="Item name *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <textarea className="input resize-none h-20" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <div className="flex gap-3">
              <input className="input flex-1" type="number" placeholder="Price (AED) *" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
              <select className="input flex-1" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.sold_out} onChange={(e) => setForm({ ...form, sold_out: e.target.checked })} />
              <span className="text-sm text-gray-700">Mark as sold out</span>
            </label>
            <div className="flex gap-3">
              <button onClick={handleSubmit} className="btn-primary flex-1 flex items-center justify-center gap-2"><Check size={16} /> Save</button>
              <button onClick={() => setShowForm(false)} className="btn-secondary flex-1">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Menu items */}
      {Object.entries(grouped).map(([cat, catItems]) => (
        <div key={cat}>
          <h3 className="font-bold text-gray-600 mb-3">{cat}</h3>
          <div className="space-y-2">
            {catItems.map((item) => (
              <div key={item.id} className={`card flex items-center justify-between ${item.sold_out ? 'opacity-60' : ''}`}>
                <div>
                  <p className="font-medium">{item.name} {item.sold_out && <span className="badge bg-red-100 text-red-600 ml-1">Sold Out</span>}</p>
                  <p className="text-sm text-gray-500">AED {item.price.toFixed(2)}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => toggleSoldOut(item)} className="text-gray-400 hover:text-primary-500 p-1">
                    {item.sold_out ? <ToggleLeft size={20} /> : <ToggleRight size={20} className="text-green-500" />}
                  </button>
                  <button onClick={() => handleEdit(item)} className="text-blue-400 hover:text-blue-600 p-1"><Edit2 size={16} /></button>
                  <button onClick={() => handleDelete(item.id)} className="text-red-400 hover:text-red-600 p-1"><Trash2 size={16} /></button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
