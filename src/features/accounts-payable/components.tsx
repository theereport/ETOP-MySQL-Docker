import type { ReactNode } from 'react'
import type {
  APGovernance,
  APInvoiceDetailResponse,
  APInvoiceSummary,
  APMetric,
  APOverviewResponse,
  DeferredCapability,
  SourceCoverageItem,
} from './types'
import {
  formatConfidence,
  formatCurrency,
  formatDate,
  formatDateTime,
  formatNumber,
  titleCase,
} from './format'

export function StatusTag({ status }: { status: string }) {
  const normalized = status.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return (
    <span className={`ap-status-tag ap-status-tag--${normalized}`}>
      {titleCase(status)}
    </span>
  )
}

export function Message({
  kind,
  children,
}: {
  kind: 'error' | 'notice' | 'success'
  children: ReactNode
}) {
  return (
    <div
      className={`ap-message ap-message--${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
    >
      {children}
    </div>
  )
}

type MetricFormat = 'currency' | 'number' | 'confidence' | 'durationDays'

function metricValue(metric: APMetric, format: MetricFormat): string {
  if (format === 'currency') {
    return formatCurrency(metric.value)
  }
  if (format === 'confidence') {
    return formatConfidence(metric.value)
  }
  if (format === 'durationDays') {
    return metric.value == null ? 'Unavailable' : `${formatNumber(metric.value)} days`
  }
  return formatNumber(metric.value)
}

function MetricCard({
  label,
  metric,
  format,
  emphasis = 'standard',
}: {
  label: string
  metric: APMetric
  format: MetricFormat
  emphasis?: 'standard' | 'attention' | 'positive'
}) {
  const unavailable = metric.value == null
  return (
    <article
      className={`ap-metric-card ap-metric-card--${emphasis}${
        unavailable ? ' ap-metric-card--unavailable' : ''
      }`}
    >
      <div>
        <span>{label}</span>
        <StatusTag status={metric.status} />
      </div>
      <strong>{metricValue(metric, format)}</strong>
      <p>{metric.explanation || 'No explanation was returned by the source service.'}</p>
      <small>
        {metric.source
          ? `${metric.source}${metric.as_of ? ` · ${formatDateTime(metric.as_of)}` : ''}`
          : 'Required source is not connected.'}
      </small>
    </article>
  )
}

export function SourceCoverage({ items }: { items: SourceCoverageItem[] }) {
  return (
    <section className="ap-panel ap-source-panel">
      <div className="ap-panel-heading">
        <div>
          <span className="ap-kicker">Trust boundary</span>
          <h2>Source coverage</h2>
        </div>
        <span className="ap-count">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="ap-empty-inline">
          The service did not return source-coverage evidence. Values should be treated as
          unverified until the source contract is restored.
        </p>
      ) : (
        <div className="ap-source-list">
          {items.map((item) => (
            <article key={item.key}>
              <div>
                <strong>{item.label}</strong>
                <StatusTag status={item.status} />
              </div>
              <p>{item.explanation}</p>
              <small>
                {item.source || 'No governed source connected'}
                {item.as_of ? ` · ${formatDateTime(item.as_of)}` : ''}
                {item.record_count != null ? ` · ${formatNumber(item.record_count)} records` : ''}
              </small>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export function GovernanceBoundary({ governance }: { governance: APGovernance }) {
  return (
    <section className="ap-panel ap-governance-panel">
      <div className="ap-panel-heading">
        <div>
          <span className="ap-kicker">Human authority</span>
          <h2>Increment 1 governance</h2>
        </div>
        <StatusTag status={governance.erp_access || 'unknown'} />
      </div>
      <dl className="ap-definition-list">
        <div><dt>ERP write</dt><dd>{governance.erp_write ? 'Enabled' : 'Not permitted'}</dd></div>
        <div><dt>Automatic approval</dt><dd>{governance.automatic_approval ? 'Enabled' : 'Not enabled'}</dd></div>
        <div><dt>Approval effect</dt><dd>{governance.approval_effect || 'Unspecified'}</dd></div>
        <div><dt>Payment effect</dt><dd>{governance.payment_effect || 'Unspecified'}</dd></div>
        <div><dt>Source authority</dt><dd>{governance.source_authority || 'Unspecified'}</dd></div>
      </dl>
      {governance.statements.length > 0 && (
        <ul className="ap-governance-statements">
          {governance.statements.map((statement) => <li key={statement}>{statement}</li>)}
        </ul>
      )}
    </section>
  )
}

export function DeferredCapabilities({
  capabilities,
}: {
  capabilities: DeferredCapability[]
}) {
  return (
    <section className="ap-panel ap-deferred-panel">
      <div className="ap-panel-heading">
        <div>
          <span className="ap-kicker">Source readiness</span>
          <h2>Target capabilities not active in Increment 1</h2>
        </div>
      </div>
      {capabilities.length === 0 ? (
        <p className="ap-empty-inline">No deferred-capability record was returned.</p>
      ) : (
        <div className="ap-deferred-grid">
          {capabilities.map((capability) => (
            <article key={capability.key} aria-disabled="true">
              <div>
                <strong>{capability.label}</strong>
                <StatusTag status={capability.status} />
              </div>
              <p>{capability.reason}</p>
              {capability.missing_sources.length > 0 && (
                <small>Needs: {capability.missing_sources.join(', ')}</small>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export function ExecutiveOverview({ overview }: { overview: APOverviewResponse }) {
  const { metrics } = overview
  return (
    <div className="ap-overview-grid">
      <section className="ap-metric-grid" aria-label="Accounts payable health metrics">
        <MetricCard label="Imported invoices" metric={metrics.imported_invoice_count} format="number" />
        <MetricCard label="Waiting for review" metric={metrics.review_required_count} format="number" emphasis="attention" />
        <MetricCard label="Exceptions" metric={metrics.exception_count} format="number" emphasis="attention" />
        <MetricCard label="Duplicate candidates" metric={metrics.duplicate_candidate_count} format="number" emphasis="attention" />
        <MetricCard label="OCR processed" metric={metrics.ocr_processed_count} format="number" />
        <MetricCard label="Average OCR confidence" metric={metrics.ocr_average_confidence} format="confidence" />
        <MetricCard label="Document-extracted invoice total" metric={metrics.extracted_invoice_total} format="currency" />
        <MetricCard label="Current AP balance" metric={metrics.current_ap_balance} format="currency" />
        <MetricCard label="Invoices due today" metric={metrics.due_today_count} format="number" />
        <MetricCard label="Amount due today" metric={metrics.due_today_amount} format="currency" />
        <MetricCard label="Past-due invoices" metric={metrics.past_due_count} format="number" emphasis="attention" />
        <MetricCard label="Past-due amount" metric={metrics.past_due_amount} format="currency" emphasis="attention" />
        <MetricCard label="Cash required in 7 days" metric={metrics.due_within_7_days_amount} format="currency" />
        <MetricCard label="Discounts available" metric={metrics.discounts_available} format="currency" />
        <MetricCard label="Average approval time" metric={metrics.average_approval_time} format="durationDays" />
      </section>

      {overview.warnings.length > 0 && (
        <Message kind="notice">
          <div>
            <strong>Coverage warnings</strong>
            <ul>{overview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </div>
        </Message>
      )}

      <div className="ap-two-column">
        <SourceCoverage items={overview.source_coverage} />
        <GovernanceBoundary governance={overview.governance} />
      </div>
      <DeferredCapabilities capabilities={overview.deferred_capabilities} />
    </div>
  )
}

export function InvoiceTable({
  invoices,
  busy,
  selectedId,
  onOpen,
}: {
  invoices: APInvoiceSummary[]
  busy: boolean
  selectedId: string | null
  onOpen: (invoice: APInvoiceSummary) => void
}) {
  return (
    <div className="ap-table-wrap">
      <table className="ap-invoice-table">
        <thead>
          <tr>
            <th>Invoice</th>
            <th>Vendor</th>
            <th>Received</th>
            <th>Due</th>
            <th>Amount</th>
            <th>OCR</th>
            <th>Review evidence</th>
            <th>Status</th>
            <th><span className="ap-visually-hidden">Open</span></th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <tr key={invoice.ap_invoice_id} className={selectedId === invoice.ap_invoice_id ? 'is-selected' : ''}>
              <td>
                <strong>{invoice.invoice_number || 'Not extracted'}</strong>
                <small>{invoice.source_file_name || `Document ${invoice.document_job_id}`}</small>
              </td>
              <td>
                <strong>{invoice.vendor_name || 'Vendor not resolved'}</strong>
                <small>{invoice.vendor_number ? `Vendor ${invoice.vendor_number}` : 'Vendor number unavailable'}</small>
              </td>
              <td>{formatDate(invoice.received_at)}</td>
              <td>{formatDate(invoice.due_date)}</td>
              <td>{formatCurrency(invoice.total_amount)}</td>
              <td>
                <strong>{formatConfidence(invoice.ocr_confidence)}</strong>
                {invoice.ocr_review_required && <small>Review required</small>}
              </td>
              <td>
                <span>{invoice.exception_count} exception{invoice.exception_count === 1 ? '' : 's'}</span>
                <small>{invoice.duplicate_candidate_count} duplicate candidate{invoice.duplicate_candidate_count === 1 ? '' : 's'}</small>
              </td>
              <td><StatusTag status={invoice.status || 'unknown'} /></td>
              <td>
                <button
                  type="button"
                  className="ap-table-open"
                  onClick={() => onOpen(invoice)}
                  disabled={busy}
                  aria-label={`Open invoice ${invoice.invoice_number || invoice.ap_invoice_id}`}
                >
                  Open
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FieldValue({ value }: { value: string | number | boolean | null }) {
  if (value == null || value === '') {
    return <>Unavailable</>
  }
  if (typeof value === 'boolean') {
    return <>{value ? 'Yes' : 'No'}</>
  }
  return <>{String(value)}</>
}

export function InvoiceDetail({
  invoice,
  busy,
  error,
  onClose,
  onRetry,
}: {
  invoice: APInvoiceDetailResponse | null
  busy: boolean
  error: string
  onClose: () => void
  onRetry: () => void
}) {
  return (
    <aside className="ap-detail" aria-label="Invoice intelligence detail" aria-busy={busy}>
      <div className="ap-detail-header">
        <div>
          <span className="ap-kicker">Invoice intelligence</span>
          <h2>{invoice?.invoice_number || 'Invoice detail'}</h2>
          {invoice && <p>{invoice.vendor_name || 'Vendor not resolved'}</p>}
        </div>
        <button type="button" className="ap-icon-button" onClick={onClose} aria-label="Close invoice detail">×</button>
      </div>

      {busy && (
        <div className="ap-detail-loading" role="status">
          <span className="ap-spinner" />
          Loading source evidence…
        </div>
      )}
      {error && (
        <Message kind="error">
          <span>{error}</span>
          <button type="button" onClick={onRetry}>Retry</button>
        </Message>
      )}

      {invoice && !busy && (
        <div className="ap-detail-body">
          <section className="ap-detail-summary">
            <div><span>Amount</span><strong>{formatCurrency(invoice.total_amount)}</strong></div>
            <div><span>Invoice date</span><strong>{formatDate(invoice.invoice_date)}</strong></div>
            <div><span>Due date</span><strong>{formatDate(invoice.due_date)}</strong></div>
            <div><span>OCR confidence</span><strong>{formatConfidence(invoice.ocr_confidence)}</strong></div>
            <div><span>Purchase order</span><strong>{invoice.purchase_order_number || 'Unavailable'}</strong></div>
            <div><span>Classification confidence</span><strong>{formatConfidence(invoice.classification_confidence)}</strong></div>
            <div><span>Source as of</span><strong>{formatDateTime(invoice.source_as_of)}</strong></div>
            <div><span>Evidence revisions</span><strong>{formatNumber(invoice.evidence_revision_count)}</strong></div>
          </section>

          {invoice.warnings.length > 0 && (
            <Message kind="notice"><ul>{invoice.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></Message>
          )}

          <section className="ap-detail-section">
            <div className="ap-section-heading">
              <h3>Extracted fields</h3>
              <span>{invoice.extracted_fields.length}</span>
            </div>
            {invoice.extracted_fields.length === 0 ? (
              <p className="ap-empty-inline">No extracted field evidence was returned.</p>
            ) : (
              <div className="ap-field-list">
                {invoice.extracted_fields.map((field) => (
                  <article key={field.field_name}>
                    <div>
                      <span>{field.label}</span>
                      <StatusTag status={field.validation_status || 'unknown'} />
                    </div>
                    <strong><FieldValue value={field.normalized_value ?? field.value} /></strong>
                    <small>
                      {field.source || 'Source unavailable'} · Confidence {formatConfidence(field.confidence)}
                      {field.page != null ? ` · Page ${field.page}` : ''}
                    </small>
                    <small>
                      Authority: {titleCase(field.authority)}
                      {field.rule_version ? ` · Rule ${field.rule_version}` : ''}
                    </small>
                    {field.explanation && <p>{field.explanation}</p>}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="ap-detail-section">
            <div className="ap-section-heading"><h3>Exceptions</h3><span>{invoice.exceptions.length}</span></div>
            {invoice.exceptions.length === 0 ? (
              <p className="ap-empty-inline">No exception evidence is attached to this invoice.</p>
            ) : (
              <div className="ap-evidence-list">
                {invoice.exceptions.map((exception) => (
                  <article key={exception.code}>
                    <div><strong>{exception.label}</strong><StatusTag status={exception.severity} /></div>
                    <p>{exception.explanation}</p>
                    {exception.evidence.length > 0 && <ul>{exception.evidence.map((item) => <li key={item}>{item}</li>)}</ul>}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="ap-detail-section">
            <div className="ap-section-heading"><h3>Duplicate evidence</h3><span>{invoice.duplicate_evidence.length}</span></div>
            {invoice.duplicate_evidence.length === 0 ? (
              <p className="ap-empty-inline">No duplicate candidate evidence is attached.</p>
            ) : (
              <div className="ap-evidence-list">
                {invoice.duplicate_evidence.map((candidate) => (
                  <article key={candidate.candidate_ap_invoice_id}>
                    <div><strong>{candidate.candidate_invoice_number || candidate.candidate_ap_invoice_id}</strong><span>{formatConfidence(candidate.confidence)}</span></div>
                    <p>{candidate.explanation}</p>
                    <small>{candidate.candidate_vendor_name || 'Vendor unavailable'} · {formatCurrency(candidate.candidate_amount)}</small>
                    <small>
                      Amount: {titleCase(candidate.amount_corroboration)} · Date: {titleCase(candidate.date_corroboration)}
                    </small>
                    {candidate.match_factors.length > 0 && <ul>{candidate.match_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul>}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="ap-detail-section">
            <div className="ap-section-heading"><h3>Invoice timeline</h3><span>{invoice.timeline.length}</span></div>
            {invoice.timeline.length === 0 ? (
              <p className="ap-empty-inline">No timestamped events were returned.</p>
            ) : (
              <ol className="ap-timeline">
                {invoice.timeline.map((event) => (
                  <li key={event.event_id}>
                    <i />
                    <div>
                      <strong>{event.label}</strong>
                      <span>{formatDateTime(event.occurred_at)} · {event.source}</span>
                      {event.details && <p>{event.details}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <SourceCoverage items={invoice.source_coverage} />
          <GovernanceBoundary governance={invoice.governance} />

          <footer className="ap-detail-provenance">
            <strong>Source document</strong>
            <span>{invoice.source_document.file_name || invoice.source_file_name}</span>
            <small>
              Job {invoice.source_document.job_id || invoice.document_job_id} · Document/extraction review status:{' '}
              {titleCase(invoice.source_document.status)}
            </small>
            <p>
              A source status such as “Approved” refers only to Document Intelligence
              extraction review. It is not AP invoice approval, payment authorization,
              posting authority, or evidence of an ERP write.
            </p>
            <small>Evidence SHA-256</small>
            <code>{invoice.source_evidence_sha256}</code>
            {invoice.provenance.length > 0 && <ul>{invoice.provenance.map((item) => <li key={item}>{item}</li>)}</ul>}
          </footer>
        </div>
      )}
    </aside>
  )
}
