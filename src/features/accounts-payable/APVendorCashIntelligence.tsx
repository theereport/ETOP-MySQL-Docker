import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import APVendorTermsReference from './APVendorTermsReference'
import {
  createAPCashScenario,
  getAPCashScenarios,
  getAPVendorCashIntelligence,
} from './api'
import { errorMessage, formatDateTime } from './format'
import type {
  APCashScenarioHistoryResponse,
  APVendorCashIntelligenceResponse,
  APVendorInsight,
  CreateAPCashScenarioRequest,
} from './types'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function todayInput(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

export default function APVendorCashIntelligence({
  mode,
  refreshKey,
}: {
  mode: 'vendor' | 'cash'
  refreshKey: number
}) {
  const [asOfDate, setAsOfDate] = useState(todayInput)
  const [data, setData] = useState<APVendorCashIntelligenceResponse | null>(null)
  const [history, setHistory] = useState<APCashScenarioHistoryResponse | null>(null)
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [error, setError] = useState('')
  const [vendorQuery, setVendorQuery] = useState('')
  const [horizon, setHorizon] = useState<7 | 14 | 30 | 60 | 90>(30)
  const [includeReview, setIncludeReview] = useState(false)
  const [preparedBy, setPreparedBy] = useState('')
  const [rationale, setRationale] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const requests = [getAPVendorCashIntelligence(asOfDate, controller.signal)] as const
    void Promise.all([
      ...requests,
      mode === 'cash' ? getAPCashScenarios(controller.signal) : Promise.resolve(null),
    ])
      .then(([intelligence, scenarioHistory]) => {
        setData(intelligence)
        setHistory(scenarioHistory)
        setStatus('success')
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return
        setStatus('error')
        setError(errorMessage(loadError, 'Unable to load AP vendor and cash evidence.'))
      })
    return () => controller.abort()
  }, [asOfDate, mode, refreshKey])

  const vendors = useMemo(() => {
    const query = vendorQuery.trim().toLocaleLowerCase()
    if (!query) return data?.vendors ?? []
    return (data?.vendors ?? []).filter((vendor) => (
      [vendor.vendor_number, vendor.vendor_name]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(query))
    ))
  }, [data, vendorQuery])

  async function submitScenario(event: FormEvent) {
    event.preventDefault()
    if (!preparedBy.trim() || !rationale.trim()) {
      setSaveStatus('error')
      setSaveMessage('Prepared by and rationale are required.')
      return
    }
    setSaveStatus('saving')
    setSaveMessage('')
    const request: CreateAPCashScenarioRequest = {
      as_of_date: asOfDate,
      horizon_days: horizon,
      include_review_required: includeReview,
      prepared_by: preparedBy.trim(),
      rationale: rationale.trim(),
    }
    try {
      const saved = await createAPCashScenario(request)
      const nextHistory = await getAPCashScenarios()
      setHistory(nextHistory)
      setRationale('')
      setSaveStatus('success')
      setSaveMessage(
        `Scenario saved: ${saved.included_invoice_count} document invoice(s), ${money.format(saved.extracted_amount)} in known extracted totals. No payment proposal or authorization was created.`,
      )
    } catch (saveError) {
      setSaveStatus('error')
      setSaveMessage(errorMessage(saveError, 'Unable to save the cash scenario.'))
    }
  }

  if (status === 'loading' && !data) {
    return <div className="ap-loading"><span className="ap-spinner" /><div><strong>Building AP evidence analytics</strong><p>Aggregating imported invoice evidence without assuming ERP payable status…</p></div></div>
  }
  if (status === 'error' && !data) {
    return <div className="ap-message ap-message--error"><strong>Vendor and cash evidence is unavailable.</strong><span>{error}</span></div>
  }
  if (!data) return null

  return (
    <section className="ap-vendor-cash">
      <div className="ap-vendor-cash-coverage">
        <article><span>Imported invoices</span><strong>{data.coverage.imported_invoice_count}</strong></article>
        <article><span>Vendor identified</span><strong>{data.coverage.identified_vendor_invoice_count}</strong></article>
        <article><span>Due date available</span><strong>{data.coverage.due_date_invoice_count}</strong></article>
        <article><span>Known totals</span><strong>{data.coverage.known_amount_invoice_count}</strong></article>
        <article><span>Review required</span><strong>{data.coverage.review_required_invoice_count}</strong></article>
      </div>

      <div className="ap-evidence-boundary">
        <strong>Document-evidence analytics · not an ERP payable forecast</strong>
        <p>Paid, voided, disputed, credited, or otherwise closed status is unavailable. Amounts below may include invoices that are no longer payable.</p>
      </div>

      {mode === 'vendor' ? (
        <>
          <div className="ap-vendor-toolbar">
            <div><span className="ap-kicker">Imported document evidence</span><h3>Vendor Intelligence</h3><p>No composite score is assigned.</p></div>
            <label>Filter vendors<input type="search" value={vendorQuery} onChange={(event) => setVendorQuery(event.target.value)} placeholder="Vendor name or number" /></label>
          </div>
          {vendors.length === 0 ? <div className="ap-empty-state"><strong>No vendor evidence matched.</strong><p>ETOP did not create placeholder vendor records.</p></div> : (
            <div className="ap-vendor-table-wrap">
              <table className="ap-vendor-table">
                <thead><tr><th>Vendor evidence</th><th>Invoices</th><th>Extracted total</th><th>Due dates</th><th>Review</th><th>Exceptions</th><th>Duplicates</th><th>OCR avg.</th></tr></thead>
                <tbody>{vendors.map((vendor: APVendorInsight) => (
                  <tr key={vendor.vendor_key}>
                    <td><strong>{vendor.vendor_name || 'Unidentified vendor'}</strong><small>{vendor.vendor_number || vendor.identity_basis.replaceAll('_', ' ')}</small>{vendor.evidence_alerts.map((alert) => <em key={alert}>{alert}</em>)}</td>
                    <td>{vendor.invoice_count}</td>
                    <td>{money.format(vendor.extracted_total_amount)}<small>{vendor.known_total_count}/{vendor.invoice_count} known</small></td>
                    <td>{vendor.due_date_count}/{vendor.invoice_count}</td>
                    <td>{vendor.review_required_count}</td>
                    <td>{vendor.exception_invoice_count}</td>
                    <td>{vendor.duplicate_candidate_invoice_count}</td>
                    <td>{vendor.ocr_average_confidence == null ? 'Unavailable' : `${(vendor.ocr_average_confidence * 100).toFixed(1)}%`}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <APVendorTermsReference />
        </>
      ) : (
        <>
          <div className="ap-cash-toolbar">
            <div><span className="ap-kicker">Saved invoice due dates</span><h3>Cash Planning Evidence</h3><p>Choose an as-of date to reclassify document due windows.</p></div>
            <label>As-of date<input type="date" value={asOfDate} onChange={(event) => setAsOfDate(event.target.value)} /></label>
          </div>
          <div className="ap-cash-windows">
            {data.cash_windows.map((window) => (
              <article key={window.code}>
                <span>{window.label}</span><strong>{money.format(window.extracted_amount)}</strong><small>{window.invoice_count} invoice{window.invoice_count === 1 ? '' : 's'} · {window.known_amount_count} known amount{window.known_amount_count === 1 ? '' : 's'}</small><p>{window.explanation}</p>
              </article>
            ))}
          </div>
          <div className="ap-cash-scenario-grid">
            <form className="ap-cash-scenario-form" onSubmit={submitScenario}>
              <span className="ap-kicker">Append-only analysis</span><h3>Save a cash evidence scenario</h3>
              <label>Horizon<select value={horizon} onChange={(event) => setHorizon(Number(event.target.value) as 7 | 14 | 30 | 60 | 90)}><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option><option value={60}>60 days</option><option value={90}>90 days</option></select></label>
              <label className="ap-checkbox"><input type="checkbox" checked={includeReview} onChange={(event) => setIncludeReview(event.target.checked)} /><span>Include invoices that currently require document/duplicate review</span></label>
              <label>Prepared by<input value={preparedBy} onChange={(event) => setPreparedBy(event.target.value)} placeholder="Person preparing this analysis" /></label>
              <label>Rationale<textarea rows={4} value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Purpose, assumptions, and intended discussion" /></label>
              <p className="ap-control-boundary">Analytical scenario only · current payable status unknown · no approval, payment batch, authorization, posting, or ERP write</p>
              <button className="ap-primary-button" type="submit" disabled={saveStatus === 'saving'}>{saveStatus === 'saving' ? 'Saving…' : 'Save cash evidence scenario'}</button>
              {saveMessage && <p className={saveStatus === 'error' ? 'ap-form-error' : 'ap-form-success'}>{saveMessage}</p>}
            </form>
            <div className="ap-cash-history">
              <span className="ap-kicker">Immutable history</span><h3>Saved scenarios</h3>
              {!history?.scenarios.length ? <p>No cash evidence scenarios have been recorded.</p> : history.scenarios.map((scenario) => (
                <article key={scenario.cash_scenario_id}>
                  <div><strong>{scenario.horizon_days}-day scenario</strong><small>{formatDateTime(scenario.created_at)}</small></div>
                  <strong>{money.format(scenario.extracted_amount)}</strong>
                  <span>{scenario.included_invoice_count} invoice{scenario.included_invoice_count === 1 ? '' : 's'} · through {scenario.horizon_end_date}</span>
                  <p>{scenario.rationale}</p>
                  <small>Evidence SHA-256 {scenario.evidence_snapshot_sha256}</small>
                </article>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="ap-two-column">
        <div className="ap-evidence-boundary"><strong>Source limits</strong>{data.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>
        <div className="ap-evidence-boundary"><strong>Authority limits</strong>{data.governance.statements.map((statement) => <p key={statement}>{statement}</p>)}</div>
      </div>
    </section>
  )
}
