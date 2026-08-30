import { useEffect, useRef, useState } from 'react'
import { searchAPErpInvoices } from './api'
import { errorMessage } from './format'

type VendorCandidate = {
  vendor_number: string
  vendor_name: string | null
  sort_name: string | null
}

export default function APVendorNumberSearchField({
  value,
  disabled,
  onSelect,
  onChangeText,
}: {
  value: string
  disabled: boolean
  onSelect: (vendorNumber: string, vendorName: string | null) => void
  onChangeText: (value: string) => void
}) {
  const [query, setQuery] = useState(value)
  const [results, setResults] = useState<VendorCandidate[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    setQuery(value)
  }, [value])

  useEffect(() => {
    const trimmed = query.trim()
    const searchable = trimmed.length > 0 && (/^\d+$/.test(trimmed) || trimmed.length >= 2)
    if (!searchable) {
      setResults([])
      setStatus('idle')
      return undefined
    }
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setStatus('loading')
    setError('')
    const timeoutId = window.setTimeout(() => {
      searchAPErpInvoices(trimmed, '', controller.signal)
        .then((response) => {
          setResults(response.vendor_candidates)
          setStatus('success')
        })
        .catch((searchError: unknown) => {
          if (controller.signal.aborted) return
          setStatus('error')
          setError(errorMessage(searchError, 'Unable to search MaddenCo vendors.'))
        })
    }, 250)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [query])

  function selectCandidate(candidate: VendorCandidate) {
    onSelect(candidate.vendor_number, candidate.vendor_name)
    setQuery(candidate.vendor_number)
    setOpen(false)
    setResults([])
  }

  return (
    <div className="ap-vendor-search">
      <input
        value={query}
        placeholder="Vendor number or vendor name"
        disabled={disabled}
        onChange={(event) => {
          const next = event.target.value
          setQuery(next)
          onChangeText(next)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && !disabled && (status === 'loading' || status === 'error' || results.length > 0) && (
        <div className="ap-vendor-search-results">
          {status === 'loading' && <p className="ap-empty-inline">Searching MaddenCo…</p>}
          {status === 'error' && <p className="ap-empty-inline">{error}</p>}
          {status === 'success' && results.length === 0 && (
            <p className="ap-empty-inline">No matching MaddenCo vendors.</p>
          )}
          {results.map((candidate) => (
            <button
              type="button"
              key={candidate.vendor_number}
              onMouseDown={(event) => {
                event.preventDefault()
                selectCandidate(candidate)
              }}
            >
              <strong>{candidate.vendor_number}</strong>
              <span>{candidate.vendor_name || candidate.sort_name || 'Vendor name unavailable'}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
