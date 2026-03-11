import { useNavigate } from 'react-router-dom'
import { UtensilsCrossed, ChefHat } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useEffect } from 'react'

export default function LandingPage() {
  const navigate = useNavigate()
  const { user, isCustomer, isStaff } = useAuth()

  // Auto-redirect if already logged in
  useEffect(() => {
    if (isCustomer) navigate('/customer/menu')
    else if (isStaff) navigate('/staff/kitchen')
  }, [user])

  return (
    <div className="min-h-screen bg-brand-gradient flex flex-col items-center justify-center p-6">
      <div className="text-center mb-12">
        <div className="text-7xl mb-4">🍽️</div>
        <h1 className="text-4xl md:text-5xl font-bold text-white mb-3">
          Restaurant AI Concierge
        </h1>
        <p className="text-white/80 text-lg">
          Order food, book tables, and more — powered by AI
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 w-full max-w-md">
        <button
          onClick={() => navigate('/customer/login')}
          className="flex-1 bg-white text-primary-600 font-bold py-5 px-8 rounded-2xl
                     shadow-xl hover:shadow-2xl hover:-translate-y-1 transition-all duration-200
                     flex flex-col items-center gap-2 min-h-[100px]"
        >
          <UtensilsCrossed size={32} />
          <span className="text-lg">I'm a Customer</span>
          <span className="text-xs text-gray-400 font-normal">Order food & book tables</span>
        </button>

        <button
          onClick={() => navigate('/staff/login')}
          className="flex-1 bg-white/20 backdrop-blur text-white font-bold py-5 px-8 rounded-2xl
                     border-2 border-white/30 hover:bg-white/30 hover:-translate-y-1
                     transition-all duration-200 flex flex-col items-center gap-2 min-h-[100px]"
        >
          <ChefHat size={32} />
          <span className="text-lg">Staff Login</span>
          <span className="text-xs text-white/60 font-normal">Kitchen, admin & manager</span>
        </button>
      </div>

      <p className="text-white/40 text-sm mt-12">
        Powered by Groq AI · Llama 3.3 70B
      </p>
    </div>
  )
}
