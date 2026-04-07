import { useState, useRef, useEffect } from 'react'
import { MessageCircle, X, Send, Mic } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/services/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

type ChatMode = 'general' | 'ordering' | 'booking'

// State machine pending actions — mirrors backend
type PendingAction = 'cancel_selection' | 'mod_selection' | 'mod_details' | null

interface ChatState {
  mode: ChatMode
  pendingAction: PendingAction
  pendingOrderId: string | null
  pendingOrderNum: number | null
}

const DEFAULT_STATE: ChatState = {
  mode: 'general',
  pendingAction: null,
  pendingOrderId: null,
  pendingOrderNum: null,
}

function loadChatState(): ChatState {
  try {
    const s = sessionStorage.getItem('chat_state')
    return s ? JSON.parse(s) : DEFAULT_STATE
  } catch {
    return DEFAULT_STATE
  }
}

function saveChatState(state: ChatState) {
  sessionStorage.setItem('chat_state', JSON.stringify(state))
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const saved = sessionStorage.getItem('chat_messages')
      if (saved) {
        const parsed = JSON.parse(saved)
        return parsed.map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) }))
      }
    } catch {}
    return [{
      role: 'assistant' as const,
      content: 'Hi! How can I help you today?',
      timestamp: new Date(),
    }]
  })
  const [chatState, setChatState] = useState<ChatState>(loadChatState)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [recording, setRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const { user } = useAuth()

  const restaurantId = new URLSearchParams(window.location.search).get('restaurant')
    || sessionStorage.getItem('restaurant_id')
    || import.meta.env.VITE_RESTAURANT_ID

  // Persist messages to sessionStorage
  useEffect(() => {
    if (messages.length > 1) {
      sessionStorage.setItem('chat_messages', JSON.stringify(messages))
    }
  }, [messages])

  // Persist chat state to sessionStorage
  useEffect(() => {
    saveChatState(chatState)
  }, [chatState])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (open) {
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'instant' }), 50)
    }
  }, [open])

  // Listen for kitchen notifications (approve/reject) and show in chat
  useEffect(() => {
    const handler = (e: Event) => {
      const msg = (e as CustomEvent).detail?.message
      if (msg) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: msg,
          timestamp: new Date(),
        }])
        setOpen(true)
      }
    }
    window.addEventListener('chat_notification', handler)
    return () => window.removeEventListener('chat_notification', handler)
  }, [])

  const addMessage = (role: 'user' | 'assistant', content: string) => {
    setMessages(prev => [...prev, { role, content, timestamp: new Date() }])
  }

  // Voice recording
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        const formData = new FormData()
        formData.append('audio', audioBlob, 'voice.webm')
        setLoading(true)
        try {
          const token = sessionStorage.getItem('token')
          const res = await fetch(`${import.meta.env.VITE_API_URL}/api/transcribe`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          })
          const data = await res.json()
          if (data.text) setInput(data.text)
        } catch { /* silent fail */ }
        finally { setLoading(false) }
      }
      mediaRecorder.start()
      setRecording(true)
    } catch {
      alert('Microphone permission denied.')
    }
  }

  const stopRecording = () => {
    mediaRecorderRef.current?.stop()
    setRecording(false)
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return

    // Ensure table number exists before ordering
    let tableNumber = user ? sessionStorage.getItem(`table_${user.user_id}`) : null
    if (!tableNumber && chatState.mode === 'ordering') {
      const tbl = window.prompt('Please enter your table number before ordering:')
      if (!tbl) return
      if (user) sessionStorage.setItem(`table_${user.user_id}`, tbl)
      tableNumber = tbl
    }

    const sentInput = input
    addMessage('user', sentInput)
    setInput('')
    setLoading(true)

    try {
      const res = await api.post('/api/chat', {
        message: sentInput,
        mode: chatState.mode,
        restaurant_id: restaurantId,
        table_number: tableNumber || null,
        conversation_history: messages.slice(-8).map(m => ({
          role: m.role,
          content: m.content,
        })),
        // Send current state machine state to backend
        pending_action: chatState.pendingAction,
        pending_order_id: chatState.pendingOrderId,
        pending_order_num: chatState.pendingOrderNum,
      })

      const {
        reply,
        new_mode,
        new_pending_action,
        new_pending_order_id,
        new_pending_order_num,
        order_placed,
        order_total,
        order_number,
        booking_placed,
        booking_summary,
        cancellation_requested,
        modification_requested,
      } = res.data

      // Update state machine state
      const newState: ChatState = {
        mode: (new_mode as ChatMode) || chatState.mode,
        pendingAction: new_pending_action || null,
        pendingOrderId: new_pending_order_id || null,
        pendingOrderNum: new_pending_order_num || null,
      }
      setChatState(newState)

      // Build reply message — add confirmation suffix if needed
      let displayReply = reply
      if (order_placed && order_total) {
        displayReply = `${reply}\n\n✅ Order #${order_number} placed! Total: AED ${Number(order_total).toFixed(2)}. Check your Orders tab.`
      } else if (booking_placed && booking_summary) {
        displayReply = `${reply}\n\n✅ Booking confirmed! ${booking_summary}. Check your Bookings tab.`
      }

      addMessage('assistant', displayReply)

    } catch (err: any) {
      const detail = err.response?.data?.detail
      addMessage('assistant',
        typeof detail === 'string'
          ? `Error: ${detail}`
          : 'Sorry, something went wrong. Please try again.'
      )
      // Reset state machine on error
      setChatState(DEFAULT_STATE)
    } finally {
      setLoading(false)
    }
  }

  const clearChat = () => {
    sessionStorage.removeItem('chat_messages')
    sessionStorage.removeItem('chat_state')
    setMessages([{
      role: 'assistant',
      content: 'Hi! How can I help you today?',
      timestamp: new Date(),
    }])
    setChatState(DEFAULT_STATE)
  }

  const tableNumber = user ? sessionStorage.getItem(`table_${user.user_id}`) : null

  // Input placeholder changes based on state
  const getPlaceholder = () => {
    if (recording) return '🎙️ Recording...'
    if (chatState.pendingAction === 'cancel_selection') return 'e.g. "cancel order #2"'
    if (chatState.pendingAction === 'mod_selection') return 'e.g. "order #3"'
    if (chatState.pendingAction === 'mod_details') return 'Describe your change...'
    if (chatState.mode === 'ordering') return '"2 burgers and a coffee"'
    if (chatState.mode === 'booking') return '"Book for 4, tomorrow 7pm"'
    return 'Ask me anything...'
  }

  return (
    <>
      {/* Floating button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-primary-500 to-primary-600 text-white shadow-lg hover:shadow-xl hover:scale-105 transition-all flex items-center justify-center"
        >
          <MessageCircle size={24} />
          {chatState.pendingAction && (
            <span className="absolute -top-1 -right-1 w-4 h-4 bg-orange-500 rounded-full" />
          )}
        </button>
      )}

      {/* Chat drawer */}
      {open && (
        <div className="fixed bottom-0 right-0 z-50 flex items-end sm:items-end sm:justify-end sm:p-6 pointer-events-none">
          <div
            className="absolute inset-0 bg-black/30 sm:hidden pointer-events-auto"
            onClick={() => setOpen(false)}
          />

          <div className="relative bg-white w-full sm:w-96 h-[85vh] sm:h-[600px] rounded-t-3xl sm:rounded-2xl shadow-2xl flex flex-col pointer-events-auto">

            {/* Header */}
            <div className="bg-gradient-to-r from-primary-500 to-primary-600 text-white px-5 py-4 rounded-t-3xl sm:rounded-t-2xl flex justify-between items-center">
              <div>
                <p className="font-bold">AI Concierge</p>
                <p className="text-xs text-white/70">
                  {chatState.pendingAction === 'cancel_selection' && '⏳ Waiting for order number (cancel)'}
                  {chatState.pendingAction === 'mod_selection' && '⏳ Waiting for order number (modify)'}
                  {chatState.pendingAction === 'mod_details' && `⏳ Waiting for change details — Order #${chatState.pendingOrderNum}`}
                  {!chatState.pendingAction && `Mode: ${chatState.mode}`}
                  {tableNumber ? ` · Table ${tableNumber}` : ' · No table set'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={clearChat}
                  className="text-xs text-white/60 hover:text-white transition-colors"
                >
                  Clear
                </button>
                <button onClick={() => setOpen(false)} className="hover:opacity-70 transition-opacity">
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Mode pills — disabled during pending state */}
            <div className="flex gap-2 px-4 py-2 border-b border-gray-100">
              {(['general', 'ordering', 'booking'] as ChatMode[]).map(m => (
                <button
                  key={m}
                  onClick={() => {
                    if (!chatState.pendingAction) {
                      setChatState(prev => ({ ...prev, mode: m }))
                    }
                  }}
                  disabled={!!chatState.pendingAction}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                    chatState.mode === m
                      ? 'bg-primary-500 text-white'
                      : 'bg-gray-100 text-gray-500'
                  } ${chatState.pendingAction ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  {m}
                </button>
              ))}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-line ${
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
                  <div className="bg-gray-100 px-4 py-3 rounded-2xl rounded-bl-sm flex gap-1">
                    {[0, 1, 2].map(i => (
                      <div
                        key={i}
                        className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${i * 150}ms` }}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t border-gray-100 flex gap-2">
              <button
                onMouseDown={startRecording}
                onMouseUp={stopRecording}
                onTouchStart={startRecording}
                onTouchEnd={stopRecording}
                className={`px-3 py-2 rounded-xl border-2 transition-all ${
                  recording
                    ? 'border-red-400 bg-red-50 text-red-500 animate-pulse'
                    : 'border-gray-200 text-gray-400 hover:border-primary-300'
                }`}
                title="Hold to record"
              >
                <Mic size={16} />
              </button>
              <input
                className="input flex-1 text-sm"
                placeholder={getPlaceholder()}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
              />
              <button
                onClick={sendMessage}
                disabled={loading}
                className="btn-primary px-3 py-2"
              >
                <Send size={16} />
              </button>
            </div>

          </div>
        </div>
      )}
    </>
  )
}
