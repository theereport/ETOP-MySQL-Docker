import type { ReportParameter } from './ReportBuilder'

type ReportFiltersProps = {
  parameters: ReportParameter[]
  values: Record<string, string>
  onChange: (
    values: Record<string, string>,
  ) => void
}

function ReportFilters({
  parameters,
  values,
  onChange,
}: ReportFiltersProps) {
  const setValue = (
    name: string,
    value: string,
  ) => {
    onChange({
      ...values,
      [name]: value,
    })
  }

  return (
    <section className="report-panel-card">
      <div className="report-panel-heading">
        <div>
          <strong>Parameters</strong>

          <span>
            Values supplied before preview or export.
          </span>
        </div>

        <span className="report-panel-count">
          {parameters.length}
        </span>
      </div>

      {parameters.length === 0 ? (
        <div className="report-empty-state">
          This report does not require any parameters.
        </div>
      ) : (
        <div className="report-filter-list">
          {parameters.map((parameter) => (
            <label
              key={parameter.id}
              className="report-filter-field"
            >
              <span>
                {parameter.label}

                {parameter.required && (
                  <strong>*</strong>
                )}
              </span>

              {parameter.type === 'text' && (
                <input
                  type="text"
                  value={
                    values[parameter.name] ?? ''
                  }
                  placeholder={
                    parameter.placeholder
                  }
                  onChange={(event) =>
                    setValue(
                      parameter.name,
                      event.target.value,
                    )
                  }
                />
              )}

              {parameter.type === 'number' && (
                <input
                  type="number"
                  value={
                    values[parameter.name] ?? ''
                  }
                  onChange={(event) =>
                    setValue(
                      parameter.name,
                      event.target.value,
                    )
                  }
                />
              )}

              {parameter.type === 'date' && (
                <input
                  type="date"
                  value={
                    values[parameter.name] ?? ''
                  }
                  onChange={(event) =>
                    setValue(
                      parameter.name,
                      event.target.value,
                    )
                  }
                />
              )}

              {parameter.type === 'boolean' && (
                <select
                  value={
                    values[parameter.name] ?? ''
                  }
                  onChange={(event) =>
                    setValue(
                      parameter.name,
                      event.target.value,
                    )
                  }
                >
                  <option value="">
                    Select...
                  </option>

                  <option value="true">
                    Yes
                  </option>

                  <option value="false">
                    No
                  </option>
                </select>
              )}

              {parameter.type === 'select' && (
                <select
                  value={
                    values[parameter.name] ?? ''
                  }
                  onChange={(event) =>
                    setValue(
                      parameter.name,
                      event.target.value,
                    )
                  }
                >
                  <option value="">
                    Select...
                  </option>

                  {parameter.options?.map(
                    (option) => (
                      <option
                        key={option.value}
                        value={option.value}
                      >
                        {option.label}
                      </option>
                    ),
                  )}
                </select>
              )}
            </label>
          ))}
        </div>
      )}
    </section>
  )
}

export default ReportFilters