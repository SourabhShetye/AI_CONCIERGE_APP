import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff } from 'lucide-react'
import toast from 'react-hot-toast'
import { authApi } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'
import type { AuthUser } from '@/types'

export default function StaffLogin() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()
  const handleLogin = async () => {
  if (!username || !password) return toast.error('Please fill all fields')
  sessionStorage.clear()  // always start fresh
  setLoading(true)
  try {
    // Don't send restaurant_id — backend finds it by username match across all restaurants
    const res = await authApi.staffLogin({ username, password })
      const user: AuthUser = { ...res.data }
      login(user)
      toast.success(`Welcome, ${username}! (${res.data.role})`)
      navigate('/staff/kitchen')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-brand-gradient flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md p-8">
        <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-600 mb-6 flex items-center gap-1">
          <ArrowLeft size={18} /> Back
        </button>

        <div className="text-center mb-8">
          <div className="text-5xl mb-3">👨‍🍳</div>
          <h2 className="text-2xl font-bold">Staff Portal</h2>
          <p className="text-gray-500 text-sm mt-1">Kitchen · Admin · Manager</p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Username</label>
            <input className="input" placeholder="e.g. admin" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Password</label>
            <div className="relative">
              <input
                className="input pr-12"
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          <button onClick={handleLogin} disabled={loading} className="btn-primary w-full">
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </div>
      </div>
    </div>
  )
}
