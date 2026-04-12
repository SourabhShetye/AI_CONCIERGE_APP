import { useState, useEffect } from 'react'
import { Save, Plus, Trash2, Edit2, Check, X, Users } from 'lucide-react'
import toast from 'react-hot-toast'
import { settingsApi, api } from '@/services/api'

interface TableEntry {
  id?: string
  table_number: string
  capacity: number
  is_active: boolean
  isNew?: boolean
  isEditing?: boolean
}

export default function SettingsPanel() {
  const [form, setForm] = useState({
    wifi_password: '', opening_hours: '', parking_info: '',
    ai_context: '', table_count: 20, max_party_size: 10,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [tables, setTables] = useState<TableEntry[]>([])
  const [tablesLoading, setTablesLoading] = useState(true)
  const [editingTable, setEditingTable] = useState<string | null>(null)
  const [editValues, setEditValues] = useState<{ table_number: string; capacity: number }>({
    table_number: '', capacity: 2
  })

  useEffect(() => {
    settingsApi.get()
      .then((res) => { if (res.data) setForm({ ...form, ...res.data }) })
      .catch(() => {})
      .finally(() => setLoading(false))

    fetchTables()
  }, [])

  const fetchTables = async () => {
    try {
      const res = await api.get('/api/staff/tables-inventory')
      setTables(res.data)
    } catch {
      // Tables inventory may not exist yet
      setTables([])
    } finally {
      setTablesLoading(false)
    }
  }

  const handleSaveSettings = async () => {
    setSaving(true)
    try {
      await settingsApi.update(form)
      toast.success('Settings saved!')
    } catch { toast.error('Failed to save settings') }
    finally { setSaving(false) }
  }

  const addTable = () => {
    const newTable: TableEntry = {
      table_number: String(tables.length + 1),
      capacity: 4,
      is_active: true,
      isNew: true,
    }
    setTables(prev => [...prev, newTable])
    setEditingTable('new')
    setEditValues({ table_number: newTable.table_number, capacity: newTable.capacity })
  }

  const saveNewTable = async () => {
    try {
      const res = await api.post('/api/staff/tables-inventory', {
        table_number: editValues.table_number,
        capacity: editValues.capacity,
        is_active: true,
      })
      setTables(prev => [
        ...prev.filter(t => !t.isNew),
        res.data,
      ])
      setEditingTable(null)
      toast.success(`Table ${editValues.table_number} added`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to add table')
    }
  }

  const startEdit = (table: TableEntry) => {
    setEditingTable(table.id || 'new')
    setEditValues({ table_number: table.table_number, capacity: table.capacity })
  }

  const saveEdit = async (tableId: string) => {
    try {
      await api.put(`/api/staff/tables-inventory/${tableId}`, {
        table_number: editValues.table_number,
        capacity: editValues.capacity,
      })
      setTables(prev => prev.map(t =>
        t.id === tableId
          ? { ...t, table_number: editValues.table_number, capacity: editValues.capacity }
          : t
      ))
      setEditingTable(null)
      toast.success('Table updated')
    } catch { toast.error('Failed to update table') }
  }

  const toggleActive = async (table: TableEntry) => {
    if (!table.id) return
    try {
      await api.put(`/api/staff/tables-inventory/${table.id}`, {
        is_active: !table.is_active,
      })
      setTables(prev => prev.map(t =>
        t.id === table.id ? { ...t, is_active: !t.is_active } : t
      ))
    } catch { toast.error('Failed to update table') }
  }

  const deleteTable = async (tableId: string) => {
    if (!confirm('Remove this table from inventory?')) return
    try {
      await api.delete(`/api/staff/tables-inventory/${tableId}`)
      setTables(prev => prev.filter(t => t.id !== tableId))
      toast.success('Table removed')
    } catch { toast.error('Failed to remove table') }
  }

  const cancelNewTable = () => {
    setTables(prev => prev.filter(t => !t.isNew))
    setEditingTable(null)
  }

  const f = (field: string) => ({
    value: (form as any)[field],
    onChange: (e: any) => setForm({ ...form, [field]: e.target.value }),
  })

  // Summary stats
  const totalSeats = tables.filter(t => t.is_active).reduce((sum, t) => sum + t.capacity, 0)
  const activeTables = tables.filter(t => t.is_active).length

  if (loading) return <div className="text-center py-20 text-gray-400">Loading settings...</div>

  return (
    <div className="max-w-3xl space-y-6">
      <h2 className="text-2xl font-bold">Policies & Settings</h2>

      {/* ── Table Inventory ─────────────────────────────────────────────── */}
      <div className="card space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="font-semibold text-gray-700">Table Inventory</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {activeTables} active tables · {totalSeats} total seats
            </p>
          </div>
          <button onClick={addTable} className="btn-primary flex items-center gap-1.5 py-2 px-4 text-sm">
            <Plus size={14} /> Add Table
          </button>
        </div>

        <p className="text-xs text-gray-500 bg-blue-50 border border-blue-100 rounded-xl p-3">
          💡 When customers book, the system automatically assigns the smallest available table
          that fits their party. No table = falls back to simple capacity check.
        </p>

        {tablesLoading ? (
          <div className="text-center py-8 text-gray-400 text-sm">Loading tables...</div>
        ) : tables.length === 0 ? (
          <div className="text-center py-8 text-gray-400">
            <Users size={32} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">No tables configured yet.</p>
            <p className="text-xs">Add tables to enable smart booking allocation.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Column headers */}
            <div className="grid grid-cols-4 gap-3 px-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
              <span>Table #</span>
              <span>Capacity</span>
              <span>Status</span>
              <span>Actions</span>
            </div>

            {tables.map((table, idx) => {
              const isEditingThis = editingTable === (table.id || 'new') && (table.id || table.isNew)

              return (
                <div key={table.id || `new-${idx}`}
                  className={`grid grid-cols-4 gap-3 items-center p-3 rounded-xl border transition-all ${
                    table.is_active ? 'bg-white border-gray-100' : 'bg-gray-50 border-gray-100 opacity-60'
                  }`}
                >
                  {/* Table number */}
                  {isEditingThis ? (
                    <input
                      className="input text-sm py-1.5"
                      value={editValues.table_number}
                      onChange={e => setEditValues(prev => ({ ...prev, table_number: e.target.value }))}
                      placeholder="e.g. VIP"
                    />
                  ) : (
                    <span className="font-semibold text-sm">Table {table.table_number}</span>
                  )}

                  {/* Capacity */}
                  {isEditingThis ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min={1}
                        max={30}
                        className="input text-sm py-1.5 w-16"
                        value={editValues.capacity}
                        onChange={e => setEditValues(prev => ({ ...prev, capacity: parseInt(e.target.value) || 1 }))}
                      />
                      <span className="text-xs text-gray-400">seats</span>
                    </div>
                  ) : (
                    <span className="text-sm text-gray-600 flex items-center gap-1">
                      <Users size={12} className="text-gray-400" />
                      {table.capacity} seats
                    </span>
                  )}

                  {/* Status toggle */}
                  <button
                    onClick={() => !isEditingThis && table.id && toggleActive(table)}
                    disabled={isEditingThis || !table.id}
                    className={`text-xs font-medium px-2 py-1 rounded-lg transition-all ${
                      table.is_active
                        ? 'bg-green-100 text-green-700 hover:bg-green-200'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}
                  >
                    {table.is_active ? 'Active' : 'Inactive'}
                  </button>

                  {/* Actions */}
                  <div className="flex gap-1">
                    {isEditingThis ? (
                      <>
                        <button
                          onClick={() => table.isNew ? saveNewTable() : saveEdit(table.id!)}
                          className="w-7 h-7 rounded-lg bg-green-100 text-green-600 flex items-center justify-center hover:bg-green-200"
                        >
                          <Check size={13} />
                        </button>
                        <button
                          onClick={() => table.isNew ? cancelNewTable() : setEditingTable(null)}
                          className="w-7 h-7 rounded-lg bg-gray-100 text-gray-500 flex items-center justify-center hover:bg-gray-200"
                        >
                          <X size={13} />
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => startEdit(table)}
                          className="w-7 h-7 rounded-lg bg-blue-50 text-blue-500 flex items-center justify-center hover:bg-blue-100"
                        >
                          <Edit2 size={13} />
                        </button>
                        {table.id && (
                          <button
                            onClick={() => deleteTable(table.id!)}
                            className="w-7 h-7 rounded-lg bg-red-50 text-red-400 flex items-center justify-center hover:bg-red-100"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── General Info ─────────────────────────────────────────────────── */}
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

      {/* ── Fallback Capacity (used if no tables configured) ─────────────── */}
      <div className="card space-y-4">
        <div>
          <h3 className="font-semibold text-gray-700">Fallback Capacity</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            Used only if no table inventory is configured above.
          </p>
        </div>
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

      {/* ── AI Context ──────────────────────────────────────────────────── */}
      <div className="card space-y-3">
        <h3 className="font-semibold text-gray-700">AI Context Injection</h3>
        <p className="text-xs text-gray-500">
          Injected into every customer AI prompt. Use for specials, restrictions, or custom instructions.
        </p>
        <textarea
          className="input resize-none h-28"
          placeholder="e.g. Today's special: Grilled Salmon 20% off. We are fully booked on Friday evening."
          {...f('ai_context')}
        />
      </div>

      {/* ── QR Codes ─────────────────────────────────────────────────────── */}
      <div className="card space-y-3">
        <h3 className="font-semibold text-gray-700">QR Codes</h3>
        <p className="text-xs text-gray-500">
          Print and place on tables. Customers scan to open the ordering portal with table pre-filled.
        </p>
        <div className="flex gap-3 flex-wrap">
          <a
            href={`${import.meta.env.VITE_API_URL}/api/qr/${import.meta.env.VITE_RESTAURANT_ID}?format=html`}
            target="_blank" rel="noreferrer"
            className="btn-secondary text-sm"
          >
            Restaurant QR
          </a>
          {tables.filter(t => t.is_active && t.id).map(t => (
            <a
              key={t.id}
              href={`${import.meta.env.VITE_API_URL}/api/qr/${import.meta.env.VITE_RESTAURANT_ID}?table=${t.table_number}&format=html`}
              target="_blank" rel="noreferrer"
              className="text-xs text-primary-600 hover:underline px-2 py-1 bg-primary-50 rounded-lg"
            >
              Table {t.table_number}
            </a>
          ))}
        </div>
      </div>

      <button onClick={handleSaveSettings} disabled={saving} className="btn-primary flex items-center gap-2">
        <Save size={16} />
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  )
}
