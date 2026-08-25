import { useMemo, useState } from 'react'

import type {
  CombinationMatch,
  CombinationResult,
} from './CashApplication'

type InvoiceDetail = {
  invoice_number: string
  invoice_date?: string | null
  due_date?: string | null
  original_amount?: string | number | null
  open_balance?: string | number | null
  recommended_amount?: string | number | null
  due_date_bucket?: string | null
  rank?: number | null
}

type InvoiceGridProps = {
  recommendedInvoiceNumbers: string[]
  combinationResult?: CombinationResult
  invoiceDetails?: InvoiceDetail[]
}

function formatCurrency(
  value: string | number | null | undefined,
) {
  if (
    value === null ||
    value === undefined ||
    value === ''
  ) {
    return '—'
  }

  const parsedValue = Number(value)

  if (Number.isNaN(parsedValue)) {
    return String(value)
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(parsedValue)
}

function formatDate(value?: string | null) {
  if (!value) {
    return '—'
  }

  const normalizedValue = value.includes('T')
    ? value
    : `${value}T00:00:00`

  const parsedDate = new Date(normalizedValue)

  if (Number.isNaN(parsedDate.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(parsedDate)
}

function normalizeInvoiceNumber(value: unknown) {
  return String(value ?? '').trim()
}

function getMatchInvoiceNumbers(
  match: CombinationMatch,
): string[] {
  return (
    match.invoice_numbers ??
    (
      match as CombinationMatch & {
        invoices?: Array<
          | string
          | {
              invoice_number?: string
            }
        >
      }
    ).invoices?.map((invoice) => {
      if (typeof invoice === 'string') {
        return invoice
      }

      return invoice.invoice_number ?? ''
    }) ??
    []
  )
    .map(normalizeInvoiceNumber)
    .filter(Boolean)
}

function getInvoiceDetailsFromCombination(
  combinationResult?: CombinationResult,
): InvoiceDetail[] {
  if (!combinationResult) {
    return []
  }

  const extendedResult = combinationResult as CombinationResult & {
    recommended_invoices?: InvoiceDetail[]
    invoice_details?: InvoiceDetail[]
    candidates?: InvoiceDetail[]
  }

  return (
    extendedResult.recommended_invoices ??
    extendedResult.invoice_details ??
    extendedResult.candidates ??
    []
  )
}

function getAlternativeTotal(match: CombinationMatch) {
  const extendedMatch = match as CombinationMatch & {
    matched_amount?: string | number
    payment_total?: string | number
  }

  return (
    match.total_amount ??
    extendedMatch.matched_amount ??
    extendedMatch.payment_total
  )
}

function getAlternativeDueDates(match: CombinationMatch) {
  const extendedMatch = match as CombinationMatch & {
    earliest_due_date?: string | null
    latest_due_date?: string | null
  }

  if (match.due_dates?.length) {
    return match.due_dates
  }

  return [
    extendedMatch.earliest_due_date,
    extendedMatch.latest_due_date,
  ].filter((value): value is string => Boolean(value))
}

function InvoiceGrid({
  recommendedInvoiceNumbers,
  combinationResult,
  invoiceDetails = [],
}: InvoiceGridProps) {
  const [showAlternatives, setShowAlternatives] =
    useState(false)

  const normalizedRecommendedNumbers = useMemo(() => {
    return recommendedInvoiceNumbers
      .map(normalizeInvoiceNumber)
      .filter(Boolean)
  }, [recommendedInvoiceNumbers])

  const displayedInvoices = useMemo(() => {
    const backendInvoiceDetails =
      invoiceDetails.length > 0
        ? invoiceDetails
        : getInvoiceDetailsFromCombination(
            combinationResult,
          )

    const detailsByInvoiceNumber = new Map(
      backendInvoiceDetails.map((invoice) => [
        normalizeInvoiceNumber(invoice.invoice_number),
        invoice,
      ]),
    )

    return normalizedRecommendedNumbers.map(
      (invoiceNumber, index) => {
        const details =
          detailsByInvoiceNumber.get(invoiceNumber)

        return {
          invoice_number: invoiceNumber,
          invoice_date: details?.invoice_date ?? null,
          due_date: details?.due_date ?? null,
          original_amount:
            details?.original_amount ?? null,
          open_balance: details?.open_balance ?? null,
          recommended_amount:
            details?.recommended_amount ??
            details?.open_balance ??
            null,
          due_date_bucket:
            details?.due_date_bucket ?? null,
          rank: details?.rank ?? index + 1,
        }
      },
    )
  }, [
    combinationResult,
    invoiceDetails,
    normalizedRecommendedNumbers,
  ])

  const recommendedTotal = useMemo(() => {
    const amounts = displayedInvoices
      .map((invoice) =>
        Number(invoice.recommended_amount),
      )
      .filter((value) => !Number.isNaN(value))

    if (amounts.length !== displayedInvoices.length) {
      return null
    }

    return amounts.reduce(
      (total, amount) => total + amount,
      0,
    )
  }, [displayedInvoices])

  const alternatives = useMemo(() => {
    return (combinationResult?.matches ?? []).filter(
      (match) => {
        const invoiceNumbers =
          getMatchInvoiceNumbers(match)

        if (
          invoiceNumbers.length !==
          normalizedRecommendedNumbers.length
        ) {
          return true
        }

        return invoiceNumbers.some(
          (invoiceNumber, index) =>
            invoiceNumber !==
            normalizedRecommendedNumbers[index],
        )
      },
    )
  }, [
    combinationResult?.matches,
    normalizedRecommendedNumbers,
  ])

  return (
    <section className="cash-panel-card cash-invoice-card">
      <div className="cash-panel-heading">
        <div>
          <strong>Invoice recommendation</strong>
          <span>
            Open invoices selected by the decision engine
          </span>
        </div>

        <span className="cash-panel-count">
          {displayedInvoices.length}
        </span>
      </div>

      {displayedInvoices.length > 0 ? (
        <>
          <div className="cash-invoice-table-wrapper">
            <table className="cash-invoice-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Invoice</th>
                  <th>Invoice date</th>
                  <th>Due date</th>
                  <th>Due bucket</th>
                  <th className="cash-numeric-column">
                    Original amount
                  </th>
                  <th className="cash-numeric-column">
                    Open balance
                  </th>
                  <th className="cash-numeric-column">
                    Apply amount
                  </th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                {displayedInvoices.map((invoice) => (
                  <tr
                    key={`${invoice.invoice_number}-${invoice.rank}`}
                  >
                    <td>
                      <span className="cash-invoice-rank">
                        {invoice.rank}
                      </span>
                    </td>

                    <td>
                      <strong>
                        {invoice.invoice_number}
                      </strong>
                    </td>

                    <td>
                      {formatDate(invoice.invoice_date)}
                    </td>

                    <td>
                      {formatDate(invoice.due_date)}
                    </td>

                    <td>
                      {invoice.due_date_bucket ? (
                        <span className="cash-due-bucket">
                          {invoice.due_date_bucket}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>

                    <td className="cash-numeric-column">
                      {formatCurrency(
                        invoice.original_amount,
                      )}
                    </td>

                    <td className="cash-numeric-column">
                      {formatCurrency(
                        invoice.open_balance,
                      )}
                    </td>

                    <td className="cash-numeric-column">
                      <strong>
                        {formatCurrency(
                          invoice.recommended_amount,
                        )}
                      </strong>
                    </td>

                    <td>
                      <span className="cash-table-status">
                        Recommended
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>

              <tfoot>
                <tr>
                  <td colSpan={7}>
                    Recommended application total
                  </td>

                  <td className="cash-numeric-column">
                    <strong>
                      {recommendedTotal === null
                        ? '—'
                        : formatCurrency(
                            recommendedTotal,
                          )}
                    </strong>
                  </td>

                  <td />
                </tr>
              </tfoot>
            </table>
          </div>

          {recommendedTotal === null && (
            <div className="cash-grid-notice">
              Invoice details were not included in the
              response, so amount and date fields cannot yet
              be displayed.
            </div>
          )}
        </>
      ) : (
        <div className="cash-no-invoice-result">
          <div>∅</div>

          <strong>No open invoice recommendation</strong>

          <p>
            No eligible open invoice or exact combination was
            selected for this payment.
          </p>
        </div>
      )}

      {combinationResult && (
        <div className="cash-combination-diagnostics">
          <div>
            <span>Combination status</span>
            <strong>
              {combinationResult.status.replaceAll(
                '_',
                ' ',
              )}
            </strong>
          </div>

          <div>
            <span>Invoices searched</span>
            <strong>
              {combinationResult.searched_invoice_count}
            </strong>
          </div>

          <div>
            <span>Exact alternatives</span>
            <strong>{alternatives.length}</strong>
          </div>

          <div>
            <span>Anchor due date</span>
            <strong>
              {formatDate(
                combinationResult.anchor_due_date,
              )}
            </strong>
          </div>

          <div>
            <span>Matched through</span>
            <strong>
              {formatDate(
                combinationResult.matched_through_due_date,
              )}
            </strong>
          </div>

          <div>
            <span>Search truncated</span>
            <strong>
              {combinationResult.truncated
                ? 'Yes'
                : 'No'}
            </strong>
          </div>
        </div>
      )}

      {alternatives.length > 0 && (
        <div className="cash-alternative-section">
          <button
            type="button"
            className="cash-alternative-toggle"
            onClick={() =>
              setShowAlternatives((current) => !current)
            }
          >
            <span>
              Alternative exact combinations
              <small>
                {alternatives.length} additional option
                {alternatives.length === 1 ? '' : 's'}
              </small>
            </span>

            <strong>
              {showAlternatives ? 'Hide' : 'Review'}
            </strong>
          </button>

          {showAlternatives && (
            <div className="cash-alternative-list">
              {alternatives.map((match, index) => {
                const invoiceNumbers =
                  getMatchInvoiceNumbers(match)

                const dueDates =
                  getAlternativeDueDates(match)

                return (
                  <article
                    className="cash-alternative-card"
                    key={`alternative-${index}`}
                  >
                    <div className="cash-alternative-heading">
                      <div>
                        <strong>
                          Alternative {index + 1}
                        </strong>

                        <span>
                          {invoiceNumbers.length}{' '}
                          invoice
                          {invoiceNumbers.length === 1
                            ? ''
                            : 's'}
                        </span>
                      </div>

                      <strong>
                        {formatCurrency(
                          getAlternativeTotal(match),
                        )}
                      </strong>
                    </div>

                    <div className="cash-alternative-invoices">
                      {invoiceNumbers.map(
                        (invoiceNumber) => (
                          <span key={invoiceNumber}>
                            {invoiceNumber}
                          </span>
                        ),
                      )}
                    </div>

                    <div className="cash-alternative-meta">
                      <span>
                        Score:{' '}
                        <strong>
                          {match.score ?? '—'}
                        </strong>
                      </span>

                      <span>
                        Due range:{' '}
                        <strong>
                          {dueDates.length
                            ? dueDates
                                .map(formatDate)
                                .join(' – ')
                            : '—'}
                        </strong>
                      </span>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export default InvoiceGrid