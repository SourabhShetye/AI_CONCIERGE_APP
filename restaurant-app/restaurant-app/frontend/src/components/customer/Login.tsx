import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff } from 'lucide-react'
import toast from 'react-hot-toast'
import { authApi } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'
import type { AuthUser } from '@/types'

type Mode = 'login' | 'register'

const ALLERGEN_OPTIONS = ['Gluten', 'Dairy', 'Nuts', 'Shellfish', 'Eggs', 'Soy']

export default function CustomerLogin() {
  const [mode, setMode] = useState<Mode>('login')
  const [name, setName] = useState('')
  const [pin, setPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [phone, setPhone] = useState('')
  const [tableNumber, setTableNumber] = useState('')
  const [allergies, setAllergies] = useState<string[]>([])
  const [showPin, setShowPin] = useState(false)
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const restaurantId = import.meta.env.VITE_RESTAURANT_ID

  const toggleAllergen = (a: string) =>
    setAllergies((prev) => (prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]))

  const handleSubmit = async () => {
    if (!name.trim()) return toast.error('Please enter your name.')
    if (pin.length !== 4) return toast.error('PIN must be exactly 4 digits.')
    if (mode === 'register' && pin !== confirmPin) return toast.error('PINs do not match.')

    setLoading(true)
    try {
      const payload = { name: name.trim(), pin, restaurant_id: restaurantId, table_number: tableNumber || undefined }
      const res = mode === 'login'
        ? await authApi.customerLogin(payload)
        : await authApi.customerRegister({ ...payload, phone: phone || undefined, allergies })

      const user: AuthUser = { ...res.data, role: 'customer' }
      login(user)

      if (mode === 'login' && res.data.visit_count > 0) {
        toast.success(`Welcome back, ${user.name}! Visit #${res.data.visit_count} 🎉`)
      } else {
        toast.success(`Welcome, ${user.name}! 🍽️`)
      }
      navigate('/customer/menu')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-brand-gradient flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md p-8">
        {/* Header */}
        <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-600 mb-6 flex items-center gap-1">
          <ArrowLeft size={18} /> Back
        </button>

        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🍽️</div>
          <h2 className="text-2xl font-bold text-gray-900">
            {mode === 'login' ? 'Welcome Back!' : 'Create Account'}
          </h2>
          <p className="text-gray-500 text-sm mt-1">
            {mode === 'login' ? 'Enter your name and PIN to continue' : 'Join us to start ordering'}
          </p>
        </div>

        {/* Mode toggle */}
        <div className="flex bg-gray-100 rounded-xl p-1 mb-6">
          {(['login', 'register'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-all ${
                mode === m ? 'bg-white shadow text-primary-600' : 'text-gray-500'
              }`}
            >
              {m === 'login' ? 'Sign In' : 'Register'}
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Your Name</label>
            <input className="input" placeholder="e.g. John Smith" value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          {/* Phone (register only) */}
          {mode === 'register' && (
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1 block">Phone (optional)</label>
              <input className="input" placeholder="+971 50 000 0000" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
          )}

          {/* Table number */}
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Table Number (optional)</label>
            <input className="input" placeholder="e.g. 5" value={tableNumber} onChange={(e) => setTableNumber(e.target.value)} />
          </div>

          {/* PIN */}
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">4-Digit PIN</label>
            <div className="relative">
              <input
                className="input pr-12"
                type={showPin ? 'text' : 'password'}
                inputMode="numeric"
                maxLength={4}
                placeholder="••••"
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
              />
              <button
                type="button"
                onClick={() => setShowPin(!showPin)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"
              >
                {showPin ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Confirm PIN (register only) */}
          {mode === 'register' && (
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1 block">Confirm PIN</label>
              <input
                className="input"
                type="password"
                inputMode="numeric"
                maxLength={4}
                placeholder="••••"
                value={confirmPin}
                onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
              />
            </div>
          )}

          {/* Allergens (register only) */}
          {mode === 'register' && (
            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">
                Dietary Restrictions / Allergens
              </label>
              <div className="flex flex-wrap gap-2">
                {ALLERGEN_OPTIONS.map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => toggleAllergen(a)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium border-2 transition-all ${
                      allergies.includes(a)
                        ? 'bg-red-100 border-red-400 text-red-700'
                        : 'border-gray-200 text-gray-500 hover:border-gray-400'
                    }`}
                  >
                    {a}
                  </button>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading}
            className="btn-primary w-full mt-2"
          >
            {loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </div>
      </div>
    </div>
  )
}
