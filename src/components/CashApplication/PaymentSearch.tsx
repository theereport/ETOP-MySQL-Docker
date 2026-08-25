import type { FormEvent } from 'react'

type PaymentSearchProps = {
  customerNumber: string
  paymentAmount: string
  paymentDate: string
  suppliedInvoiceNumbers: string
  isLoading: boolean
  onCustomerNumberChange: (value: string) => void
  onPaymentAmountChange: (value: string) => void
  onPaymentDateChange: (value: string) => void
  onSuppliedInvoiceNumbersChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

function PaymentSearch({
  customerNumber,
  paymentAmount,
  paymentDate,
  suppliedInvoiceNumbers,
  isLoading,
  onCustomerNumberChange,
  onPaymentAmountChange,
  onPaymentDateChange,
  onSuppliedInvoiceNumbersChange,
  onSubmit,
}: PaymentSearchProps) {
  return (
    <form
      className="cash-search-panel"
      onSubmit={onSubmit}
    >
      <div className="cash-search-heading">
        <div>
          <strong>Payment information</strong>
          <span>
            Only invoices with an open balance greater than
            $0.00 are eligible.
          </span>
        </div>

        <span className="cash-read-only-badge">
          Recommendation Only
        </span>
      </div>

      <div className="cash-search-grid">
        <label>
          <span>Customer number</span>

          <input
            value={customerNumber}
            onChange={(event) =>
              onCustomerNumberChange(event.target.value)
            }
            placeholder="640194"
            autoComplete="off"
          />
        </label>

        <label>
          <span>Payment amount</span>

          <div className="cash-money-input">
            <span>$</span>

            <input
              value={paymentAmount}
              onChange={(event) =>
                onPaymentAmountChange(event.target.value)
              }
              inputMode="decimal"
              placeholder="22607.28"
              autoComplete="off"
            />
          </div>
        </label>

        <label>
          <span>Payment received date</span>

          <input
            type="date"
            value={paymentDate}
            onChange={(event) =>
              onPaymentDateChange(event.target.value)
            }
          />
        </label>

        <label className="cash-invoice-input">
          <span>Remittance invoice numbers</span>

          <input
            value={suppliedInvoiceNumbers}
            onChange={(event) =>
              onSuppliedInvoiceNumbersChange(
                event.target.value,
              )
            }
            placeholder="Optional — separate with commas"
            autoComplete="off"
          />
        </label>
      </div>

      <div className="cash-search-actions">
        <div>
          <strong>Safe review mode</strong>
          <span>
            No ERP posting or invoice update will be performed.
          </span>
        </div>

        <button
          type="submit"
          className="desktop-primary-button"
          disabled={isLoading}
        >
          {isLoading
            ? 'Evaluating Payment…'
            : 'Find Recommendation'}
        </button>
      </div>
    </form>
  )
}

export default PaymentSearch