import { useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  formatCents,
  formatCount,
  formatDate,
  formatDateTime,
  readableStatus,
  shortHash,
} from './format'
import type {
  BankItem,
  DepositSummary,
  MatchClassification,
  PaymentNoteCandidate,
  PaymentNotesERPProvenance,
  PaymentNotesRunSummary,
  ReviewDecision,
  RouteReferenceStatus,
  RouteReferenceSummary,
} from './types'

export type QueueView = 'all' | 'matched' | 'review' | 'unmatched'

const matchedStates = new Set<MatchClassification>([
  'AUTO_MATCHED',
  'LOCAL_REVIEW_ACCEPTED_MATCH',
])

const reviewStates = new Set<MatchClassification>([
  'CHECK_MATCH_AMOUNT_MISMATCH',
  'SUGGESTED_REVIEW',
  'AMBIGUOUS_MATCH',
])

const unmatchedStates = new Set<MatchClassification>([
  'NO_MATCH',
  'LOCALLY_RECORDED_UNMATCHED',
])

function itemsForQueue(items: BankItem[], queue: QueueView): BankItem[] {
  if (queue === 'matched') return items.filter((item) => matchedStates.has(item.classification))
  if (queue === 'review') return items.filter((item) => reviewStates.has(item.classification))
  if (queue === 'unmatched') return items.filter((item) => unmatchedStates.has(item.classification))
  return items
}

function toneForStatus(status: string): 'good' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (['READY', 'ACTIVE', 'ARITHMETICALLY_BALANCED', 'LOCAL_REVIEW_COMPLETE', 'AUTO_MATCHED', 'LOCAL_REVIEW_ACCEPTED_MATCH', 'SIGNED_EVIDENCE', 'SOURCE_COMPLETE'].includes(status)) return 'good'
  if (['BALANCE_FAILED', 'NO_MATCH', 'CHECK_MATCH_AMOUNT_MISMATCH'].includes(status)) return 'danger'
  if (['NOT_READY', 'REVIEW_REQUIRED', 'SUGGESTED_REVIEW', 'AMBIGUOUS_MATCH', 'SIGNATURE_UNDETERMINED', 'SOURCE_INCOMPLETE'].includes(status)) return 'warning'
  if (['LOCALLY_RECORDED_UNMATCHED', 'SIGNATURE_ROW_NO_FILE'].includes(status)) return 'info'
  return 'neutral'
}

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={`pn-status pn-status--${toneForStatus(status)}`}>
      {readableStatus(status)}
    </span>
  )
}

export function Message({
  kind,
  children,
}: {
  kind: 'error' | 'success' | 'notice'
  children: ReactNode
}) {
  return <div className={`pn-message pn-message--${kind}`}>{children}</div>
}

export function EmptyState({
  title,
  detail,
}: {
  title: string
  detail: string
}) {
  return (
    <div className="pn-empty-state">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  )
}

export function RouteReferencePanel({
  status,
  references,
  busy,
  onUpload,
  onActivate,
}: {
  status: RouteReferenceStatus | null
  references: RouteReferenceSummary[]
  busy: boolean
  onUpload: (file: File, versionLabel: string) => Promise<void>
  onActivate: (referenceId: string) => Promise<void>
}) {
  const [file, setFile] = useState<File | null>(null)
  const [versionLabel, setVersionLabel] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const normalizedVersion = versionLabel.trim()
    if (!file || !normalizedVersion) return
    await onUpload(file, normalizedVersion)
    setFile(null)
    setVersionLabel('')
    form.reset()
  }

  return (
    <section className="pn-panel pn-route-panel" aria-labelledby="pn-route-title">
      <div className="pn-panel-heading">
        <div>
          <span>Route scope control</span>
          <h2 id="pn-route-title">Route reference</h2>
          <p>Bank locations can reconcile only through an active, versioned location-to-route reference.</p>
        </div>
        <StatusPill status={status?.ready ? 'READY' : 'NOT_READY'} />
      </div>

      {status?.active_reference ? (
        <div className="pn-reference-current">
          <div>
            <span>Active reference</span>
            <strong>{status.active_reference.source_file_name}</strong>
            <small>
              Version {status.active_reference.version_label} · {shortHash(status.active_reference.source_sha256)} · activated {formatDateTime(status.active_reference.activated_at)}
            </small>
          </div>
          <div className="pn-reference-quality" aria-label="Route-reference quality">
            <span><strong>{formatCount(status.active_reference.quality.unique_mapping_count)}</strong> mappings</span>
            <span><strong>{formatCount(status.active_reference.quality.conflicting_route_count)}</strong> conflicts</span>
            <span><strong>{formatCount(status.active_reference.quality.warnings.length)}</strong> warnings</span>
          </div>
        </div>
      ) : (
        <EmptyState
          title="No active route reference"
          detail="Upload a controlled CSV or Excel lookup, inspect its quality result, then explicitly activate the intended version."
        />
      )}

      {(status?.blocking_reasons.length ?? 0) > 0 && (
        <Message kind="notice">
          <strong>Route matching is blocked</strong>
          <ul>{status?.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </Message>
      )}

      <form className="pn-inline-form" onSubmit={(event) => void submit(event)}>
        <label>
          <span>Route-reference file</span>
          <input
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            disabled={busy}
          />
        </label>
        <label>
          <span>Version label</span>
          <input
            type="text"
            value={versionLabel}
            maxLength={120}
            placeholder="e.g. 2026-08 controlled routes"
            onChange={(event) => setVersionLabel(event.target.value)}
            disabled={busy}
          />
        </label>
        <button type="submit" disabled={!file || !versionLabel.trim() || busy}>
          {busy ? 'Uploading…' : 'Upload reference'}
        </button>
      </form>

      {references.length > 0 && (
        <div className="pn-reference-list">
          <div className="pn-reference-row pn-reference-row--header" aria-hidden="true">
            <span>Reference</span><span>Quality</span><span>State</span><span>Action</span>
          </div>
          {references.map((reference) => {
            const active = status?.active_reference?.reference_id === reference.reference_id
            return (
              <div className="pn-reference-row" key={reference.reference_id}>
                <span>
                  <strong>{reference.source_file_name}</strong>
                  <small>{reference.version_label} · {formatDateTime(reference.created_at)}</small>
                </span>
                <span>
                  <strong>{reference.quality.unique_mapping_count} mappings</strong>
                  <small>{reference.quality.conflicting_route_count} conflicts · {reference.quality.warnings.length} warnings</small>
                </span>
                <span><StatusPill status={active ? 'ACTIVE' : reference.state} /></span>
                <span>
                  {active ? (
                    <small>Current reference</small>
                  ) : (
                    <button
                      type="button"
                      className="pn-button pn-button--secondary"
                      disabled={busy || reference.state === 'invalid'}
                      onClick={() => void onActivate(reference.reference_id)}
                    >
                      Activate
                    </button>
                  )}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

export function RunHistory({
  runs,
  selectedRunId,
  busy,
  onOpen,
}: {
  runs: PaymentNotesRunSummary[]
  selectedRunId: string | null
  busy: boolean
  onOpen: (runId: string) => void
}) {
  return (
    <section className="pn-panel pn-history" aria-labelledby="pn-history-title">
      <div className="pn-panel-heading pn-panel-heading--compact">
        <div>
          <span>Durable evidence</span>
          <h2 id="pn-history-title">Reconciliation history</h2>
        </div>
        <b>{runs.length}</b>
      </div>
      {runs.length === 0 ? (
        <EmptyState title="No bank imports" detail="Upload the first PNC remote-capture CSV to create a durable reconciliation run." />
      ) : (
        <div className="pn-run-list">
          {runs.map((run) => (
            <button
              type="button"
              key={run.run_id}
              className={selectedRunId === run.run_id ? 'active' : ''}
              disabled={busy}
              onClick={() => onOpen(run.run_id)}
            >
              <span>
                <strong>{run.source_file_name}</strong>
                <small>{formatDate(run.date_from)} – {formatDate(run.date_to)}</small>
              </span>
              <span>
                <StatusPill status={run.status} />
                <small>{run.summary.unresolved_count == null ? 'Open for reconciliation counts' : `${run.summary.unresolved_count} unresolved`} · {formatDateTime(run.created_at)}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

export function DepositList({
  deposits,
  selectedDepositKey,
  onSelect,
}: {
  deposits: DepositSummary[]
  selectedDepositKey: string | null
  onSelect: (depositKey: string | null) => void
}) {
  return (
    <section className="pn-panel pn-deposits" aria-labelledby="pn-deposits-title">
      <div className="pn-panel-heading pn-panel-heading--compact">
        <div>
          <span>Bank control</span>
          <h2 id="pn-deposits-title">Deposits</h2>
        </div>
        {selectedDepositKey && (
          <button type="button" className="pn-link-button" onClick={() => onSelect(null)}>Show all</button>
        )}
      </div>
      {deposits.length === 0 ? (
        <EmptyState title="No deposit evidence" detail="The selected run did not return any deposits." />
      ) : (
        <div className="pn-deposit-list">
          {deposits.map((deposit) => (
            <button
              type="button"
              key={deposit.deposit_key}
              className={selectedDepositKey === deposit.deposit_key ? 'active' : ''}
              onClick={() => onSelect(deposit.deposit_key)}
            >
              <span className="pn-deposit-title">
                <strong>{deposit.payment_location_key ?? deposit.bank_location_raw}</strong>
                <small>Deposit {deposit.deposit_no} · {deposit.physical_item_count} checks</small>
              </span>
              <span className="pn-deposit-amount">
                <strong>{formatCents(deposit.bank_total_cents)}</strong>
                <StatusPill status={deposit.status} />
              </span>
              <span className="pn-balance-line">
                <StatusPill status={deposit.balance_status} /> · Virtual Credit {formatCents(deposit.virtual_credit_amount_cents)} · Difference {formatCents(deposit.virtual_credit_difference_cents)}
              </span>
              <span className="pn-deposit-counts">
                <small>{deposit.matched_count} matched</small>
                <small>{deposit.unresolved_count} unresolved</small>
                <small>{deposit.blocking_exception_count} blocking</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

export function ERPProvenancePanel({
  provenance,
}: {
  provenance: PaymentNotesERPProvenance
}) {
  return (
    <section className="pn-panel pn-provenance" aria-labelledby="pn-provenance-title">
      <div className="pn-panel-heading">
        <div>
          <span>Read-only source evidence</span>
          <h2 id="pn-provenance-title">ERP query provenance</h2>
          <p>Each source query is independently bounded. This evidence is not one atomic ERP snapshot and performs no ERP write.</p>
        </div>
        <StatusPill status={provenance.complete ? 'SOURCE_COMPLETE' : 'SOURCE_INCOMPLETE'} />
      </div>
      <div className="pn-provenance-summary">
        <span><small>Contract</small><strong>{provenance.contract_version}</strong></span>
        <span><small>Snapshot mode</small><strong>{readableStatus(provenance.snapshot_mode)}</strong></span>
        <span><small>WHSIGPAY queries</small><strong>{provenance.expected_payment_query_count}</strong></span>
        <span><small>WHSIGIMG queries</small><strong>{provenance.signature_query_count}</strong></span>
      </div>
      <div className="pn-provenance-query-groups">
        <details>
          <summary>KMTDTA.WHSIGPAY query evidence</summary>
          {provenance.expected_payment_queries.length === 0 ? (
            <small>No expected-payment query was executed.</small>
          ) : (
            <div className="pn-provenance-rows">
              {provenance.expected_payment_queries.map((query) => (
                <div key={`${query.store_number}-${query.canonical_evidence_sha256}`}>
                  <span><strong>Store {query.store_number}</strong><small>{query.routes.join(', ')} · {query.date_from} through {query.date_to}</small></span>
                  <span><StatusPill status={query.complete ? 'SOURCE_COMPLETE' : 'SOURCE_INCOMPLETE'} /><small>{query.returned_count} of {query.row_limit} row limit</small></span>
                  <span><small>{formatDateTime(query.retrieved_at)} · evidence {shortHash(query.canonical_evidence_sha256)}</small></span>
                  {query.error && <span className="pn-provenance-error"><small>{query.error}</small></span>}
                </div>
              ))}
            </div>
          )}
        </details>
        <details>
          <summary>KMTDTA.WHSIGIMG query evidence</summary>
          {provenance.signature_queries.length === 0 ? (
            <small>No signature query was required.</small>
          ) : (
            <div className="pn-provenance-rows">
              {provenance.signature_queries.map((query) => (
                <div key={query.canonical_evidence_sha256}>
                  <span><strong>{query.pair_count} customer/invoice pairs</strong><small>{query.returned_count} rows · limit {query.row_limit}</small></span>
                  <span><StatusPill status={query.complete ? 'SOURCE_COMPLETE' : 'SOURCE_INCOMPLETE'} /></span>
                  <span><small>{formatDateTime(query.retrieved_at)} · evidence {shortHash(query.canonical_evidence_sha256)}</small></span>
                  {query.error && <span className="pn-provenance-error"><small>{query.error}</small></span>}
                </div>
              ))}
            </div>
          )}
        </details>
      </div>
    </section>
  )
}

export function ItemQueue({
  items,
  queue,
  selectedItemId,
  onQueueChange,
  onOpen,
}: {
  items: BankItem[]
  queue: QueueView
  selectedItemId: string | null
  onQueueChange: (queue: QueueView) => void
  onOpen: (itemId: string) => void
}) {
  const counts = useMemo(() => ({
    all: items.length,
    matched: itemsForQueue(items, 'matched').length,
    review: itemsForQueue(items, 'review').length,
    unmatched: itemsForQueue(items, 'unmatched').length,
  }), [items])
  const visibleItems = useMemo(() => itemsForQueue(items, queue), [items, queue])

  return (
    <section className="pn-panel pn-items" aria-labelledby="pn-items-title">
      <div className="pn-panel-heading pn-panel-heading--compact">
        <div>
          <span>One-to-one assignment</span>
          <h2 id="pn-items-title">Payment review queue</h2>
        </div>
        <b>{visibleItems.length}</b>
      </div>
      <div className="pn-queue-tabs" role="tablist" aria-label="Payment match queues">
        {(['all', 'matched', 'review', 'unmatched'] as QueueView[]).map((value) => (
          <button
            type="button"
            key={value}
            role="tab"
            aria-selected={queue === value}
            className={queue === value ? 'active' : ''}
            onClick={() => onQueueChange(value)}
          >
            {readableStatus(value)} <span>{counts[value]}</span>
          </button>
        ))}
      </div>
      {visibleItems.length === 0 ? (
        <EmptyState title="No items in this queue" detail="Change the queue or deposit filter to inspect other bank items." />
      ) : (
        <div className="pn-item-table-wrap">
          <table className="pn-item-table">
            <thead>
              <tr>
                <th>Check</th><th>Amount</th><th>Location</th><th>Disposition</th><th>Candidate</th><th>Signature</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((item) => (
                <tr key={item.bank_item_id} className={selectedItemId === item.bank_item_id ? 'active' : ''}>
                  <td>
                    <button type="button" className="pn-row-link" onClick={() => onOpen(item.bank_item_id)}>
                      <strong>{item.normalized_check_number ?? 'Missing'}</strong>
                      <small>Raw {item.raw_check_number || 'blank'} · line {item.source_line}</small>
                    </button>
                  </td>
                  <td>{formatCents(item.amount_cents)}</td>
                  <td><strong>{item.payment_location_key ?? 'Unresolved'}</strong><small>{item.deposit_no}</small></td>
                  <td><StatusPill status={item.classification} /></td>
                  <td>
                    <strong>{item.selected_payment_id ?? `${item.candidate_count} of ${item.candidate_total_count} candidate${item.candidate_total_count === 1 ? '' : 's'} shown`}</strong>
                    <small>{item.candidate_population_truncated ? `Population truncated at ${item.candidate_display_cap}` : 'Complete candidate population'} · {item.strongest_mismatch ?? item.recommendation_tier ?? 'No additional evidence'}</small>
                  </td>
                  <td><StatusPill status={item.signature_state} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function CandidateCard({
  candidate,
  selected,
  onSelect,
}: {
  candidate: PaymentNoteCandidate
  selected: boolean
  onSelect: () => void
}) {
  return (
    <label className={`pn-candidate ${selected ? 'active' : ''}`}>
      <input type="radio" name="payment-note-candidate" checked={selected} onChange={onSelect} />
      <span className="pn-candidate-main">
        <span className="pn-candidate-title">
          <strong>Payment Note {candidate.payment_id}</strong>
          <span>{readableStatus(candidate.tier)}</span>
        </span>
        <span className="pn-candidate-grid">
          <span><small>Customer</small><strong>{candidate.customer_number ?? 'Unavailable'}</strong></span>
          <span><small>Route</small><strong>{candidate.route || 'Unavailable'}</strong></span>
          <span><small>Check</small><strong>{candidate.normalized_check_number ?? 'Missing'}</strong><em>Raw {candidate.raw_check_number || 'blank'}</em></span>
          <span><small>Amount</small><strong>{formatCents(candidate.amount_cents)}</strong></span>
          <span><small>Invoices</small><strong>{candidate.invoices.join(', ') || candidate.raw_invoices || 'Unavailable'}</strong></span>
          <span><small>Received</small><strong>{candidate.received ?? 'Unknown'}</strong><em>{formatDateTime(candidate.received_at)}</em></span>
        </span>
        <span className="pn-candidate-evidence">
          {candidate.matched_factors.map((feature) => (
            <span className={feature.matched ? 'matched' : 'not-matched'} key={feature.code} title={feature.explanation}>
              {feature.label} {feature.points > 0 ? `+${feature.points}` : ''}
            </span>
          ))}
        </span>
        <span className="pn-signature-summary">
          <StatusPill status={candidate.signature_state} />
          <small>{candidate.signatures.length} source row{candidate.signatures.length === 1 ? '' : 's'}</small>
        </span>
        {candidate.signatures.length > 0 && (
          <span className="pn-signature-list">
            {candidate.signatures.map((signature) => (
              <span key={`${signature.rrn}-${signature.invoice_number}`}>
                <strong>Invoice {signature.invoice_number}</strong>
                <small>{signature.file_name ? 'Image file recorded' : 'No image file'} · signer {signature.signer_name || 'not recorded'} · RRN {signature.rrn}</small>
              </span>
            ))}
          </span>
        )}
        {(candidate.conflicts.length > 0 || candidate.rejection_reasons.length > 0) && (
          <span className="pn-candidate-warnings">
            {[...candidate.conflicts, ...candidate.rejection_reasons].map((reason) => <small key={reason}>{reason}</small>)}
          </span>
        )}
      </span>
    </label>
  )
}

export function ItemDetail({
  item,
  busy,
  onClose,
  onReview,
}: {
  item: BankItem
  busy: boolean
  onClose: () => void
  onReview: (payload: {
    decision: ReviewDecision
    selected_payment_id?: string
    reason: string
  }) => Promise<void>
}) {
  const [decision, setDecision] = useState<ReviewDecision>('hold')
  const [candidateId, setCandidateId] = useState(item.selected_payment_id ?? item.candidates[0]?.payment_id ?? '')
  const [reason, setReason] = useState('')
  const [validation, setValidation] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalizedReason = reason.trim()
    if (decision === 'accept_candidate' && !item.candidate_population_complete) {
      setValidation('Candidate acceptance is unavailable because the backend candidate population is incomplete.')
      return
    }
    if (decision === 'accept_candidate' && !candidateId) {
      setValidation('Select one Payment Note candidate before accepting it for local review.')
      return
    }
    if (!normalizedReason) {
      setValidation('Document the reason for the manual review decision.')
      return
    }
    setValidation('')
    await onReview({
      decision,
      selected_payment_id: decision === 'accept_candidate' ? candidateId : undefined,
      reason: normalizedReason,
    })
    setReason('')
  }

  return (
    <aside className="pn-detail" aria-labelledby="pn-detail-title">
      <div className="pn-detail-header">
        <div>
          <span>Bank item evidence</span>
          <h2 id="pn-detail-title">Check {item.normalized_check_number ?? 'missing'}</h2>
          <p>{formatCents(item.amount_cents)} · {item.payment_location_key ?? item.bank_location_raw} · deposit {item.deposit_no}</p>
        </div>
        <button type="button" className="pn-icon-button" aria-label="Close item detail" onClick={onClose}>×</button>
      </div>

      <div className="pn-boundary-banner">
        <strong>Recommendation only</strong>
        <span>R73 does not update Payment Notes, customer accounts, AR status, or ERP receipt fields.</span>
      </div>

      <div className="pn-detail-summary">
        <span><small>Classification</small><StatusPill status={item.classification} /></span>
        <span><small>Raw check</small><strong>{item.raw_check_number || 'Blank'}</strong></span>
        <span><small>Normalized</small><strong>{item.normalized_check_number ?? 'Unavailable'}</strong></span>
        <span><small>Source line</small><strong>{item.source_line}</strong></span>
        <span><small>Candidate population</small><strong>{item.candidate_count} shown / {item.candidate_total_count} total</strong></span>
        <span><small>Signature</small><StatusPill status={item.signature_state} /></span>
      </div>

      {!item.candidate_population_complete && (
        <Message kind="notice">
          <div>
            <strong>Candidate population incomplete</strong>
            <p>The bounded ERP result contains {item.candidate_total_count} candidates; only {item.candidate_count} are displayed under the {item.candidate_display_cap}-candidate cap. Candidate acceptance remains unavailable.</p>
          </div>
        </Message>
      )}

      <section className="pn-detail-section">
        <div className="pn-detail-section-heading">
          <div><span>Candidate scope</span><h3>Route and date evidence</h3></div>
        </div>
        <div className="pn-route-chips">
          {item.route_scope.length > 0
            ? item.route_scope.map((route) => <span key={route}>{route}</span>)
            : <small>No trustworthy route scope was returned.</small>}
        </div>
      </section>

      {(item.exception_codes.length > 0 || item.explanation.length > 0) && (
        <section className="pn-detail-section">
          <div className="pn-detail-section-heading">
            <div><span>Exception trace</span><h3>Why this item needs attention</h3></div>
          </div>
          <ul className="pn-reason-list">
            {item.exception_codes.map((code) => <li key={code}><strong>{readableStatus(code)}</strong></li>)}
            {item.explanation.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </section>
      )}

      {item.cross_run_reuse_evidence.length > 0 && (
        <section className="pn-detail-section">
          <div className="pn-detail-section-heading">
            <div><span>Prior local evidence</span><h3>Cross-run Payment Note reuse</h3></div>
          </div>
          <p className="pn-section-copy">These records are local evidence from prior runs. They do not establish ERP receipt status or authorize reuse.</p>
          <ul className="pn-reason-list">
            {item.cross_run_reuse_evidence.map((evidence) => (
              <li key={evidence.payment_id}>
                <strong>Payment Note {evidence.payment_id}</strong> · {evidence.prior_run_ids.length} prior run{evidence.prior_run_ids.length === 1 ? '' : 's'} · {evidence.prior_item_ids.length} prior item{evidence.prior_item_ids.length === 1 ? '' : 's'} · {evidence.source_types.join(', ') || 'source type unavailable'}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="pn-detail-section">
        <div className="pn-detail-section-heading">
          <div><span>Payment Notes evidence</span><h3>{item.candidates.length} candidate{item.candidates.length === 1 ? '' : 's'}</h3></div>
        </div>
        {item.candidates.length === 0 ? (
          <EmptyState title="No in-scope candidate" detail="The bank item remains unmatched until a reviewer accepts the exception or source evidence changes." />
        ) : (
          <div className="pn-candidate-list">
            {item.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.payment_id}
                candidate={candidate}
                selected={candidateId === candidate.payment_id}
                onSelect={() => setCandidateId(candidate.payment_id)}
              />
            ))}
          </div>
        )}
      </section>

      {item.current_review && (
        <section className="pn-detail-section">
          <div className="pn-detail-section-heading"><div><span>Human disposition</span><h3>Current review</h3></div></div>
          <div className="pn-current-review">
            <StatusPill status={item.current_review.decision} />
            <p>{item.current_review.reason}</p>
            <small>{item.current_review.actor_name} · {formatDateTime(item.current_review.created_at)} · version {item.current_review.version}</small>
          </div>
        </section>
      )}

      <form className="pn-review-form" onSubmit={(event) => void submit(event)}>
        <div className="pn-detail-section-heading">
          <div><span>Accountable action</span><h3>Record manual review</h3></div>
        </div>
        <label>
          <span>Decision</span>
          <select value={decision} onChange={(event) => setDecision(event.target.value as ReviewDecision)} disabled={busy}>
            <option value="hold">Keep in review</option>
            <option value="accept_candidate" disabled={!item.candidate_population_complete}>Accept candidate for local review</option>
            <option value="leave_unmatched">Record locally as unmatched</option>
          </select>
        </label>
        {decision === 'accept_candidate' && (
          <label>
            <span>Selected Payment Note</span>
            <select value={candidateId} onChange={(event) => setCandidateId(event.target.value)} disabled={busy}>
              <option value="">Select a candidate</option>
              {item.candidates.map((candidate) => (
                <option value={candidate.payment_id} key={candidate.payment_id}>
                  {candidate.payment_id} · {candidate.customer_number ?? 'customer unavailable'} · {formatCents(candidate.amount_cents)}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          <span>Reason</span>
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} disabled={busy} placeholder="Document why this disposition is appropriate." />
        </label>
        {validation && <Message kind="error">{validation}</Message>}
        <button type="submit" className="pn-button pn-button--primary" disabled={busy}>
          {busy ? 'Saving review…' : 'Record review'}
        </button>
        <small>This records an append-only local review. It does not write to ERP or approve cash application.</small>
      </form>
    </aside>
  )
}
