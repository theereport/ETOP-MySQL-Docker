import type {
  BusinessRuleResult,
  HistoricalBehavior,
} from './CashApplication'

type BusinessRulesPanelProps = {
  businessRuleResult?: BusinessRuleResult
  historicalBehavior?: HistoricalBehavior
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

function BusinessRulesPanel({
  businessRuleResult,
  historicalBehavior,
}: BusinessRulesPanelProps) {
  return (
    <section className="cash-panel-card">
      <div className="cash-panel-heading">
        <div>
          <strong>Business rules</strong>
          <span>
            Centralized decision controls and historical context
          </span>
        </div>

        <span className="cash-panel-icon">✓</span>
      </div>

      {businessRuleResult ? (
        <>
          <div className="cash-rule-state-grid">
            <div>
              <span>Auto-apply eligible</span>
              <strong>
                {businessRuleResult.auto_apply_allowed
                  ? 'Yes'
                  : 'No'}
              </strong>
            </div>

            <div>
              <span>Review required</span>
              <strong>
                {businessRuleResult.review_required
                  ? 'Yes'
                  : 'No'}
              </strong>
            </div>
          </div>

          {businessRuleResult.passed_rules.length > 0 && (
            <div className="cash-subsection">
              <strong>Passed rules</strong>

              <ul className="cash-passed-list">
                {businessRuleResult.passed_rules.map(
                  (rule, index) => (
                    <li key={`${rule}-${index}`}>
                      <span>✓</span>
                      {rule}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}

          {businessRuleResult.warnings.length > 0 && (
            <div className="cash-subsection">
              <strong>Warnings</strong>

              <ul className="cash-warning-list">
                {businessRuleResult.warnings.map(
                  (warning, index) => (
                    <li key={`${warning}-${index}`}>
                      <span>!</span>
                      {warning}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="cash-empty-state">
          No business-rule details were returned.
        </p>
      )}

      {historicalBehavior && (
        <div className="cash-history-section">
          <div className="cash-subsection-heading">
            <strong>Historical behavior</strong>
            <span>
              {historicalBehavior.confidence_level} confidence
            </span>
          </div>

          <dl className="cash-history-list">
            <div>
              <dt>Payment groups sampled</dt>
              <dd>{historicalBehavior.sample_size}</dd>
            </div>

            <div>
              <dt>Multi-invoice ratio</dt>
              <dd>
                {formatPercent(
                  historicalBehavior.multiple_payment_ratio,
                )}
              </dd>
            </div>

            <div>
              <dt>Average group size</dt>
              <dd>
                {historicalBehavior.average_invoice_group_size.toFixed(
                  2,
                )}
              </dd>
            </div>

            <div>
              <dt>Largest group</dt>
              <dd>
                {
                  historicalBehavior.largest_invoice_group_size
                }{' '}
                invoices
              </dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  )
}

export default BusinessRulesPanel