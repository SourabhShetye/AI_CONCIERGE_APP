import { useState, useRef, useEffect } from 'react'
import { Send, Bot, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

const QUICK_PROMPTS = [
  "Which orders have been waiting the longest?",
  "Who are the priority customers seated right now?",
  "Which dates this week are busiest?",
  "Which dishes are sold out?",
  "What's today's total active table revenue?",
  "Send Table 5: Kitchen closes in 30 mins, any last orders?",
]

export default function StaffChat() {
  const { user } = useAuth()
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: `Hi ${user?.name || 'there'}! I'm your restaurant operations assistant. I can help you with:\n\n• Delayed or priority orders\n• Busy booking dates\n• Customer insights\n• Sending messages to tables\n• Revenue summaries\n\nWhat would you like to know?`,
      timestamp: new Date(),
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text: string) => {
    if (!text.trim() || loading) return
    const userMsg: Message = { role: 'user', content: text, timestamp: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await api.post('/api/staff/chat', {
        message: text,
        conversation_history: messages.slice(-8).map(m => ({
          role: m.role,
          content: m.content,
        })),
      })
      const { reply } = res.data
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: reply,
        timestamp: new Date(),
      }])
    } catch (err: any) {
      const detail = err.response?.data?.detail
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: typeof detail === 'string' ? `Error: ${detail}` : 'Something went wrong. Please try again.',
        timestamp: new Date(),
      }])
    } finally {
      setLoading(false)
    }
  }

  const clearChat = () => {
    setMessages([{
      role: 'assistant',
      content: 'Chat cleared. How can I help?',
      timestamp: new Date(),
    }])
  }

  return (
    <div className="flex flex-col h-[calc(100vh-180px)] max-w-3xl">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
            <Bot size={18} className="text-white" />
          </div>
          <div>
            <h2 className="font-bold text-gray-900">Operations AI</h2>
            <p className="text-xs text-gray-500">Real-time restaurant intelligence</p>
          </div>
        </div>
        <button onClick={clearChat} className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1">
          <RefreshCw size={12} /> Clear
        </button>
      </div>

      {/* Quick prompts */}
      <div className="flex gap-2 overflow-x-auto pb-2 mb-3 scrollbar-hide">
        {QUICK_PROMPTS.map((prompt, i) => (
          <button
            key={i}
            onClick={() => send(prompt)}
            disabled={loading}
            className="px-3 py-1.5 bg-gray-100 hover:bg-primary-50 hover:text-primary-700 rounded-xl text-xs font-medium whitespace-nowrap text-gray-600 transition-all flex-shrink-0 border border-transparent hover:border-primary-200"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-lg bg-primary-100 flex items-center justify-center mr-2 mt-1 flex-shrink-0">
                <Bot size={14} className="text-primary-600" />
              </div>
            )}
            <div className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-line ${
              msg.role === 'user'
                ? 'bg-primary-500 text-white rounded-br-sm'
                : 'bg-gray-100 text-gray-800 rounded-bl-sm'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="w-7 h-7 rounded-lg bg-primary-100 flex items-center justify-center mr-2 mt-1">
              <Bot size={14} className="text-primary-600" />
            </div>
            <div className="bg-gray-100 px-4 py-3 rounded-2xl rounded-bl-sm flex gap-1">
              {[0, 1, 2].map(i => (
                <div key={i} className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2 mt-4 pt-4 border-t border-gray-100">
        <input
          className="input flex-1 text-sm"
          placeholder="Ask about orders, bookings, customers, or send a table message..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send(input)}
        />
        <button
          onClick={() => send(input)}
          disabled={loading}
          className="btn-primary px-4"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
