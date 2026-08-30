import { useEffect, useState } from 'react'
import { getAPVendorTermsReference, upsertAPVendorTermsReference } from './api'
import { errorMessage } from './format'
import type { APVendorTermsReferenceRecord, APVendorTermsReferenceUpsert } from './types'

type DraftRow = {
  terms_code: string
  isNew: boolean
  discount_percent: string
  num_periods: string
  num_months: string
  num_days: string
  second_period: string
  third_period: string
  next_period: string
  day_of_month: string
  cutoff_day: string
  description: string
}

const EMPTY_DRAFT: DraftRow = {
  terms_code: '',
  isNew: true,
  discount_percent: '0',
  num_periods: '',
  num_months: '',
  num_days: '',
  second_period: '',
  third_period: '',
  next_period: '',
  day_of_month: '',
  cutoff_day: '',
  description: '',
}

function toDraft(record: APVendorTermsReferenceRecord): DraftRow {
  return {
    terms_code: record.terms_code,
    isNew: false,
    discount_percent: String(record.discount_percent),
    num_periods: record.num_periods == null ? '' : String(record.num_periods),
    num_months: record.num_months == null ? '' : String(record.num_months),
    num_days: record.num_days == null ? '' : String(record.num_days),
    second_period: record.second_period == null ? '' : String(record.second_period),
    third_period: record.third_period == null ? '' : String(record.third_period),
    next_period: record.next_period == null ? '' : String(record.next_period),
    day_of_month: record.day_of_month == null ? '' : String(record.day_of_month),
    cutoff_day: record.cutoff_day == null ? '' : String(record.cutoff_day),
    description: record.description,
  }
}

function toPayload(draft: DraftRow): APVendorTermsReferenceUpsert {
  const int = (value: string): number | null => (value.trim() === '' ? null : Number(value))
  return {
    discount_percent: Number(draft.discount_percent) || 0,
    num_periods: int(draft.num_periods),
    num_months: int(draft.num_months),
    num_days: int(draft.num_days),
    second_period: int(draft.second_period),
    third_period: int(draft.third_period),
    next_period: int(draft.next_period),
    day_of_month: int(draft.day_of_month),
    cutoff_day: int(draft.cutoff_day),
    description: draft.description,
  }
}

type NumericFieldKey = Exclude<keyof DraftRow, 'terms_code' | 'isNew' | 'description'>

const NUMERIC_FIELDS: Array<{ key: NumericFieldKey; label: string }> = [
  { key: 'discount_percent', label: '%Dsc' },
  { key: 'num_periods', label: '#ofP' },
  { key: 'num_months', label: '#ofM' },
  { key: 'num_days', label: '#ofD' },
  { key: 'second_period', label: '#2nd' },
  { key: 'third_period', label: '#3rd' },
  { key: 'next_period', label: '#Nxt' },
  { key: 'day_of_month', label: 'DofM' },
  { key: 'cutoff_day', label: 'CutOff' },
]

export default function APVendorTermsReference() {
  const [rows, setRows] = useState<DraftRow[]>([])
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [error, setError] = useState('')
  const [savingCode, setSavingCode] = useState<string | null>(null)
  const [rowError, setRowError] = useState<Record<string, string>>({})

  useEffect(() => {
    const controller = new AbortController()
    getAPVendorTermsReference(controller.signal)
      .then((response) => {
        setRows(response.items.map(toDraft))
        setStatus('success')
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return
        setStatus('error')
        setError(errorMessage(loadError, 'Unable to load the vendor terms reference.'))
      })
    return () => controller.abort()
  }, [])

  function updateRow(index: number, key: keyof DraftRow, value: string) {
    setRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)),
    )
  }

  function addRow() {
    setRows((current) => [...current, { ...EMPTY_DRAFT }])
  }

  async function saveRow(index: number) {
    const row = rows[index]
    const termsCode = row.terms_code.trim()
    if (!termsCode) {
      setRowError((current) => ({ ...current, [`draft-${index}`]: 'A terms code is required.' }))
      return
    }
    setSavingCode(termsCode)
    setRowError((current) => {
      const next = { ...current }
      delete next[`draft-${index}`]
      delete next[termsCode]
      return next
    })
    try {
      await upsertAPVendorTermsReference(termsCode, toPayload(row))
      setRows((current) =>
        current.map((existing, existingIndex) =>
          existingIndex === index ? { ...existing, terms_code: termsCode, isNew: false } : existing,
        ),
      )
    } catch (saveError) {
      setRowError((current) => ({
        ...current,
        [termsCode]: errorMessage(saveError, 'Unable to save this terms code.'),
      }))
    } finally {
      setSavingCode(null)
    }
  }

  if (status === 'loading') {
    return <p className="ap-empty-inline">Loading vendor terms reference…</p>
  }
  if (status === 'error') {
    return <p className="ap-empty-inline">{error}</p>
  }

  return (
    <div className="ap-terms-reference">
      <div className="ap-vendor-toolbar">
        <div>
          <span className="ap-kicker">Local reference · you maintain this</span>
          <h3>Vendor Terms Reference</h3>
          <p>
            MaddenCo has no terms-code-to-description lookup table; this is a local copy of
            the "Work with AP Terms Code" screen you maintain here. Only a flat discount
            percent with a plain #ofD (days-from-invoice-date) value is used to compute
            Discounts Available today — day-of-month/cutoff ("proximo") terms are stored for
            reference but excluded from that calculation.
          </p>
        </div>
        <button type="button" className="ap-secondary-button" onClick={addRow}>
          Add terms code
        </button>
      </div>
      <div className="ap-vendor-table-wrap">
        <table className="ap-vendor-table">
          <thead>
            <tr>
              <th>Code</th>
              {NUMERIC_FIELDS.map((field) => (
                <th key={field.key}>{field.label}</th>
              ))}
              <th>Description</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.terms_code || `draft-${index}`}>
                <td>
                  <input
                    value={row.terms_code}
                    onChange={(event) => updateRow(index, 'terms_code', event.target.value)}
                    readOnly={!row.isNew}
                    style={{ width: '4rem' }}
                  />
                </td>
                {NUMERIC_FIELDS.map((field) => (
                  <td key={field.key}>
                    <input
                      value={row[field.key]}
                      onChange={(event) => updateRow(index, field.key, event.target.value)}
                      style={{ width: '3.5rem' }}
                    />
                  </td>
                ))}
                <td>
                  <input
                    value={row.description}
                    onChange={(event) => updateRow(index, 'description', event.target.value)}
                    style={{ width: '12rem' }}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="ap-secondary-button"
                    onClick={() => void saveRow(index)}
                    disabled={savingCode === row.terms_code.trim()}
                  >
                    {savingCode === row.terms_code.trim() ? 'Saving…' : 'Save'}
                  </button>
                  {(rowError[`draft-${index}`] || rowError[row.terms_code.trim()]) && (
                    <small className="ap-form-error">
                      {rowError[`draft-${index}`] || rowError[row.terms_code.trim()]}
                    </small>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
