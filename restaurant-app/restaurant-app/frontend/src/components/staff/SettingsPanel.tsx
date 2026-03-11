import { useState, useEffect } from 'react'
import { Save } from 'lucide-react'
import toast from 'react-hot-toast'
import { settingsApi } from '@/services/api'

export default function SettingsPanel() {
  const [form, setForm] = useState({
    wifi_password: '', opening_hours: '', parking_info: '',
    ai_context: '', table_count: 20, max_party_size: 10,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    settingsApi.get()
      .then((res) => { if (res.data) setForm({ ...form, ...res.data }) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await settingsApi.update(form)
      toast.success('Settings saved!')
    } catch { toast.error('Failed to save settings') }
    finally { setSaving(false) }
  }

  const f = (field: string) => ({
    value: (form as any)[field],
    onChange: (e: any) => setForm({ ...form, [field]: e.target.value }),
  })

  if (loading) return <div className="text-center py-20 text-gray-400">Loading settings...</div>

  return (
    <div className="max-w-2xl space-y-5">
      <h2 className="text-2xl font-bold">Policies & Settings</h2>

      <div className="card space-y-4">
        <h3 className="font-semibold text-gray-700">General Info</h3>
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">WiFi Password</label>
          <input className="input" placeholder="e.g. Restaurant2024" {...f('wifi_password')} />
        </div>
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">Opening Hours</label>
          <input className="input" placeholder="e.g. Mon-Fri 9am-11pm, Sat-Sun 10am-12am" {...f('opening_hours')} />
        </div>
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">Parking Info</label>
          <input className="input" placeholder="e.g. Free parking available in basement" {...f('parking_info')} />
        </div>
      </div>

      <div className="card space-y-4">
        <h3 className="font-semibold text-gray-700">Table Management</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Total Tables</label>
            <input className="input" type="number" min={1} {...f('table_count')} />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Max Party Size</label>
            <input className="input" type="number" min={1} {...f('max_party_size')} />
          </div>
        </div>
      </div>

      <div className="card space-y-3">
        <h3 className="font-semibold text-gray-700">AI Context Injection</h3>
        <p className="text-xs text-gray-500">This text is injected into the AI prompt for every order. Use it to add specials, restrictions, or custom instructions.</p>
        <textarea
          className="input resize-none h-32"
          placeholder="e.g. Today's special: Grilled Salmon is 20% off. We are out of pasta dishes today."
          {...f('ai_context')}
        />
      </div>

      <button onClick={handleSave} disabled={saving} className="btn-primary flex items-center gap-2">
        <Save size={16} />
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  )
}
