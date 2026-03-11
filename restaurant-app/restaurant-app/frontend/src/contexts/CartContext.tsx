import { createContext, useContext, useState, ReactNode } from 'react'
import type { MenuItem } from '@/types'

export interface CartEntry {
  item: MenuItem
  quantity: number
}

interface CartContextType {
  cart: CartEntry[]
  addItem: (item: MenuItem) => void
  removeItem: (itemId: string) => void
  updateQty: (itemId: string, qty: number) => void
  clearCart: () => void
  total: number
  itemCount: number
}

const CartContext = createContext<CartContextType | null>(null)

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<CartEntry[]>([])

  const addItem = (item: MenuItem) => {
    setCart((prev) => {
      const existing = prev.find((e) => e.item.id === item.id)
      if (existing) {
        return prev.map((e) =>
          e.item.id === item.id ? { ...e, quantity: e.quantity + 1 } : e
        )
      }
      return [...prev, { item, quantity: 1 }]
    })
  }

  const removeItem = (itemId: string) => {
    setCart((prev) => prev.filter((e) => e.item.id !== itemId))
  }

  const updateQty = (itemId: string, qty: number) => {
    if (qty <= 0) {
      removeItem(itemId)
      return
    }
    setCart((prev) =>
      prev.map((e) => (e.item.id === itemId ? { ...e, quantity: qty } : e))
    )
  }

  const clearCart = () => setCart([])

  const total = cart.reduce((sum, e) => sum + e.item.price * e.quantity, 0)
  const itemCount = cart.reduce((sum, e) => sum + e.quantity, 0)

  return (
    <CartContext.Provider value={{ cart, addItem, removeItem, updateQty, clearCart, total, itemCount }}>
      {children}
    </CartContext.Provider>
  )
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within CartProvider')
  return ctx
}
