import { createContext, useContext, useState, ReactNode } from 'react'
import type { AuthUser } from '@/types'

interface AuthContextType {
  user: AuthUser | null
  login: (user: AuthUser) => void
  logout: () => void
  isCustomer: boolean
  isStaff: boolean
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

// Use sessionStorage so each browser tab is fully independent
// Tab 1 = customer, Tab 2 = staff — no interference
const storage = sessionStorage

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    try {
      const stored = storage.getItem('user')
      return stored ? JSON.parse(stored) : null
    } catch {
      return null
    }
  })

  const login = (authUser: AuthUser) => {
    storage.setItem('token', authUser.access_token)
    storage.setItem('user', JSON.stringify(authUser))
    setUser(authUser)
  }

  const logout = () => {
    storage.clear()
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        login,
        logout,
        isCustomer: user?.role === 'customer',
        isStaff: ['admin', 'chef', 'manager'].includes(user?.role ?? ''),
        isAdmin: user?.role === 'admin',
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}