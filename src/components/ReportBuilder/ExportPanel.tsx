type ExportPanelProps = {
  reportName: string
  isExporting: boolean
  canExport: boolean
  maximumRows: number | null
  onExport: () => void
}

function ExportPanel({
  reportName,
  isExporting,
  canExport,
  maximumRows,
  onExport,
}: ExportPanelProps) {
  return (
    <section className="report-panel-card">
      <div className="report-panel-heading">
        <div>
          <strong>Controlled export</strong>
          <span>
            Download through the existing read-only SQL export service.
          </span>
        </div>

        <span className="report-panel-icon">⇩</span>
      </div>

      <div className="report-export-summary">
        <span>Report</span>
        <strong>{reportName.trim() || 'Untitled Report'}</strong>
      </div>

      <div className="report-export-notice">
        {maximumRows
          ? `Direct CSV exports are capped at the server limit of ${maximumRows.toLocaleString()} rows.`
          : 'Connect to the read-only ERP reporting service before exporting.'}
      </div>

      <div className="report-export-options">
        <button
          type="button"
          className="report-export-option"
          onClick={onExport}
          disabled={!canExport || isExporting}
        >
          <div className="report-export-option-icon">CSV</div>
          <div>
            <strong>Download CSV</strong>
            <span>
              Uses the currently supported backend export route and its
              configured row limit.
            </span>
          </div>
        </button>

        <div className="report-export-option report-export-option-unavailable">
          <div className="report-export-option-icon">XLSX</div>
          <div>
            <strong>Direct Excel unavailable</strong>
            <span>
              The current direct export API produces CSV only. Excel remains
              available for scheduled saved reports.
            </span>
          </div>
        </div>
      </div>

      {isExporting && (
        <div className="report-export-progress" role="status">
          <div className="report-export-spinner" />
          <div>
            <strong>Building CSV export</strong>
            <span>The server is processing the controlled result set.</span>
          </div>
        </div>
      )}
    </section>
  )
}

export default ExportPanel
