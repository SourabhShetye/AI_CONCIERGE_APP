import { createContext, useContext, useState, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import type { AuthUser } from '@/types'

interface AuthContextType {
  user: AuthUser | null
  login: (user: AuthUser) => void
  logout: () => Promise<void>
  isCustomer: boolean
  isStaff: boolean
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

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

  // NOTE: useNavigate must be used inside a component that is a child of
  // <BrowserRouter>. AuthProvider must be nested inside your router.
  const navigate = useNavigate()

  const login = (authUser: AuthUser) => {
    // Store access token
    storage.setItem('token', authUser.access_token)

    // SECURITY FIX: Store refresh token so Axios interceptor can rotate it
    if (authUser.refresh_token) {
      storage.setItem('refresh_token', authUser.refresh_token)
    }

    storage.setItem('user', JSON.stringify(authUser))
    setUser(authUser)
  }

  // SECURITY FIX: logout is now async — calls server to revoke refresh token
  const logout = async () => {
    try {
      const refreshToken = storage.getItem('refresh_token')
      if (refreshToken) {
        // Revoke server-side tokens — fire and forget, don't block UI
        await axios.post(
          `${import.meta.env.VITE_API_URL}/api/auth/logout`,
          { refresh_token: refreshToken },
          {
            headers: {
              Authorization: `Bearer ${storage.getItem('token') || ''}`,
            },
          }
        )
      }
    } catch {
      // Server-side revocation failed — clear client-side regardless
      // The refresh token will expire naturally in 7 days
    } finally {
      storage.clear()
      setUser(null)
      // Redirect based on what role was logged in
      // Both customer and staff go to login — adjust path if staff has separate login
      navigate('/customer/login')
    }
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