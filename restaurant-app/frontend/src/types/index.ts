// ─── Auth ─────────────────────────────────────────────────────────────────────

export type StaffRole = 'admin' | 'chef' | 'manager'

export interface AuthUser {
  user_id: string
  name: string
  role: 'customer' | StaffRole
  restaurant_id: string
  access_token: string
  visit_count?: number
  total_spend?: number
  tags?: string[]
}

// ─── Menu ─────────────────────────────────────────────────────────────────────

export interface MenuItem {
  id: string
  restaurant_id: string
  name: string
  description?: string
  price: number
  category: 'Starters' | 'Mains' | 'Drinks' | 'Desserts' | string
  sold_out: boolean
  allergens?: string[]
}

// ─── Orders ───────────────────────────────────────────────────────────────────

export interface OrderItem {
  name: string
  quantity: number
  unit_price: number
  total_price: number
}

export type OrderStatus = 'pending' | 'preparing' | 'ready' | 'completed' | 'cancelled'
export type CancellationStatus = 'none' | 'requested' | 'approved' | 'rejected'
export type ModificationStatus = 'none' | 'requested' | 'approved' | 'rejected'

export interface Order {
  id: string
  restaurant_id: string
  user_id: string
  customer_name: string
  table_number: string
  items: OrderItem[]
  price: number
  status: OrderStatus
  cancellation_status: CancellationStatus
  modification_status: ModificationStatus
  allergy_warnings?: string[]
  created_at: string
  daily_order_number?: number
}

export interface PlaceOrderResponse extends Order {
  sold_out_items?: string[]
  unrecognized_items?: string[]
}

// ─── Cart ─────────────────────────────────────────────────────────────────────

export interface CartItem extends OrderItem {
  menu_item_id: string
}

// ─── Bookings ─────────────────────────────────────────────────────────────────

export type BookingStatus = 'confirmed' | 'cancelled' | 'completed'

export interface Booking {
  id: string
  restaurant_id: string
  user_id: string
  customer_name: string
  party_size: number
  booking_time: string
  status: BookingStatus
  special_requests?: string
  created_at: string
  assigned_table_id?: string     
  assigned_table_number?: string
}

// ─── CRM ──────────────────────────────────────────────────────────────────────

export interface CustomerInsight {
  id: string
  name: string
  phone?: string
  visit_count: number
  total_spend: number
  tags: string[]
  last_visit?: string
  allergies?: string[]
}

// ─── WebSocket events ─────────────────────────────────────────────────────────

export interface WSEvent {
  type:
    | 'order_ready'
    | 'order_cancelled'
    | 'modification_approved'
    | 'modification_rejected'
    | 'cancellation_rejected'
    | 'feedback_requested'
    | 'new_order'
    | 'modification_request'
    | 'cancellation_request'
  data: Record<string, unknown>
}

// ─── Table (billing) ──────────────────────────────────────────────────────────

export interface TableSummary {
  table_number: string
  orders: Order[]
  total: number
}

// ─── Settings ─────────────────────────────────────────────────────────────────

export interface RestaurantSettings {
  wifi_password?: string
  opening_hours?: string
  parking_info?: string
  ai_context?: string
  table_count?: number
  max_party_size?: number
}
