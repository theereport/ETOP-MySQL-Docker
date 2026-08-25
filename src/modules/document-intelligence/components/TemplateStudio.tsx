export default function TemplateStudio() {
  return (
    <section className="ed-card">
      <div className="ed-card-heading">
        <div>
          <strong>
            Output Template Studio
          </strong>
          <span>
            Planned backend integration
          </span>
        </div>
      </div>

      <div className="ed-template-grid">
        <article>
          <span>LOCKBOX</span>
          <strong>
            PNC Standard Excel
          </strong>
          <p>
            Deposit date, batch, check,
            customer, invoice, amount,
            and reference columns.
          </p>
        </article>

        <article>
          <span>
            ACCOUNTS PAYABLE
          </span>
          <strong>
            AP Invoice Intake
          </strong>
          <p>
            Vendor, invoice, PO, dates,
            location, GL, tax, freight,
            and total.
          </p>
        </article>
      </div>
    </section>
  )
}
