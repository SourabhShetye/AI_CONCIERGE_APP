import { useState } from 'react'
import { Star } from 'lucide-react'
import toast from 'react-hot-toast'
import { feedbackApi } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'


export default function Feedback() {
  const [overall, setOverall] = useState(0)
  const [comments, setComments] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const { user } = useAuth()
  const restaurantId = user?.restaurant_id || import.meta.env.VITE_RESTAURANT_ID

  const handleSubmit = async () => {
    if (!overall) return toast.error('Please give an overall rating')
    try {
      await feedbackApi.submit({ overall_rating: overall, comments: comments || undefined, restaurant_id: restaurantId })
      setSubmitted(true)
      toast.success('Thank you for your feedback! 🌟')
    } catch {
      toast.error('Failed to submit feedback')
    }
  }

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center h-64 p-4">
        <div className="text-6xl mb-4">🙏</div>
        <h3 className="text-xl font-bold text-gray-800">Thank You!</h3>
        <p className="text-gray-500 text-sm mt-2">We hope to see you again soon.</p>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-5">
      <h2 className="text-xl font-bold">Leave Feedback</h2>

      <div className="card">
        <p className="font-semibold text-gray-700 mb-3">Overall Experience</p>
        <div className="flex gap-2">
          {[1,2,3,4,5].map((n) => (
            <button key={n} onClick={() => setOverall(n)}>
              <Star
                size={36}
                className={`transition-colors ${n <= overall ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`}
              />
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <p className="font-semibold text-gray-700 mb-3">Comments (optional)</p>
        <textarea
          className="input resize-none h-28"
          placeholder="Tell us what you loved or how we can improve..."
          value={comments}
          onChange={(e) => setComments(e.target.value)}
        />
      </div>

      <button onClick={handleSubmit} className="btn-primary w-full">
        Submit Feedback
      </button>
    </div>
  )
}
