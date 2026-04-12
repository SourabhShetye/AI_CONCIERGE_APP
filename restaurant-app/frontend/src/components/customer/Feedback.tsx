import { useState } from 'react'
import { Star } from 'lucide-react'
import toast from 'react-hot-toast'
import { feedbackApi } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'

export default function Feedback() {
  const { user } = useAuth()
  const { submitted, setSubmitted } = useFeedbackSession(user?.user_id)
  const [overall, setOverall] = useState(0)
  const [comments, setComments] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const restaurantId = import.meta.env.VITE_RESTAURANT_ID

  const handleSubmit = async () => {
    if (!overall) return toast.error('Please give an overall rating')
    setSubmitting(true)
    try {
      await feedbackApi.submit({
        overall_rating: overall,
        comments: comments || undefined,
        restaurant_id: restaurantId,
      })
      setSubmitted(true)
      toast.success('Thank you for your feedback! 🌟')
    } catch {
      toast.error('Failed to submit feedback')
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center h-64 p-4">
        <div className="text-6xl mb-4">🙏</div>
        <h3 className="text-xl font-bold text-gray-800">Thank You!</h3>
        <p className="text-gray-500 text-sm mt-2 text-center">
          Your feedback has been recorded for this visit.
        </p>
        <p className="text-gray-400 text-xs mt-1">
          You can submit feedback again on your next visit.
        </p>
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
                className={`transition-colors ${
                  n <= overall
                    ? 'text-yellow-400 fill-yellow-400'
                    : 'text-gray-300'
                }`}
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

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="btn-primary w-full"
      >
        {submitting ? 'Submitting...' : 'Submit Feedback'}
      </button>
    </div>
  )
}

// ── Session-scoped feedback state ─────────────────────────────────────────────
// Uses sessionStorage so it resets on logout (session cleared) but persists
// across tab switches within the same session.

function useFeedbackSession(userId: string | undefined) {
  // Key is user-specific so different users on same device don't share state
  const key = `feedback_submitted_${userId || 'guest'}`

  const [submitted, setSubmittedState] = useState<boolean>(() => {
    return sessionStorage.getItem(key) === 'true'
  })

  const setSubmitted = (val: boolean) => {
    sessionStorage.setItem(key, String(val))
    setSubmittedState(val)
  }

  return { submitted, setSubmitted }
}