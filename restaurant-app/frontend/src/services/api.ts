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
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const isLoginEndpoint =
      err.config?.url?.includes('/customer/login') ||
      err.config?.url?.includes('/customer/register') ||
      err.config?.url?.includes('/staff/login')

    if (err.response?.status === 401 && !isLoginEndpoint) {
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('user')
      window.location.href = '/'
    }
    return Promise.reject(err)
  }
)

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  customerRegister: (data: {
    name: string; pin: string; phone?: string;
    restaurant_id?: string; table_number?: string; allergies?: string[]
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
