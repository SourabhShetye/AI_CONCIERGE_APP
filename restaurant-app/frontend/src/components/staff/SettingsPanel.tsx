import { useState, useEffect } from 'react'
import { Save } from 'lucide-react'
import toast from 'react-hot-toast'
import { settingsApi } from '@/services/api'

export default function SettingsPanel() {
  const [form, setForm] = useState({
    wifi_password: '',
    opening_hours: '',
    parking_info: '',
    ai_context: '',
    table_count: 20,
    max_party_size: 10,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    settingsApi
      .get()
      .then((res) => {
        if (res.data) setForm((prev) => ({ ...prev, ...res.data }))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await settingsApi.update(form)
      toast.success('Settings saved!')
    } catch {
      toast.error('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleChange = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  const restaurantId = import.meta.env.VITE_RESTAURANT_ID
  const apiUrl = import.meta.env.VITE_API_URL

  if (loading) {
    return <div className="text-center py-20 text-gray-400">Loading settings...</div>
  }

  return (
    <div className="max-w-2xl space-y-5">
      <h2 className="text-2xl font-bold">Policies and Settings</h2>

      <div className="card space-y-4">
        <h3 className="font-semibold text-gray-700">General Info</h3>
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">
            WiFi Password
          </label>
          <input
            className="input"
            placeholder="e.g. Restaurant2024"
            value={form.wifi_password}
            onChange={handleChange('wifi_password')}
          />
        </div>
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">
            Opening Hours
          </label>
          <input
            className="input"
            placeholder="e.g. Mon-Fri 9am-11pm"
            value={form.opening_hours}
            onChange={handleChange('opening_hours')}
          />
        </div>
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">
            Parking Info
          </label>
          <input
            className="input"
            placeholder="e.g. Free parking in basement"
            value={form.parking_info}
            onChange={handleChange('parking_info')}
          />
        </div>
      </div>

      <div className="card space-y-4">
        <h3 className="font-semibold text-gray-700">Table Management</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">
              Total Tables
            </label>
            <input
              className="input"
              type="number"
              min={1}
              value={form.table_count}
              onChange={handleChange('table_count')}
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">
              Max Party Size
            </label>
            <input
              className="input"
              type="number"
              min={1}
              value={form.max_party_size}
              onChange={handleChange('max_party_size')}
            />
          </div>
        </div>
      </div>

      <div className="card space-y-3">
        <h3 className="font-semibold text-gray-700">AI Context Injection</h3>
        <p className="text-xs text-gray-500">
          This text is injected into every AI prompt. Use it to add specials or restrictions.
        </p>
        <textarea
          className="input resize-none h-32"
          placeholder="e.g. Today's special: Grilled Salmon is 20% off."
          value={form.ai_context}
          onChange={handleChange('ai_context')}
        />
      </div>

      <div className="card space-y-4">
        <h3 className="font-semibold text-gray-700">QR Codes</h3>
        <p className="text-xs text-gray-500">
          Print these and place on tables. Customers scan to open the ordering portal directly.
        </p>
        <a
          href={`${apiUrl}/api/qr/${restaurantId}?format=html`}
          target="_blank"
          rel="noreferrer"
          className="btn-secondary text-sm inline-block"
        >
          View Restaurant QR
        </a>
        <div className="flex gap-2 flex-wrap">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
            <a
              key={n}
              href={`${apiUrl}/api/qr/${restaurantId}?table=${n}&format=html`}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary-600 hover:underline px-2 py-1 border border-primary-200 rounded-lg"
            >
              Table {n}
            </a>
          ))}
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="btn-primary flex items-center gap-2"
      >
        <Save size={16} />
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  )
}