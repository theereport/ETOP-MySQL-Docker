type DecisionTraceProps = {
  trace: string[]
}

function DecisionTrace({
  trace,
}: DecisionTraceProps) {
  return (
    <section className="cash-panel-card cash-trace-card">
      <div className="cash-panel-heading">
        <div>
          <strong>Decision trace</strong>
          <span>
            Auditable sequence used to reach the recommendation
          </span>
        </div>

        <span className="cash-panel-icon">◎</span>
      </div>

      {trace.length > 0 ? (
        <ol className="cash-trace-list">
          {trace.map((step, index) => (
            <li key={`${step}-${index}`}>
              <div className="cash-trace-number">
                {index + 1}
              </div>

              <div>
                <strong>
                  {index === trace.length - 1
                    ? 'Final decision'
                    : `Evaluation step ${index + 1}`}
                </strong>

                <p>{step}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="cash-empty-state">
          No decision trace was returned.
        </p>
      )}
    </section>
  )
}

export default DecisionTrace