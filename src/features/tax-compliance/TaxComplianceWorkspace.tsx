import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  checkCustomerExemption,
  createCustomerNote,
  getCustomerNotes,
  searchExemptionCodes,
  searchTaxAuthorities,
} from './api'
import type {
  CustomerExemptionCheckResponse,
  TaxAuthorityRecord,
  TaxComplianceNoteHistoryResponse,
  TaxExemptionCodeRecord,
} from './types'
import './TaxComplianceWorkspace.css'

type TabId = 'authorities' | 'exemption-codes' | 'customer-check'

const TABS: { id: TabId; label: string }[] = [
  { id: 'authorities', label: 'Tax Authorities' },
  { id: 'exemption-codes', label: 'Exemption Codes' },
  { id: 'customer-check', label: 'Customer Exemption Check' },
]

const percent = new Intl.NumberFormat('en-US', {
  style: 'percent',
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
})

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatPercent(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : percent.format(value)
}

function formatMoney(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : money.format(value)
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleDateString('en-US', { dateStyle: 'medium' })
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function matchStatusLabel(status: string): string {
  switch (status) {
    case 'matched':
      return 'Matched'
    case 'no_matching_exemption_code_found':
      return 'No matching exemption code found'
    case 'no_exemption_code_on_customer':
      return 'No exemption code on customer'
    default:
      return status
  }
}

function expirationStatusLabel(status: string): string {
  switch (status) {
    case 'current':
      return 'Current'
    case 'expired':
      return 'Expired'
    case 'no_expiration_date_on_file':
      return 'No expiration date on file'
    default:
      return status
  }
}

export default function TaxComplianceWorkspace() {
  const [activeTab, setActiveTab] = useState<TabId>('authorities')

  // --- Tax authorities tab ---
  const [authorityState, setAuthorityState] = useState('')
  const [authorityType, setAuthorityType] = useState('')
  const [authorityActiveOnly, setAuthorityActiveOnly] = useState(true)
  const [authorities, setAuthorities] = useState<TaxAuthorityRecord[]>([])
  const [authorityError, setAuthorityError] = useState('')
  const [authorityLoading, setAuthorityLoading] = useState(false)

  useEffect(() => {
    if (activeTab !== 'authorities') return
    const controller = new AbortController()
    setAuthorityLoading(true)
    searchTaxAuthorities(
      {
        state: authorityState,
        taxType: authorityType,
        activeOnly: authorityActiveOnly,
      },
      controller.signal,
    )
      .then((response) => {
        setAuthorities(response.authorities)
        setAuthorityError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setAuthorityError(errorMessage(error, 'Unable to load tax authorities.'))
      })
      .finally(() => setAuthorityLoading(false))
    return () => controller.abort()
  }, [activeTab, authorityState, authorityType, authorityActiveOnly])

  // --- Exemption codes tab ---
  const [exemptionState, setExemptionState] = useState('')
  const [exemptionType, setExemptionType] = useState('')
  const [exemptionActiveOnly, setExemptionActiveOnly] = useState(true)
  const [exemptionCodes, setExemptionCodes] = useState<TaxExemptionCodeRecord[]>([])
  const [exemptionError, setExemptionError] = useState('')
  const [exemptionLoading, setExemptionLoading] = useState(false)

  useEffect(() => {
    if (activeTab !== 'exemption-codes') return
    const controller = new AbortController()
    setExemptionLoading(true)
    const stateCode = exemptionState.trim() ? Number(exemptionState.trim()) : undefined
    searchExemptionCodes(
      {
        stateCode: Number.isFinite(stateCode) ? stateCode : undefined,
        taxType: exemptionType,
        activeOnly: exemptionActiveOnly,
      },
      controller.signal,
    )
      .then((response) => {
        setExemptionCodes(response.exemption_codes)
        setExemptionError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setExemptionError(errorMessage(error, 'Unable to load exemption codes.'))
      })
      .finally(() => setExemptionLoading(false))
    return () => controller.abort()
  }, [activeTab, exemptionState, exemptionType, exemptionActiveOnly])

  // --- Customer exemption check tab ---
  const [customerInput, setCustomerInput] = useState('')
  const [selectedCustomer, setSelectedCustomer] = useState<number | null>(null)
  const [checkResult, setCheckResult] = useState<CustomerExemptionCheckResponse | null>(null)
  const [checkError, setCheckError] = useState('')
  const [checkLoading, setCheckLoading] = useState(false)
  const [notes, setNotes] = useState<TaxComplianceNoteHistoryResponse | null>(null)

  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  function submitCustomerLookup(event: FormEvent) {
    event.preventDefault()
    const parsed = Number(customerInput.trim())
    if (!customerInput.trim() || !Number.isFinite(parsed) || parsed <= 0) {
      setCheckError('Enter a valid customer number.')
      return
    }
    setSelectedCustomer(parsed)
  }

  useEffect(() => {
    if (selectedCustomer == null) return
    const controller = new AbortController()
    setCheckLoading(true)
    setCheckError('')
    Promise.all([
      checkCustomerExemption(selectedCustomer, controller.signal),
      getCustomerNotes(selectedCustomer, controller.signal),
    ])
      .then(([checkResponse, notesResponse]) => {
        setCheckResult(checkResponse)
        setNotes(notesResponse)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setCheckResult(null)
        setNotes(null)
        setCheckError(errorMessage(error, 'Unable to load customer exemption evidence.'))
      })
      .finally(() => setCheckLoading(false))
    return () => controller.abort()
  }, [selectedCustomer])

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (selectedCustomer == null) return
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createCustomerNote(selectedCustomer, {
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
      })
      const refreshed = await getCustomerNotes(selectedCustomer)
      setNotes(refreshed)
      setNoteText('')
      setNoteSaveStatus('success')
      setNoteSaveMessage('Note saved. It is append-only and creates no ERP change.')
    } catch (error) {
      setNoteSaveStatus('error')
      setNoteSaveMessage(errorMessage(error, 'Unable to save the note.'))
    }
  }

  const gaps = useMemo(() => checkResult?.gaps ?? [], [checkResult])

  return (
    <section className="tc-shell">
      <header className="tc-header">
        <div>
          <span className="tc-kicker">Read-only MaddenCo evidence</span>
          <h2>Tax Compliance</h2>
          <p>
            Tax authority rates, tax exemption codes, and a deterministic
            customer exemption-code check — no invented risk score, no ERP
            write.
          </p>
        </div>
      </header>

      <nav className="tc-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={tab.id === activeTab ? 'tc-tab tc-tab--active' : 'tc-tab'}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === 'authorities' && (
        <div className="tc-panel">
          <form className="tc-filter-row" onSubmit={(event) => event.preventDefault()}>
            <label>
              State abbreviation
              <input
                value={authorityState}
                onChange={(event) => setAuthorityState(event.target.value)}
                placeholder="OH"
                maxLength={2}
              />
            </label>
            <label>
              Tax type code
              <input
                value={authorityType}
                onChange={(event) => setAuthorityType(event.target.value)}
                placeholder="ST"
                maxLength={2}
              />
            </label>
            <label className="tc-checkbox">
              <input
                type="checkbox"
                checked={authorityActiveOnly}
                onChange={(event) => setAuthorityActiveOnly(event.target.checked)}
              />
              Active only
            </label>
          </form>

          {authorityError && <p className="tc-error">{authorityError}</p>}
          {authorityLoading && <p className="tc-loading">Loading tax authorities…</p>}

          {!authorityLoading && authorities.length === 0 ? (
            <p className="tc-empty">No tax authorities matched.</p>
          ) : (
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Authority</th>
                    <th>State</th>
                    <th>Description</th>
                    <th>Type</th>
                    <th>Rate</th>
                    <th>Max tax</th>
                    <th>FET</th>
                    <th>Active</th>
                  </tr>
                </thead>
                <tbody>
                  {authorities.map((authority) => (
                    <tr key={`${authority.tax_authority}-${authority.state_code}`}>
                      <td>{authority.tax_authority}</td>
                      <td>{authority.state_abbreviation || authority.state_code}</td>
                      <td>{authority.description || 'Unavailable'}</td>
                      <td>{authority.tax_type_code || 'Unavailable'}</td>
                      <td>{formatPercent(authority.rate_percent)}</td>
                      <td>{formatMoney(authority.max_tax_amount)}</td>
                      <td>{authority.fet_applicable ? 'Yes' : 'No'}</td>
                      <td>{authority.active ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'exemption-codes' && (
        <div className="tc-panel">
          <form className="tc-filter-row" onSubmit={(event) => event.preventDefault()}>
            <label>
              State code
              <input
                value={exemptionState}
                onChange={(event) => setExemptionState(event.target.value)}
                placeholder="39"
                inputMode="numeric"
              />
            </label>
            <label>
              Tax type code
              <input
                value={exemptionType}
                onChange={(event) => setExemptionType(event.target.value)}
                placeholder="ST"
                maxLength={2}
              />
            </label>
            <label className="tc-checkbox">
              <input
                type="checkbox"
                checked={exemptionActiveOnly}
                onChange={(event) => setExemptionActiveOnly(event.target.checked)}
              />
              Active only
            </label>
          </form>

          {exemptionError && <p className="tc-error">{exemptionError}</p>}
          {exemptionLoading && <p className="tc-loading">Loading exemption codes…</p>}

          {!exemptionLoading && exemptionCodes.length === 0 ? (
            <p className="tc-empty">No exemption codes matched.</p>
          ) : (
            <div className="tc-table-wrap">
              <table className="tc-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>State</th>
                    <th>Description</th>
                    <th>Type</th>
                    <th>Override/Percent</th>
                    <th>% taxable</th>
                    <th>Rate</th>
                    <th>Max/line</th>
                    <th>Active</th>
                  </tr>
                </thead>
                <tbody>
                  {exemptionCodes.map((code) => (
                    <tr key={`${code.exempt_code}-${code.state_code}`}>
                      <td>{code.exempt_code}</td>
                      <td>{code.state_code}</td>
                      <td>{code.description || 'Unavailable'}</td>
                      <td>{code.tax_type_code || 'Unavailable'}</td>
                      <td>{code.override_or_percent_code || 'Unavailable'}</td>
                      <td>{formatPercent(code.percent_taxable)}</td>
                      <td>{formatPercent(code.rate_percent)}</td>
                      <td>{formatMoney(code.max_taxable_per_line)}</td>
                      <td>{code.active ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'customer-check' && (
        <div className="tc-panel">
          <form className="tc-filter-row" onSubmit={submitCustomerLookup}>
            <label>
              Customer number
              <input
                value={customerInput}
                onChange={(event) => setCustomerInput(event.target.value)}
                placeholder="e.g. 555444"
                inputMode="numeric"
              />
            </label>
            <button type="submit">Check exemption code</button>
          </form>

          {checkError && <p className="tc-error">{checkError}</p>}
          {checkLoading && <p className="tc-loading">Loading customer exemption evidence…</p>}

          {checkResult && (
            <div className="tc-evidence">
              <div className="tc-result-card">
                <div>
                  <h3>{checkResult.result.customer_name || 'Unnamed customer'}</h3>
                  <span>Customer #{checkResult.result.customer_number}</span>
                </div>
                <dl>
                  <div>
                    <dt>Exemption code on file</dt>
                    <dd>{checkResult.result.exemption_code_on_file || '(blank)'}</dd>
                  </div>
                  <div>
                    <dt>Match status</dt>
                    <dd className={`tc-status tc-status--${checkResult.result.match_status}`}>
                      {matchStatusLabel(checkResult.result.match_status)}
                    </dd>
                  </div>
                  <div>
                    <dt>FET exempt</dt>
                    <dd>{checkResult.result.fet_exempt ? 'Yes' : 'No'}</dd>
                  </div>
                  <div>
                    <dt>Certificate expiration date</dt>
                    <dd>{formatDate(checkResult.result.exemption_certificate_expiration_date)}</dd>
                  </div>
                  <div>
                    <dt>Expiration status</dt>
                    <dd className={`tc-status tc-status--${checkResult.result.expiration_status}`}>
                      {expirationStatusLabel(checkResult.result.expiration_status)}
                    </dd>
                  </div>
                </dl>

                {checkResult.result.matched_exemption_codes.length > 0 && (
                  <div className="tc-table-wrap">
                    <p className="tc-section-note">
                      Matching TMTAXE rows for this code (one per state where it is defined):
                    </p>
                    <table className="tc-table">
                      <thead>
                        <tr>
                          <th>Code</th>
                          <th>State</th>
                          <th>Description</th>
                          <th>Active</th>
                        </tr>
                      </thead>
                      <tbody>
                        {checkResult.result.matched_exemption_codes.map((code) => (
                          <tr key={`${code.exempt_code}-${code.state_code}`}>
                            <td>{code.exempt_code}</td>
                            <td>{code.state_code}</td>
                            <td>{code.description || 'Unavailable'}</td>
                            <td>{code.active ? 'Yes' : 'No'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="tc-gaps">
                <strong>What this evidence does not include</strong>
                <ul>
                  {gaps.map((gap) => (
                    <li key={gap.code}>
                      <strong>{gap.label}:</strong> {gap.explanation}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="tc-notes">
                <h4>Tax compliance notes</h4>
                <p className="tc-section-note">
                  Append-only. A note creates no ERP change, approval, or recommendation. Use
                  this to record certificate custody details the ERP does not track.
                </p>
                <form className="tc-note-form" onSubmit={submitNote}>
                  <label>
                    Your name
                    <input
                      value={authorIdentity}
                      onChange={(event) => setAuthorIdentity(event.target.value)}
                      placeholder="Name"
                    />
                  </label>
                  <label>
                    Note
                    <textarea
                      rows={3}
                      value={noteText}
                      onChange={(event) => setNoteText(event.target.value)}
                      placeholder="What did you observe or confirm about this customer's exemption status?"
                    />
                  </label>
                  <button type="submit" disabled={noteSaveStatus === 'saving'}>
                    {noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}
                  </button>
                  {noteSaveMessage && (
                    <p className={noteSaveStatus === 'error' ? 'tc-form-error' : 'tc-form-success'}>
                      {noteSaveMessage}
                    </p>
                  )}
                </form>
                {notes && notes.count > 0 && (
                  <ul className="tc-note-list">
                    {notes.notes.map((note) => (
                      <li key={note.note_id}>
                        <div>
                          <strong>{note.author_identity}</strong>
                          <span>{formatDateTime(note.created_at)}</span>
                        </div>
                        <p>{note.note}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
