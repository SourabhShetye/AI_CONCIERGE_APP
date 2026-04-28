/**
 * api.ts - Centralised API service layer.
 * All fetch calls go through here. Token is read from localStorage.
 */

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({ baseURL: BASE_URL })

// Attach JWT to every request automatically
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401, only redirect to home if it's NOT a login attempt
// Login failures should show an error message, not redirect
let isRefreshing = false
let failedQueue: Array<{resolve: Function, reject: Function}> = []

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token)
  })
  failedQueue = []
}

api.interceptors.response.use(
  (response) => response,  // Pass through success responses
  async (error) => {
    const originalRequest = error.config

    // Only attempt refresh on 401, and only once per request
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Queue requests while refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      const refreshToken = sessionStorage.getItem('refresh_token')
      if (!refreshToken) {
        // No refresh token — force logout
        sessionStorage.clear()
        window.location.href = '/customer/login'
        return Promise.reject(error)
      }

      try {
        const response = await axios.post(
          `${import.meta.env.VITE_API_URL}/api/auth/refresh`,
          { refresh_token: refreshToken }
        )

        const { access_token, refresh_token: newRefreshToken } = response.data

        // Store new tokens
        sessionStorage.setItem('token', access_token)
        sessionStorage.setItem('refresh_token', newRefreshToken)

        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${access_token}`
        processQueue(null, access_token)

        return api(originalRequest)
      } catch (refreshError) {
        // Refresh failed — clear session and redirect to login
        processQueue(refreshError, null)
        sessionStorage.clear()
        window.location.href = '/customer/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  customerRegister: (data: {
    name: string; pin: string; phone?: string;
    restaurant_id?: string; table_number?: string; allergies?: string[];
    health_data_consent?: boolean; terms_accepted?: boolean;
  }) => api.post('/api/customer/register', data),

  customerLogin: (data: {
    name: string; pin: string; restaurant_id?: string; table_number?: string
  }) => api.post('/api/customer/login', data),

  staffLogin: (data: {
    username: string; password: string; restaurant_id?: string
  }) => api.post('/api/staff/login', data),
}

// ─── Menu ─────────────────────────────────────────────────────────────────────

export const menuApi = {
  getMenu: (restaurant_id?: string) =>
    api.get('/api/menu', { params: { restaurant_id } }),

  createItem: (data: object) => api.post('/api/staff/menu', data),
  updateItem: (id: string, data: object) => api.put(`/api/staff/menu/${id}`, data),
  deleteItem: (id: string) => api.delete(`/api/staff/menu/${id}`),
}

// ─── Orders ───────────────────────────────────────────────────────────────────

export const orderApi = {
  placeOrder: (data: { natural_language_input: string; table_number: string; restaurant_id?: string }) =>
    api.post('/api/orders', data),

  getMyOrders: () => api.get('/api/orders'),

  modifyOrder: (id: string, modification_text: string) =>
    api.put(`/api/orders/${id}/modify`, { modification_text }),

  cancelOrder: (id: string) => api.delete(`/api/orders/${id}`),

  // Staff actions
  getKitchenOrders: () => api.get('/api/staff/orders'),
  markReady: (id: string) => api.put(`/api/staff/orders/${id}/ready`),
  approveModification: (id: string) => api.put(`/api/staff/orders/${id}/approve_modification`),
  rejectModification: (id: string) => api.put(`/api/staff/orders/${id}/reject_modification`),
  approveCancellation: (id: string) => api.put(`/api/staff/orders/${id}/approve_cancellation`),
  rejectCancellation: (id: string) => api.put(`/api/staff/orders/${id}/reject_cancellation`),
}

// ─── Tables & Billing ─────────────────────────────────────────────────────────

export const tableApi = {
  getLiveTables: () => api.get('/api/staff/tables'),
  closeTable: (tableNumber: string) => api.post(`/api/staff/tables/${tableNumber}/close`),
  getBill: (tableNumber: string, restaurant_id?: string) =>
    api.get(`/api/bill/${tableNumber}`, { params: { restaurant_id } }),
}

// ─── Bookings ─────────────────────────────────────────────────────────────────

export const bookingApi = {
  createBooking: (data: {
    party_size: number; booking_time: string; special_requests?: string; restaurant_id?: string
  }) => api.post('/api/bookings', data),

  getMyBookings: () => api.get('/api/bookings'),
  cancelBooking: (id: string) => api.delete(`/api/bookings/${id}`),

  // Staff
  getStaffBookings: () => api.get('/api/staff/bookings'),
  confirmBooking: (id: string) => api.put(`/api/staff/bookings/${id}/confirm`),
  staffCancelBooking: (id: string) => api.delete(`/api/staff/bookings/${id}`),
  purgeBooking: (id: string) => api.delete(`/api/staff/bookings/${id}/purge`),
}

// ─── Feedback ─────────────────────────────────────────────────────────────────

export const feedbackApi = {
  submit: (data: {
    order_ratings?: Record<string, number>; overall_rating: number; comments?: string; restaurant_id?: string
  }) => api.post('/api/feedback', data),
}

// ─── CRM ──────────────────────────────────────────────────────────────────────

export const crmApi = {
  getCustomers: () => api.get('/api/staff/crm'),
}

// ─── Settings ─────────────────────────────────────────────────────────────────

export const settingsApi = {
  get: () => api.get('/api/staff/settings'),
  update: (data: object) => api.put('/api/staff/settings', data),
}
