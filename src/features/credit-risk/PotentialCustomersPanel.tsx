import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE } from '../../api/client'
import {
  getPotentialCustomers,
  updatePotentialCustomerReview,
  uploadPotentialCustomerApplication,
} from './api'
import type { PotentialCustomerAddress, PotentialCustomerRecord } from './types'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const date = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' })

function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

type ChoiceDraft = '' | 'yes' | 'no'

function choiceFrom(value: boolean | null | undefined): ChoiceDraft {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return ''
}

function choiceTo(value: ChoiceDraft): boolean | null {
  if (value === 'yes') return true
  if (value === 'no') return false
  return null
}

function emptyAddress(): PotentialCustomerAddress {
  return { street: '', city: '', state: '', zip: '' }
}

export default function PotentialCustomersPanel() {
  const [records, setRecords] = useState<PotentialCustomerRecord[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fieldDraft, setFieldDraft] = useState<Record<string, string>>({})
  const [addressDraft, setAddressDraft] = useState<{ shipping: PotentialCustomerAddress; billing: PotentialCustomerAddress }>({
    shipping: emptyAddress(),
    billing: emptyAddress(),
  })
  const [choiceDraft, setChoiceDraft] = useState<Record<string, ChoiceDraft>>({})
  const [setupDraft, setSetupDraft] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    try {
      setStatus('loading')
      const response = await getPotentialCustomers()
      setRecords(response.potential_customers)
      setSelectedId((current) => current || response.potential_customers[0]?.potential_customer_id || '')
      setStatus('ready')
      setMessage('')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Unable to load potential customers.')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const selected = useMemo(
    () => records.find((record) => record.potential_customer_id === selectedId) ?? null,
    [records, selectedId],
  )

  useEffect(() => {
    if (!selected) return
    setFieldDraft({
      legal_business_name: selected.fields.legal_business_name || '',
      trade_name: selected.fields.trade_name || '',
      type_of_business: selected.fields.type_of_business || '',
      business_phone: selected.fields.business_phone || '',
      primary_language: selected.fields.primary_language || '',
      cell_phone: selected.fields.cell_phone || '',
      county: selected.fields.county || '',
      email_address: selected.fields.email_address || '',
      federal_tax_id: selected.fields.federal_tax_id || '',
      manager_name: selected.fields.manager_name || '',
      year_started_business: selected.fields.year_started_business || '',
      accounts_payable_contact: selected.fields.accounts_payable_contact || '',
      previous_business_name: selected.fields.previous_business_name || '',
      sales_tax_exemption_reason: selected.fields.sales_tax_exemption_reason || '',
      sales_tax_id: selected.fields.sales_tax_id || '',
      weblink_email: selected.fields.weblink_email || '',
      statement_email: selected.fields.statement_email || '',
    })
    setAddressDraft({
      shipping: { ...emptyAddress(), ...(selected.fields.shipping_address || {}) },
      billing: { ...emptyAddress(), ...(selected.fields.billing_address || {}) },
    })
    setChoiceDraft({
      purchase_order_required: choiceFrom(selected.fields.purchase_order_required),
      previous_km_relationship: choiceFrom(selected.fields.previous_km_relationship),
      sales_tax_exempt: choiceFrom(selected.fields.sales_tax_exempt),
      weblink_signup: choiceFrom(selected.fields.weblink_signup),
      statement_email_signup: choiceFrom(selected.fields.statement_email_signup),
    })
    const nextSetup: Record<string, string> = {}
    for (const key of ['customer_number','route_code','price_code','terms_code','customer_class','customer_type','site','store_number','salesman_number','credit_limit','bill_to_customer']) {
      const value = selected.km_setup[key]
      nextSetup[key] = value == null ? '' : String(value)
    }
    setSetupDraft(nextSetup)
  }, [selected])

  async function upload(file: File | undefined) {
    if (!file) return
    try {
      setUploading(true)
      setMessage('')
      const created = await uploadPotentialCustomerApplication(file)
      setRecords((current) => [created, ...current.filter((row) => row.potential_customer_id !== created.potential_customer_id)])
      setSelectedId(created.potential_customer_id)
      setMessage('Application parsed and saved as a potential customer. Human review is still required.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to parse the uploaded application.')
    } finally {
      setUploading(false)
    }
  }

  async function saveReview(nextStatus: string) {
    if (!selected) return
    try {
      setSaving(true)
      const cleanedSetup = Object.fromEntries(
        Object.entries(setupDraft).filter(([, value]) => value.trim() !== ''),
      )
      const fieldUpdates: Record<string, unknown> = Object.fromEntries(
        Object.entries(fieldDraft).filter(([key, value]) => value !== String((selected.fields as unknown as Record<string, unknown>)[key] ?? '')),
      )
      if (JSON.stringify(addressDraft.shipping) !== JSON.stringify(selected.fields.shipping_address)) {
        fieldUpdates.shipping_address = addressDraft.shipping
      }
      if (JSON.stringify(addressDraft.billing) !== JSON.stringify(selected.fields.billing_address)) {
        fieldUpdates.billing_address = addressDraft.billing
      }
      for (const key of ['purchase_order_required', 'previous_km_relationship', 'sales_tax_exempt', 'weblink_signup', 'statement_email_signup']) {
        const nextValue = choiceTo(choiceDraft[key] ?? '')
        const currentValue = (selected.fields as unknown as Record<string, unknown>)[key]
        if (nextValue !== currentValue) fieldUpdates[key] = nextValue
      }
      const updated = await updatePotentialCustomerReview(selected.potential_customer_id, {
        status: nextStatus,
        km_setup: cleanedSetup,
        field_updates: fieldUpdates,
        review_notes: selected.review_notes || 'Potential New Customer review updated.',
      })
      setRecords((current) => current.map((row) => row.potential_customer_id === updated.potential_customer_id ? updated : row))
      setMessage(nextStatus === 'application_complete'
        ? 'Application marked complete. This does not create or update a MaddenCo customer.'
        : 'Potential customer review saved locally. MaddenCo remains read only.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to update the review state.')
    } finally {
      setSaving(false)
    }
  }


  const counters = useMemo(() => ({
    total: records.length,
    needsReview: records.filter((row) => row.status === 'needs_review').length,
    complete: records.filter((row) => row.status === 'application_complete').length,
    ready: records.filter((row) => row.status === 'ready_for_customer_setup').length,
  }), [records])

  return (
    <section className="potential-customers">
      <div className="potential-customers__heading">
        <div>
          <span className="credit-risk-kicker">R72 · CREDIT APPLICATION INTAKE</span>
          <h2>Potential New Customers</h2>
          <p>Parse the governed K&amp;M application, retain source evidence, and prepare MaddenCo customer-master fields without writing to ERP.</p>
        </div>
        <label className="credit-risk-primary-button potential-customers__upload">
          {uploading ? 'Parsing…' : 'Upload Credit Application'}
          <input
            type="file"
            accept="application/pdf,.pdf"
            disabled={uploading}
            onChange={(event) => { void upload(event.currentTarget.files?.[0]) }}
          />
        </label>
      </div>

      <div className="potential-customers__metrics">
        <div><span>Applications</span><strong>{counters.total}</strong></div>
        <div><span>Needs Review</span><strong>{counters.needsReview}</strong></div>
        <div><span>Application Complete</span><strong>{counters.complete}</strong></div>
        <div><span>Ready for Setup</span><strong>{counters.ready}</strong></div>
      </div>

      {message && <div className="credit-risk-message credit-risk-message--notice" role="status">{message}</div>}
      {status === 'loading' && <p>Loading potential customers…</p>}
      {status === 'error' && <div className="credit-risk-message credit-risk-message--error" role="alert">{message}</div>}

      {status === 'ready' && records.length === 0 && (
        <div className="potential-customers__empty">
          <h3>No potential customers yet</h3>
          <p>Upload the exact two-page K&amp;M Tire Credit Application to start the governed parser workflow.</p>
        </div>
      )}

      {records.length > 0 && (
        <div className="potential-customers__layout">
          <aside className="potential-customers__list" aria-label="Potential customers">
            {records.map((record) => (
              <button
                key={record.potential_customer_id}
                type="button"
                className={selectedId === record.potential_customer_id ? 'is-selected' : ''}
                onClick={() => setSelectedId(record.potential_customer_id)}
              >
                <strong>{record.fields.legal_business_name || 'Unnamed applicant'}</strong>
                <span>{record.potential_customer_id}</span>
                <small>{humanize(record.status)} · {date.format(new Date(record.received_at))}</small>
              </button>
            ))}
          </aside>

          {selected && (
            <div className="potential-customers__detail">
              <div className="potential-customers__detail-heading">
                <div>
                  <span className="credit-risk-kicker">{selected.potential_customer_id}</span>
                  <h3>{selected.fields.legal_business_name || 'Unnamed applicant'}</h3>
                  <p>{humanize(selected.status)} · Parser {selected.parser_version} · {(selected.classifier_confidence * 100).toFixed(0)}% classification confidence</p>
                </div>
                <div className="potential-customers__actions">
                  <a
                    className="credit-risk-secondary-button"
                    href={`${API_BASE}/credit-risk/potential-customers/${encodeURIComponent(selected.potential_customer_id)}/document`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open Original PDF
                  </a>
                  <button type="button" className="credit-risk-secondary-button" disabled={saving} onClick={() => { void saveReview(selected.status) }}>
                    Save Review
                  </button>
                  <button type="button" className="credit-risk-primary-button" disabled={saving || selected.status !== 'needs_review'} onClick={() => { void saveReview('application_complete') }}>
                    {saving ? 'Saving…' : 'Mark Application Complete'}
                  </button>
                </div>
              </div>

              <div className="potential-customers__cards">
                <section>
                  <h4>Application Data</h4>
                  <dl>
                    <div><dt>Legal Business Name</dt><dd><input value={fieldDraft.legal_business_name ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, legal_business_name: event.target.value }))} /><small>{humanize(selected.evidence.legal_business_name?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Trade Name (DBA)</dt><dd><input value={fieldDraft.trade_name ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, trade_name: event.target.value }))} /><small>{humanize(selected.evidence.trade_name?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Type of Business</dt><dd><input value={fieldDraft.type_of_business ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, type_of_business: event.target.value }))} /><small>{humanize(selected.evidence.type_of_business?.status || 'not_detected')} · MaddenCo code translation remains governed.</small></dd></div>
                    <div><dt>Shipping Address</dt><dd><div className="potential-customers__address-grid">{(['street','city','state','zip'] as const).map((key) => <label key={key}>{humanize(key)}<input value={addressDraft.shipping[key]} onChange={(event) => setAddressDraft((current) => ({ ...current, shipping: { ...current.shipping, [key]: event.target.value } }))} /></label>)}</div><small>{humanize(selected.evidence.shipping_address?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Billing Address</dt><dd><div className="potential-customers__address-grid">{(['street','city','state','zip'] as const).map((key) => <label key={key}>{humanize(key)}<input value={addressDraft.billing[key]} onChange={(event) => setAddressDraft((current) => ({ ...current, billing: { ...current.billing, [key]: event.target.value } }))} /></label>)}</div><small>{humanize(selected.evidence.billing_address?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Business Phone</dt><dd><input value={fieldDraft.business_phone ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, business_phone: event.target.value }))} /><small>{humanize(selected.evidence.business_phone?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Primary Language</dt><dd><input value={fieldDraft.primary_language ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, primary_language: event.target.value }))} /><small>{humanize(selected.evidence.primary_language?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Cell Phone</dt><dd><input value={fieldDraft.cell_phone ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, cell_phone: event.target.value }))} /><small>{humanize(selected.evidence.cell_phone?.status || 'not_detected')}</small></dd></div>
                    <div><dt>County</dt><dd><input value={fieldDraft.county ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, county: event.target.value }))} /><small>{humanize(selected.evidence.county?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Email Address</dt><dd><input value={fieldDraft.email_address ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, email_address: event.target.value }))} /><small>{humanize(selected.evidence.email_address?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Federal Tax ID</dt><dd><input value={fieldDraft.federal_tax_id ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, federal_tax_id: event.target.value }))} /><small>{humanize(selected.evidence.federal_tax_id?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Manager's Name</dt><dd><input value={fieldDraft.manager_name ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, manager_name: event.target.value }))} /><small>{humanize(selected.evidence.manager_name?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Year Started Business</dt><dd><input value={fieldDraft.year_started_business ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, year_started_business: event.target.value }))} /><small>{humanize(selected.evidence.year_started_business?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Accounts Payable Contact</dt><dd><input value={fieldDraft.accounts_payable_contact ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, accounts_payable_contact: event.target.value }))} /><small>{humanize(selected.evidence.accounts_payable_contact?.status || 'not_detected')}</small></dd></div>
                    <div><dt>PO Required</dt><dd><select value={choiceDraft.purchase_order_required ?? ''} onChange={(event) => setChoiceDraft((current) => ({ ...current, purchase_order_required: event.target.value as ChoiceDraft }))}><option value="">Blank / not selected</option><option value="yes">Yes</option><option value="no">No</option></select><small>{humanize(selected.evidence.purchase_order_required?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Prior K&amp;M Relationship</dt><dd><select value={choiceDraft.previous_km_relationship ?? ''} onChange={(event) => setChoiceDraft((current) => ({ ...current, previous_km_relationship: event.target.value as ChoiceDraft }))}><option value="">Blank / not selected</option><option value="yes">Yes</option><option value="no">No</option></select><input placeholder="If yes, prior name / timing" value={fieldDraft.previous_business_name ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, previous_business_name: event.target.value }))} /><small>{humanize(selected.evidence.previous_km_relationship?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Sales Tax Exempt</dt><dd><select value={choiceDraft.sales_tax_exempt ?? ''} onChange={(event) => setChoiceDraft((current) => ({ ...current, sales_tax_exempt: event.target.value as ChoiceDraft }))}><option value="">Blank / not selected</option><option value="yes">Yes</option><option value="no">No</option></select><small>{humanize(selected.evidence.sales_tax_exempt?.status || 'not_detected')} · Blank is never treated as No.</small></dd></div>
                    <div><dt>Exemption Reason</dt><dd><input value={fieldDraft.sales_tax_exemption_reason ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, sales_tax_exemption_reason: event.target.value }))} /><small>{humanize(selected.evidence.sales_tax_exemption_reason?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Sales Tax ID</dt><dd><input value={fieldDraft.sales_tax_id ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, sales_tax_id: event.target.value }))} /><small>{humanize(selected.evidence.sales_tax_id?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Weblink Signup</dt><dd><select value={choiceDraft.weblink_signup ?? ''} onChange={(event) => setChoiceDraft((current) => ({ ...current, weblink_signup: event.target.value as ChoiceDraft }))}><option value="">Blank / not selected</option><option value="yes">Yes</option><option value="no">No</option></select><input placeholder="Weblink email" value={fieldDraft.weblink_email ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, weblink_email: event.target.value }))} /><small>{humanize(selected.evidence.weblink_signup?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Statement Email Signup</dt><dd><select value={choiceDraft.statement_email_signup ?? ''} onChange={(event) => setChoiceDraft((current) => ({ ...current, statement_email_signup: event.target.value as ChoiceDraft }))}><option value="">Blank / not selected</option><option value="yes">Yes</option><option value="no">No</option></select><input placeholder="Statement email" value={fieldDraft.statement_email ?? ''} onChange={(event) => setFieldDraft((current) => ({ ...current, statement_email: event.target.value }))} /><small>{humanize(selected.evidence.statement_email_signup?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Locations</dt><dd>{selected.fields.number_of_locations == null ? 'Blank / not parsed' : selected.fields.number_of_locations}<small>{humanize(selected.evidence.number_of_locations?.status || 'not_detected')}</small></dd></div>
                    <div><dt>Annual Purchases</dt><dd>{selected.fields.estimated_annual_purchases == null ? 'Blank / not parsed' : money.format(selected.fields.estimated_annual_purchases)}<small>{humanize(selected.evidence.estimated_annual_purchases?.status || 'not_detected')}</small></dd></div>
                  </dl>
                </section>

                <section>
                  <h4>MaddenCo Setup Readiness</h4>
                  <p><strong>{selected.madden_setup.ready_count}</strong> of <strong>{selected.madden_setup.total_count}</strong> mapped setup fields currently ready.</p>
                  <div className="potential-customers__setup-grid">
                    {[
                      ['customer_number','Customer #'],['route_code','Route'],['price_code','Price Code'],['terms_code','Terms'],
                      ['customer_class','Class'],['customer_type','Customer Type'],['site','Site'],['store_number','Store'],
                      ['salesman_number','Salesman'],['credit_limit','Credit Limit'],['bill_to_customer','Bill-To Customer'],
                    ].map(([key, label]) => (
                      <label key={key}>{label}<input value={setupDraft[key] ?? ''} onChange={(event) => setSetupDraft((current) => ({ ...current, [key]: event.target.value }))} /></label>
                    ))}
                  </div>
                  <div className="potential-customers__mapping">
                    {selected.tmcust_mapping.filter((item) => item.status !== 'ready').slice(0, 9).map((item) => (
                      <div key={item.field}>
                        <span>{humanize(item.field)}</span>
                        <code>{item.tmcust_column}</code>
                        <small>{humanize(item.status)}</small>
                      </div>
                    ))}
                  </div>
                </section>
              </div>

              <section className="potential-customers__matches">
                <h4>Possible Existing MaddenCo Customers</h4>
                {selected.existing_customer_matches.length === 0 ? (
                  <p>No deterministic TMCUST candidate was returned. This is not proof that the applicant is new.</p>
                ) : selected.existing_customer_matches.map((match) => (
                  <div key={match.customer_number}>
                    <strong>{match.customer_name} · {match.customer_number}</strong>
                    <span>{match.matched_factors.map(humanize).join(', ')}</span>
                    <small>{Math.round(match.confidence * 100)}% evidence confidence · Human decision required</small>
                  </div>
                ))}
              </section>

              <div className="potential-customers__governance">
                ERP read only · No automatic customer creation · Human review required · Source SHA-256 {selected.source_sha256.slice(0, 12)}…
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
