/**
 * websocket.ts - WebSocket connection helpers.
 * Handles reconnection with exponential backoff.
 * SECURITY: JWT token passed as query param on connection.
 */

import type { WSEvent } from '@/types'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

type EventHandler = (event: WSEvent) => void

class WSClient {
  private ws: WebSocket | null = null
  private handlers: EventHandler[] = []
  private reconnectDelay = 1000
  private shouldReconnect = true
  private url = ''

  connect(url: string) {
    this.url = url.split('?')[0]
    this.shouldReconnect = true
    this._open()
  }

  private _open() {
    // Re-read token on every open attempt (handles token refresh between reconnects)
    const freshToken = sessionStorage.getItem('token') || ''
    const urlWithToken = this.url.split('?')[0] + `?token=${encodeURIComponent(freshToken)}`
    this.ws = new WebSocket(urlWithToken)

    this.ws.onopen = () => {
      console.log('WS connected:', this.url)
      this.reconnectDelay = 1000
    }

    this.ws.onmessage = (ev) => {
      try {
        const event: WSEvent = JSON.parse(ev.data)
        this.handlers.forEach((h) => h(event))
      } catch {
        console.warn('WS unparseable message:', ev.data)
      }
    }

    this.ws.onclose = () => {
      if (this.shouldReconnect) {
        console.log(`WS disconnected. Reconnecting in ${this.reconnectDelay}ms...`)
        setTimeout(() => this._open(), this.reconnectDelay)
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000)
      }
    }

    this.ws.onerror = (e) => console.error('WS error:', e)
  }

  on(handler: EventHandler) {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  disconnect() {
    this.shouldReconnect = false
    this.ws?.close()
    this.ws = null
  }
}

// ── SECURITY FIX: Both factory functions now read token from sessionStorage
// and append it as ?token= query param so the backend can verify identity
// before accepting the WebSocket connection.

export function createCustomerWS(userId: string): WSClient {
  const client = new WSClient()
  client.connect(`${WS_URL}/ws/customer/${userId}`)  // no token here
  return client
}

export function createKitchenWS(restaurantId: string): WSClient {
  const client = new WSClient()
  client.connect(`${WS_URL}/ws/kitchen/${restaurantId}`)  // no token here
  return client
}