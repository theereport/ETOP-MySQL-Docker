import type { ScoreComponent } from './CashApplication'

type ScoreBreakdownProps = {
  scoreComponents: ScoreComponent[]
  finalScore: number
}

function ScoreBreakdown({
  scoreComponents,
  finalScore,
}: ScoreBreakdownProps) {
  return (
    <section className="cash-panel-card">
      <div className="cash-panel-heading">
        <div>
          <strong>Score breakdown</strong>
          <span>
            Individual decision-rule contributions
          </span>
        </div>

        <div className="cash-final-score">
          {Math.round(finalScore)}
        </div>
      </div>

      {scoreComponents.length > 0 ? (
        <div className="cash-score-list">
          {scoreComponents.map((component) => (
            <div
              className="cash-score-row"
              key={component.rule_code}
            >
              <div
                className={
                  component.passed
                    ? 'cash-rule-result passed'
                    : 'cash-rule-result failed'
                }
              >
                {component.passed ? '✓' : '×'}
              </div>

              <div className="cash-score-copy">
                <strong>{component.rule_name}</strong>
                <p>{component.explanation}</p>
                <small>{component.rule_code}</small>
              </div>

              <span
                className={
                  component.score_adjustment > 0
                    ? 'cash-score-adjustment positive'
                    : component.score_adjustment < 0
                      ? 'cash-score-adjustment negative'
                      : 'cash-score-adjustment'
                }
              >
                {component.score_adjustment > 0
                  ? '+'
                  : ''}
                {component.score_adjustment}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="cash-empty-state">
          No score components were returned.
        </p>
      )}
    </section>
  )
}

export default ScoreBreakdown