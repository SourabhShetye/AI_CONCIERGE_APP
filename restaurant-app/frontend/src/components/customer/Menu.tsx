import { useState, useEffect } from 'react'
import { Search, ShoppingCart, Plus, Minus, Mic, Send, AlertTriangle, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { menuApi, orderApi } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'
import { useCart } from '@/contexts/CartContext'
import type { MenuItem, PlaceOrderResponse } from '@/types'

const CATEGORIES = ['All', 'Starters', 'Mains', 'Drinks', 'Desserts']

export default function Menu() {
  const [menuItems, setMenuItems] = useState<MenuItem[]>([])
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [nlInput, setNlInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [ordering, setOrdering] = useState(false)
  const [orderResult, setOrderResult] = useState<PlaceOrderResponse | null>(null)
  const [showCart, setShowCart] = useState(false)
  const { cart, addItem, removeItem, updateQty, clearCart, total, itemCount } = useCart()

  const { user } = useAuth()
  const restaurantId = user?.restaurant_id || import.meta.env.VITE_RESTAURANT_ID

  useEffect(() => {
    menuApi.getMenu(restaurantId)
      .then((r) => setMenuItems(r.data))
      .catch(() => toast.error('Failed to load menu'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = menuItems.filter((item) => {
    const matchesSearch = item.name.toLowerCase().includes(search.toLowerCase()) ||
      item.description?.toLowerCase().includes(search.toLowerCase())
    const matchesCategory = category === 'All' || item.category === category
    return matchesSearch && matchesCategory
  })

  const grouped = CATEGORIES.slice(1).reduce((acc, cat) => {
    const items = filtered.filter((i) => i.category === cat)
    if (items.length) acc[cat] = items
    return acc
  }, {} as Record<string, MenuItem[]>)

  const getCartQty = (id: string) => cart.find((e) => e.item.id === id)?.quantity ?? 0

  // Natural language order submission
  const handleNLOrder = async () => {
    if (!nlInput.trim()) return toast.error('Please describe your order.')
    const tableNumber = user ? sessionStorage.getItem(`table_${user.user_id}`) || '' : ''

    if (!tableNumber) {
      // Ask for table number
      const tbl = window.prompt('Please enter your table number:')
      if (!tbl) return
      if (user) sessionStorage.setItem(`table_${user.user_id}`, tbl)
    }

    const tbl = sessionStorage.getItem(`table_${user?.user_id}`) || ''
    setOrdering(true)
    try {
      const res = await orderApi.placeOrder({
        natural_language_input: nlInput,
        table_number: tbl,
        restaurant_id: restaurantId,
      })
      setOrderResult(res.data)
      setNlInput('')
      toast.success('Order placed! Kitchen is preparing it 🍳')
    } catch (err: any) {
      const detail = err.response?.data?.detail
      if (typeof detail === 'object') {
        toast.error(`Could not recognise: ${detail.unrecognized?.join(', ') || 'some items'}`)
      } else {
        toast.error(detail || 'Failed to place order')
      }
    } finally {
      setOrdering(false)
    }
  }

  // Cart-based order
  const handleCartOrder = async () => {
    if (!cart.length) return
    const tableNumber = sessionStorage.getItem(`table_${user?.user_id}`) || ''
    if (!tableNumber) {
      const tbl = window.prompt('Please enter your table number:')
      if (!tbl) return
      if (user) sessionStorage.setItem(`table_${user.user_id}`, tbl)
    }
    const tbl = sessionStorage.getItem(`table_${user?.user_id}`) || ''
    const nlText = cart.map((e) => `${e.quantity} ${e.item.name}`).join(', ')
    setOrdering(true)
    try {
      const res = await orderApi.placeOrder({
        natural_language_input: nlText,
        table_number: tbl,
        restaurant_id: restaurantId,
      })
      setOrderResult(res.data)
      clearCart()
      setShowCart(false)
      toast.success('Order placed! 🎉')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to place order')
    } finally {
      setOrdering(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading menu...</div>

  return (
    <div className="p-4 space-y-4">
      {/* Search */}
      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          className="input pl-10"
          placeholder="Search menu..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* AI Natural Language Input */}
      <div className="card border-primary-100 bg-gradient-to-br from-primary-50 to-white">
        <p className="text-sm font-semibold text-primary-700 mb-2">🤖 Order with AI</p>
        <p className="text-xs text-gray-500 mb-3">Just describe what you want in plain English</p>
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder='"I want 2 burgers and a coffee"'
            value={nlInput}
            onChange={(e) => setNlInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleNLOrder()}
          />
          <button onClick={handleNLOrder} disabled={ordering} className="btn-primary px-4">
            {ordering ? '...' : <Send size={18} />}
          </button>
        </div>
      </div>

      {/* Order result (allergy warnings / unrecognized items) */}
      {orderResult && (
        <div className="card border-green-200 bg-green-50">
          <div className="flex justify-between items-start">
            <p className="font-semibold text-green-800">✅ Order Confirmed</p>
            <button onClick={() => setOrderResult(null)}><X size={16} className="text-gray-400" /></button>
          </div>
          <p className="text-sm text-green-700 mt-1">AED {orderResult.price.toFixed(2)}</p>
          {orderResult.allergy_warnings?.map((w, i) => (
            <div key={i} className="flex items-center gap-2 mt-2 text-orange-700 text-xs">
              <AlertTriangle size={14} /> {w}
            </div>
          ))}
          {orderResult.sold_out_items?.length ? (
            <p className="text-xs text-red-600 mt-1">
              Sold out: {orderResult.sold_out_items.join(', ')}
            </p>
          ) : null}
        </div>
      )}

      {/* Category tabs */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all ${
              category === cat
                ? 'bg-primary-500 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:border-primary-300'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Menu items grouped by category */}
      {Object.entries(grouped).map(([cat, items]) => (
        <div key={cat}>
          <h3 className="font-bold text-gray-700 mb-3">{cat}</h3>
          <div className="space-y-3">
            {items.map((item) => {
              const qty = getCartQty(item.id)
              return (
                <div key={item.id} className={`card flex gap-3 ${item.sold_out ? 'opacity-50' : ''}`}>
                  <div className="flex-1">
                    <div className="flex items-start justify-between">
                      <p className="font-semibold text-gray-900 text-sm">{item.name}</p>
                      <p className="font-bold text-primary-600 text-sm ml-2">AED {item.price.toFixed(2)}</p>
                    </div>
                    {item.description && (
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{item.description}</p>
                    )}
                    {item.sold_out && (
                      <span className="badge bg-red-100 text-red-600 mt-1">Sold Out</span>
                    )}
                    {item.allergens?.length ? (
                      <p className="text-xs text-orange-500 mt-1">Contains: {item.allergens.join(', ')}</p>
                    ) : null}
                  </div>

                  {!item.sold_out && (
                    <div className="flex items-center gap-2 self-end">
                      {qty > 0 ? (
                        <>
                          <button
                            onClick={() => updateQty(item.id, qty - 1)}
                            className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center hover:bg-gray-200"
                          >
                            <Minus size={14} />
                          </button>
                          <span className="w-4 text-center font-bold text-sm">{qty}</span>
                        </>
                      ) : null}
                      <button
                        onClick={() => addItem(item)}
                        className="w-8 h-8 rounded-lg bg-primary-500 flex items-center justify-center hover:bg-primary-600 text-white"
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {/* Floating cart button */}
      {itemCount > 0 && (
        <div className="fixed bottom-20 left-0 right-0 px-4 max-w-2xl mx-auto">
          <button
            onClick={() => setShowCart(true)}
            className="btn-primary w-full flex items-center justify-between"
          >
            <span className="bg-white/20 rounded-lg px-2 py-0.5 text-sm">{itemCount}</span>
            <span>View Cart</span>
            <span>AED {total.toFixed(2)}</span>
          </button>
        </div>
      )}

      {/* Cart modal */}
      {showCart && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end" onClick={() => setShowCart(false)}>
          <div className="bg-white w-full max-w-2xl mx-auto rounded-t-3xl p-6 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg">Your Cart</h3>
              <button onClick={() => setShowCart(false)}><X size={20} /></button>
            </div>
            {cart.map((entry) => (
              <div key={entry.item.id} className="flex items-center justify-between py-3 border-b border-gray-100">
                <div>
                  <p className="font-medium text-sm">{entry.item.name}</p>
                  <p className="text-xs text-gray-500">AED {entry.item.price.toFixed(2)} each</p>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => updateQty(entry.item.id, entry.quantity - 1)} className="w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center">
                    <Minus size={12} />
                  </button>
                  <span className="w-4 text-center font-bold text-sm">{entry.quantity}</span>
                  <button onClick={() => updateQty(entry.item.id, entry.quantity + 1)} className="w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center">
                    <Plus size={12} />
                  </button>
                </div>
              </div>
            ))}
            <div className="flex justify-between font-bold text-lg mt-4 mb-6">
              <span>Total</span>
              <span>AED {total.toFixed(2)}</span>
            </div>
            <button onClick={handleCartOrder} disabled={ordering} className="btn-primary w-full">
              {ordering ? 'Placing Order...' : 'Place Order 🍳'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
