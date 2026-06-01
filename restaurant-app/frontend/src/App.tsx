import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import LandingPage from './components/LandingPage'
import CustomerLogin from './components/customer/Login'
import CustomerApp from './components/customer/CustomerApp'
import StaffLogin from './components/staff/Login'
import StaffApp from './components/staff/StaffApp'

function ProtectedCustomer({ children }: { children: React.ReactNode }) {
  const { isCustomer } = useAuth()
  return isCustomer ? <>{children}</> : <Navigate to="/customer/login" replace />
}

function ProtectedStaff({ children }: { children: React.ReactNode }) {
  const { isStaff } = useAuth()
  return isStaff ? <>{children}</> : <Navigate to="/staff/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/customer/login" element={<CustomerLogin />} />
      <Route
        path="/customer/*"
        element={
          <ProtectedCustomer>
            <CustomerApp />
          </ProtectedCustomer>
        }
      />
      <Route path="/staff/login" element={<StaffLogin />} />
      <Route
        path="/staff/*"
        element={
          <ProtectedStaff>
            <StaffApp />
          </ProtectedStaff>
        }
      />
      <Route path="*" element={
        <div className="min-h-screen flex flex-col items-center justify-center text-center p-6">
          <div className="text-6xl mb-4">🍽️</div>
          <h1 className="text-2xl font-bold text-gray-800 mb-2">Page not found</h1>
          <p className="text-gray-500 mb-6">This page doesn't exist.</p>
          <a href="/" className="px-4 py-2 bg-primary-500 text-white rounded-xl text-sm font-medium">
            Go home
          </a>
        </div>
      } />
    </Routes>
  )
}
