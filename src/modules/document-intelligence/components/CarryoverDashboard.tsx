import { useEffect, useState } from 'react'

import {
  carryoverExportUrl,
  getCarryoverTransactions,
  getLockboxReview,
} from '../api'
import type { LockboxReviewResult, ReviewedLockboxTransaction } from '../types'
import LockboxReviewWorkspace from './LockboxReviewWorkspace'

type CarryoverTransaction = ReviewedLockboxTransaction & {
  job_id: string
  source_file_name: string
}

function money(value: number) {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

export default function CarryoverDashboard() {
  const [transactions, setTransactions] = useState<CarryoverTransaction[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [openJobId, setOpenJobId] = useState('')
  const [openTransactionId, setOpenTransactionId] = useState('')
  const [openReview, setOpenReview] = useState<LockboxReviewResult | null>(null)
  const [isOpeningReview, setIsOpeningReview] = useState(false)
  const [customerFilter, setCustomerFilter] = useState('')

  const loadCarryover = () => {
    setIsLoading(true)
    setError('')
    getCarryoverTransactions().then((response) => {
      setTransactions(response.transactions as CarryoverTransaction[])
    }).catch((err) => {
      setError(err instanceof Error ? err.message : 'Unable to load carryover transactions.')
    }).finally(() => {
      setIsLoading(false)
    })
  }

  useEffect(() => {
    loadCarryover()
  }, [])

  const openTransaction = (transaction: CarryoverTransaction) => {
    setIsOpeningReview(true)
    setError('')
    getLockboxReview(transaction.job_id).then((review) => {
      setOpenJobId(transaction.job_id)
      setOpenTransactionId(transaction.transaction_id)
      setOpenReview(review)
    }).catch((err) => {
      setError(err instanceof Error ? err.message : 'Unable to open this transaction.')
    }).finally(() => {
      setIsOpeningReview(false)
    })
  }

  const normalizedFilter = customerFilter.trim().toLowerCase()
  const visibleTransactions = normalizedFilter
    ? transactions.filter((transaction) => (
      transaction.customer_name?.toLowerCase().includes(normalizedFilter)
      || transaction.customer_number?.toLowerCase().includes(normalizedFilter)
    ))
    : transactions

  const totalCheckAmount = visibleTransactions.reduce(
    (total, transaction) => total + Number(transaction.check_amount || 0),
    0,
  )

  // A filter narrowed to exactly one customer number scopes the export too -
  // otherwise it stays the full cross-customer approved-carryover export.
  const filteredCustomerNumbers = new Set(
    visibleTransactions.map((transaction) => transaction.customer_number).filter(Boolean),
  )
  const exportCustomerNumber = normalizedFilter && filteredCustomerNumbers.size === 1
    ? [...filteredCustomerNumbers][0]
    : ''

  return (
    <div className="carryover-dashboard">
      <style>{`
        .carryover-dashboard { padding: 20px; color: #edf4fc; }
        .carryover-dashboard-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 16px;
        }
        .carryover-dashboard-header h2 { margin: 0 0 4px; font-size: 20px; }
        .carryover-dashboard-header p { margin: 0; color: #aebdd2; font-size: 13px; }
        .carryover-dashboard-actions { display: flex; gap: 8px; }
        .carryover-dashboard-actions a,
        .carryover-dashboard-actions button {
          padding: 9px 14px;
          border-radius: 7px;
          border: 1px solid #3b526f;
          background: #16223a;
          color: #edf4fc;
          font-size: 12px;
          text-decoration: none;
          cursor: pointer;
        }
        .carryover-dashboard-filter {
          padding: 9px 12px;
          border-radius: 7px;
          border: 1px solid #3b526f;
          background: #0f1928;
          color: #edf4fc;
          font-size: 12px;
          min-width: 220px;
        }
        .carryover-dashboard-metrics {
          display: flex;
          gap: 14px;
          margin-bottom: 16px;
        }
        .carryover-dashboard-metric {
          padding: 12px 16px;
          border: 1px solid #3b526f;
          border-radius: 8px;
          background: #0f1928;
        }
        .carryover-dashboard-metric strong { display: block; font-size: 22px; }
        .carryover-dashboard-metric span { color: #aebdd2; font-size: 12px; }
        .carryover-dashboard-table-wrap {
          border: 1px solid #3b526f;
          border-radius: 8px;
          overflow: auto;
        }
        .carryover-dashboard table { width: 100%; border-collapse: collapse; font-size: 12px; }
        .carryover-dashboard th {
          text-align: left;
          padding: 10px 12px;
          background: #16223a;
          color: #aebdd2;
          border-bottom: 1px solid #3b526f;
        }
        .carryover-dashboard td {
          padding: 10px 12px;
          border-bottom: 1px solid #263952;
        }
        .carryover-dashboard tr.carryover-row {
          cursor: pointer;
        }
        .carryover-dashboard tr.carryover-row:hover { background: #182841; }
        .carryover-dashboard-empty {
          padding: 24px;
          text-align: center;
          color: #aebdd2;
        }
        .carryover-dashboard-error {
          margin-bottom: 12px;
          padding: 10px 12px;
          border: 1px solid rgba(239, 107, 115, 0.3);
          background: rgba(239, 107, 115, 0.08);
          color: #ffadb3;
          border-radius: 7px;
          font-size: 12px;
        }
      `}</style>

      <div className="carryover-dashboard-header">
        <div>
          <h2>Carryover Dashboard</h2>
          <p>
            Every lockbox transaction currently parked as carryover, across
            every job. Working one here updates it in its original job -
            there is no separate copy of the data.
          </p>
        </div>
        <div className="carryover-dashboard-actions">
          <input
            type="text"
            className="carryover-dashboard-filter"
            value={customerFilter}
            onChange={(event) => setCustomerFilter(event.target.value)}
            placeholder="Filter by customer name or number"
          />
          <button type="button" onClick={loadCarryover} disabled={isLoading}>
            {isLoading ? 'Refreshing…' : 'Refresh'}
          </button>
          <a href={carryoverExportUrl(exportCustomerNumber)}>
            {exportCustomerNumber
              ? 'Export Approved Carryover (this customer)'
              : 'Export Approved Carryover'}
          </a>
        </div>
      </div>

      {error && <div className="carryover-dashboard-error">{error}</div>}

      <div className="carryover-dashboard-metrics">
        <div className="carryover-dashboard-metric">
          <strong>{visibleTransactions.length}</strong>
          <span>Carryover Transactions</span>
        </div>
        <div className="carryover-dashboard-metric">
          <strong>{money(totalCheckAmount)}</strong>
          <span>Total Check Amount</span>
        </div>
      </div>

      <div className="carryover-dashboard-table-wrap">
        {visibleTransactions.length === 0 ? (
          <div className="carryover-dashboard-empty">
            {isLoading
              ? 'Loading carryover transactions…'
              : normalizedFilter
                ? 'No carryover transactions match this filter.'
                : 'No transactions are currently parked as carryover.'}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Transaction</th>
                <th>Source PDF</th>
                <th>Customer</th>
                <th>Check</th>
                <th>Check Amount</th>
              </tr>
            </thead>
            <tbody>
              {visibleTransactions.map((transaction) => (
                <tr
                  key={`${transaction.job_id}:${transaction.transaction_id}`}
                  className="carryover-row"
                  onClick={() => openTransaction(transaction)}
                >
                  <td>{transaction.transaction_id}</td>
                  <td>{transaction.source_file_name}</td>
                  <td>{transaction.customer_name}</td>
                  <td>{transaction.check_number}</td>
                  <td>{money(Number(transaction.check_amount || 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {isOpeningReview && (
        <div className="carryover-dashboard-empty">Opening transaction…</div>
      )}

      {openReview && openTransactionId && (
        <LockboxReviewWorkspace
          jobId={openJobId}
          review={openReview}
          initialTransactionId={openTransactionId}
          onClose={() => {
            setOpenReview(null)
            setOpenTransactionId('')
            setOpenJobId('')
          }}
          onUpdated={(updated) => {
            setOpenReview(updated)
            loadCarryover()
          }}
        />
      )}
    </div>
  )
}
