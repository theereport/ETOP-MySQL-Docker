import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createAPControlCase,
  createAPControlReview,
  getAPControlCase,
  getAPControlCases,
  getAccountsPayableInvoices,
} from './api'
import { GovernanceBoundary, Message, SourceCoverage, StatusTag } from './components'
import { errorMessage, formatCurrency, formatDateTime, titleCase } from './format'
import type {
  APControlCaseDetail,
  APControlCaseSummary,
  APInvoiceSummary,
} from './types'

type Action = 'approval_review' | 'payment_preparation'
type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

export default function APControlCenter({ mode }: { mode: Action }) {
  const [cases, setCases] = useState<APControlCaseSummary[]>([])
  const [listStatus, setListStatus] = useState<AsyncStatus>('loading')
  const [listError, setListError] = useState('')
  const [selectedCase, setSelectedCase] = useState<APControlCaseDetail | null>(null)
  const [search, setSearch] = useState('')
  const [searchStatus, setSearchStatus] = useState<AsyncStatus>('idle')
  const [searchError, setSearchError] = useState('')
  const [invoiceResults, setInvoiceResults] = useState<APInvoiceSummary[]>([])
  const [selectedInvoice, setSelectedInvoice] = useState<APInvoiceSummary | null>(null)
  const [requestedBy, setRequestedBy] = useState('')
  const [assignedReviewer, setAssignedReviewer] = useState('')
  const [paymentPreparer, setPaymentPreparer] = useState('')
  const [caseNotes, setCaseNotes] = useState('')
  const [caseStatus, setCaseStatus] = useState<AsyncStatus>('idle')
  const [caseMessage, setCaseMessage] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [disposition, setDisposition] = useState<'evidence_ready' | 'needs_information' | 'duplicate_review_required' | 'not_ready'>('needs_information')
  const [reviewNotes, setReviewNotes] = useState('')
  const [reviewStatus, setReviewStatus] = useState<AsyncStatus>('idle')
  const [reviewMessage, setReviewMessage] = useState('')

  const title = mode === 'approval_review' ? 'Approval readiness center' : 'Payment-control readiness'
  const loadCases = useCallback(async (signal?: AbortSignal) => {
    setListStatus('loading')
    setListError('')
    try {
      const response = await getAPControlCases(mode, signal)
      setCases(response.items)
      setListStatus('success')
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setListStatus('error')
      setListError(errorMessage(error, 'Unable to load AP control cases.'))
    }
  }, [mode])

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      void loadCases(controller.signal)
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [loadCases])

  async function findInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!search.trim()) {
      setSearchStatus('error')
      setSearchError('Enter an invoice, vendor, PO, document job ID, or filename.')
      return
    }
    setSearchStatus('loading')
    setSearchError('')
    try {
      const response = await getAccountsPayableInvoices({ query: search.trim(), limit: 20, offset: 0 })
      setInvoiceResults(response.items)
      setSelectedInvoice(null)
      setSearchStatus('success')
    } catch (error) {
      setSearchStatus('error')
      setSearchError(errorMessage(error, 'Unable to search imported invoice evidence.'))
    }
  }

  async function createCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedInvoice || !requestedBy.trim() || !assignedReviewer.trim() || !caseNotes.trim()) {
      setCaseStatus('error')
      setCaseMessage('Select an invoice and enter the requester, assigned reviewer, and case notes.')
      return
    }
    if (mode === 'payment_preparation' && !paymentPreparer.trim()) {
      setCaseStatus('error')
      setCaseMessage('Payment-control cases require an operator-supplied payment preparer.')
      return
    }
    setCaseStatus('loading')
    setCaseMessage('')
    try {
      const created = await createAPControlCase(selectedInvoice.ap_invoice_id, {
        intended_action: mode,
        requested_by: requestedBy.trim(),
        assigned_reviewer: assignedReviewer.trim(),
        payment_preparer: mode === 'payment_preparation' ? paymentPreparer.trim() : null,
        notes: caseNotes.trim(),
      })
      setSelectedCase(created)
      setReviewer(created.assigned_reviewer)
      setSelectedInvoice(null)
      setInvoiceResults([])
      setSearch('')
      setRequestedBy('')
      setAssignedReviewer('')
      setPaymentPreparer('')
      setCaseNotes('')
      setCaseStatus('success')
      setCaseMessage('Control case created from an immutable invoice evidence snapshot. No approval or payment action occurred.')
      await loadCases()
    } catch (error) {
      setCaseStatus('error')
      setCaseMessage(errorMessage(error, 'Unable to create the AP control case.'))
    }
  }

  async function openCase(controlCaseId: string) {
    setReviewMessage('')
    try {
      const detail = await getAPControlCase(controlCaseId)
      setSelectedCase(detail)
      setReviewer(detail.assigned_reviewer)
    } catch (error) {
      setListStatus('error')
      setListError(errorMessage(error, 'Unable to open the control case.'))
    }
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedCase || !reviewer.trim() || !reviewNotes.trim()) {
      setReviewStatus('error')
      setReviewMessage('Enter the assigned reviewer identity, a disposition, and review notes.')
      return
    }
    setReviewStatus('loading')
    setReviewMessage('')
    try {
      const updated = await createAPControlReview(selectedCase.control_case_id, {
        reviewer_identity: reviewer.trim(),
        disposition,
        notes: reviewNotes.trim(),
      })
      setSelectedCase(updated)
      setReviewNotes('')
      setReviewStatus('success')
      setReviewMessage('Append-only readiness disposition saved. It did not approve the invoice or authorize payment.')
      await loadCases()
    } catch (error) {
      setReviewStatus('error')
      setReviewMessage(errorMessage(error, 'Unable to record the readiness disposition.'))
    }
  }

  const blockers = useMemo(() => {
    if (!selectedCase) return 0
    return selectedCase.evidence_gates.filter((gate) => gate.status === 'blocked').length
      + selectedCase.segregation_checks.filter((check) => check.status === 'blocked').length
  }, [selectedCase])

  return (
    <div className="ap-control-workspace">
      <section className="ap-panel ap-control-boundary">
        <div className="ap-panel-heading"><div><span className="ap-kicker">Governed readiness, not authorization</span><h2>{title}</h2></div><StatusTag status="no execution authority" /></div>
        <p>Build an immutable evidence packet, check available document controls and operator-supplied role separation, then record a professional readiness disposition. Authentication, approval tiers, ERP payable status, vendor authority, payment rails, posting, and execution remain unavailable.</p>
      </section>

      <div className="ap-control-columns">
        <section className="ap-panel ap-control-create">
          <div className="ap-panel-heading"><div><span className="ap-kicker">Start from real evidence</span><h2>Create control case</h2></div></div>
          <form className="ap-control-search" onSubmit={findInvoice}>
            <label><span>Find imported invoice evidence</span><div><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Invoice, vendor, PO, job ID, or filename" /><button className="ap-secondary-button" type="submit" disabled={searchStatus === 'loading'}>{searchStatus === 'loading' ? 'Searching…' : 'Find invoice'}</button></div></label>
          </form>
          {searchError && <Message kind="error">{searchError}</Message>}
          {searchStatus === 'success' && invoiceResults.length === 0 && <p className="ap-empty-inline">No imported invoice evidence matched. No placeholder case can be created.</p>}
          {invoiceResults.length > 0 && (
            <div className="ap-control-invoice-results">
              {invoiceResults.map((invoice) => (
                <button type="button" key={invoice.ap_invoice_id} className={selectedInvoice?.ap_invoice_id === invoice.ap_invoice_id ? 'is-selected' : ''} onClick={() => setSelectedInvoice(invoice)}>
                  <strong>{invoice.invoice_number || 'Invoice number unavailable'}</strong>
                  <span>{invoice.vendor_name || invoice.vendor_number || 'Vendor unavailable'} · {formatCurrency(invoice.total_amount)}</span>
                  <small>{invoice.source_file_name}</small>
                </button>
              ))}
            </div>
          )}
          <form className="ap-control-form" onSubmit={createCase}>
            <p className="ap-control-selected"><strong>Selected invoice</strong><span>{selectedInvoice ? `${selectedInvoice.invoice_number || selectedInvoice.ap_invoice_id} · ${selectedInvoice.vendor_name || 'Vendor unavailable'}` : 'None selected'}</span></p>
            <div className="ap-control-form-grid">
              <label><span>Requested by</span><input value={requestedBy} onChange={(event) => setRequestedBy(event.target.value)} maxLength={200} /></label>
              <label><span>Assigned reviewer</span><input value={assignedReviewer} onChange={(event) => setAssignedReviewer(event.target.value)} maxLength={200} /></label>
              {mode === 'payment_preparation' && <label><span>Payment preparer</span><input value={paymentPreparer} onChange={(event) => setPaymentPreparer(event.target.value)} maxLength={200} /></label>}
            </div>
            <label><span>Case notes</span><textarea rows={4} value={caseNotes} onChange={(event) => setCaseNotes(event.target.value)} maxLength={5000} /></label>
            {caseMessage && <Message kind={caseStatus === 'error' ? 'error' : 'success'}>{caseMessage}</Message>}
            <button className="ap-primary-button" type="submit" disabled={caseStatus === 'loading'}>{caseStatus === 'loading' ? 'Creating case…' : 'Create immutable control case'}</button>
          </form>
        </section>

        <section className="ap-panel ap-control-list">
          <div className="ap-panel-heading"><div><span className="ap-kicker">Append-only local cases</span><h2>{mode === 'approval_review' ? 'Approval-readiness cases' : 'Payment-readiness cases'}</h2></div><span className="ap-count">{cases.length}</span></div>
          {listStatus === 'loading' && <p className="ap-empty-inline">Loading control cases…</p>}
          {listError && <Message kind="error">{listError}</Message>}
          {listStatus === 'success' && cases.length === 0 && <p className="ap-empty-inline">No control cases have been created for this view.</p>}
          <div className="ap-control-case-list">
            {cases.map((item) => (
              <button type="button" key={item.control_case_id} className={selectedCase?.control_case_id === item.control_case_id ? 'is-selected' : ''} onClick={() => void openCase(item.control_case_id)}>
                <div><strong>{item.invoice.invoice_number || item.ap_invoice_id}</strong><StatusTag status={item.control_status} /></div>
                <span>{item.invoice.vendor_name || item.invoice.vendor_number || 'Vendor unavailable'} · {formatCurrency(item.invoice.total_amount)}</span>
                <small>Reviewer {item.assigned_reviewer} · {formatDateTime(item.created_at)}</small>
              </button>
            ))}
          </div>
        </section>
      </div>

      {selectedCase && (
        <section className="ap-panel ap-control-detail">
          <div className="ap-panel-heading"><div><span className="ap-kicker">Immutable case {selectedCase.control_case_id}</span><h2>{selectedCase.invoice.invoice_number || selectedCase.ap_invoice_id}</h2></div><StatusTag status={selectedCase.control_status} /></div>
          <div className="ap-control-summary">
            <div><span>Evidence current</span><strong>{selectedCase.evidence_current ? 'Yes' : 'No'}</strong></div>
            <div><span>Document evidence ready</span><strong>{selectedCase.document_evidence_ready ? 'Yes' : 'No'}</strong></div>
            <div><span>Blocked controls</span><strong>{blockers}</strong></div>
            <div><span>Approval authority</span><strong>{titleCase(selectedCase.approval_authority_status)}</strong></div>
            <div><span>Payment authorization</span><strong>{titleCase(selectedCase.payment_authorization_status)}</strong></div>
          </div>
          <div className="ap-control-check-columns">
            <div><h3>Evidence gates</h3>{selectedCase.evidence_gates.map((gate) => <article key={gate.code}><div><strong>{gate.label}</strong><StatusTag status={gate.status} /></div><p>{gate.explanation}</p><small>{gate.source || 'No governed source connected'}</small></article>)}</div>
            <div><h3>Segregation checks</h3>{selectedCase.segregation_checks.map((check) => <article key={check.code}><div><strong>{check.label}</strong><StatusTag status={check.status} /></div><p>{check.explanation}</p><small>{check.identities.join(' / ')}</small></article>)}</div>
          </div>
          <form className="ap-control-review-form" onSubmit={submitReview}>
            <div className="ap-panel-heading"><div><span className="ap-kicker">Professional disposition</span><h2>Record readiness review</h2></div></div>
            <div className="ap-control-form-grid">
              <label><span>Reviewer identity</span><input value={reviewer} onChange={(event) => setReviewer(event.target.value)} maxLength={200} /></label>
              <label><span>Disposition</span><select value={disposition} onChange={(event) => setDisposition(event.target.value as typeof disposition)}><option value="evidence_ready">Evidence ready</option><option value="needs_information">Needs information</option><option value="duplicate_review_required">Duplicate review required</option><option value="not_ready">Not ready</option></select></label>
            </div>
            <label><span>Review notes</span><textarea rows={4} value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} maxLength={5000} /></label>
            {reviewMessage && <Message kind={reviewStatus === 'error' ? 'error' : 'success'}>{reviewMessage}</Message>}
            <div className="ap-control-execution-warning"><strong>No execution effect</strong><p>Evidence ready is not invoice approval. This record cannot enter a governed approval tier, authorize payment, release funds, post to ERP, or verify the operator's authority.</p></div>
            <button className="ap-primary-button" type="submit" disabled={reviewStatus === 'loading'}>{reviewStatus === 'loading' ? 'Saving disposition…' : 'Save append-only disposition'}</button>
          </form>
          {selectedCase.reviews.length > 0 && <div className="ap-control-review-history"><h3>Review history</h3>{selectedCase.reviews.map((review) => <article key={review.review_id}><div><strong>{titleCase(review.disposition)}</strong><span>{review.reviewer_identity} · {formatDateTime(review.created_at)}</span></div><p>{review.notes}</p><small>Approval effect {review.approval_effect}; payment effect {review.payment_effect}; authority {titleCase(review.actor_authority_status)}</small></article>)}</div>}
          {selectedCase.warnings.length > 0 && <Message kind="notice"><ul>{selectedCase.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></Message>}
          <div className="ap-two-column"><SourceCoverage items={selectedCase.source_coverage} /><GovernanceBoundary governance={selectedCase.governance} /></div>
          <p className="ap-control-hash">Source evidence SHA-256 <code>{selectedCase.source_evidence_sha256}</code> · Case evidence SHA-256 <code>{selectedCase.evidence_snapshot_sha256}</code></p>
        </section>
      )}
    </div>
  )
}
