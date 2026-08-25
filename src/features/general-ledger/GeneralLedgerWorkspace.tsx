import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createAccountNote,
  getAccountBalances,
  getAccountEvidence,
  getAccountNotes,
  getAccountTransactions,
  getTemplateDetail,
  listTemplates,
  searchAccounts,
} from './api'
import type {
  AccountBalanceEvidence,
  AccountEvidenceResponse,
  AccountSearchResult,
  GLNoteHistoryResponse,
  StandardJournalEntryTemplateDetail,
  StandardJournalEntryTemplateSummary,
  TransactionEvidence,
} from './types'
import './GeneralLedgerWorkspace.css'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatMoney(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : money.format(value)
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleDateString('en-US', { dateStyle: 'medium' })
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

type SelectedAccount = {
  accountNumber: number
  division: number
  department: number
}

type DetailError = { key: string; message: string }

const currentYear = new Date().getFullYear()

function accountKey(account: SelectedAccount): string {
  return `${account.accountNumber}-${account.division}-${account.department}`
}

export default function GeneralLedgerWorkspace() {
  const [view, setView] = useState<'accounts' | 'templates'>('accounts')

  // --- Chart of accounts search -------------------------------------
  const [query, setQuery] = useState('')
  const [activeOnly, setActiveOnly] = useState(true)
  const [results, setResults] = useState<AccountSearchResult[]>([])
  const [searchError, setSearchError] = useState('')

  const [selectedAccount, setSelectedAccount] = useState<SelectedAccount | null>(null)
  const [evidence, setEvidence] = useState<AccountEvidenceResponse | null>(null)
  const [notes, setNotes] = useState<GLNoteHistoryResponse | null>(null)
  const [detailError, setDetailError] = useState<DetailError | null>(null)

  // --- Balances --------------------------------------------------------
  const [yearFrom, setYearFrom] = useState(currentYear)
  const [periodFrom, setPeriodFrom] = useState(1)
  const [yearTo, setYearTo] = useState(currentYear)
  const [periodTo, setPeriodTo] = useState(13)
  const [balances, setBalances] = useState<AccountBalanceEvidence | null>(null)
  const [balanceError, setBalanceError] = useState('')
  const [balanceLoading, setBalanceLoading] = useState(false)

  // --- Transactions ------------------------------------------------------
  const [txYear, setTxYear] = useState(currentYear)
  const [txPeriod, setTxPeriod] = useState(1)
  const [transactions, setTransactions] = useState<TransactionEvidence | null>(null)
  const [txError, setTxError] = useState('')
  const [txLoading, setTxLoading] = useState(false)

  // --- Notes ---------------------------------------------------------
  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [notePeriod, setNotePeriod] = useState('')
  const [noteYear, setNoteYear] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  // --- Templates -------------------------------------------------------
  const [templateQuery, setTemplateQuery] = useState('')
  const [templates, setTemplates] = useState<StandardJournalEntryTemplateSummary[]>([])
  const [templateError, setTemplateError] = useState('')
  const [selectedTemplateName, setSelectedTemplateName] = useState<string | null>(null)
  const [templateDetail, setTemplateDetail] = useState<StandardJournalEntryTemplateDetail | null>(null)
  const [templateDetailError, setTemplateDetailError] = useState('')

  const selectedKey = selectedAccount ? accountKey(selectedAccount) : null
  const currentEvidence =
    evidence && selectedAccount && evidence.identity.account_number === selectedAccount.accountNumber
      ? evidence
      : null
  const currentDetailError =
    detailError && detailError.key === selectedKey ? detailError.message : ''
  const isLoadingDetail = selectedAccount != null && !currentEvidence && !currentDetailError

  useEffect(() => {
    if (view !== 'accounts') return
    const controller = new AbortController()
    searchAccounts(query, activeOnly, controller.signal)
      .then((response) => {
        setResults(response.accounts)
        setSearchError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setSearchError(errorMessage(error, 'Unable to search accounts.'))
      })
    return () => controller.abort()
  }, [query, activeOnly, view])

  useEffect(() => {
    if (!selectedAccount) return
    const controller = new AbortController()
    const account = selectedAccount
    Promise.all([
      getAccountEvidence(account.accountNumber, account.division, account.department, controller.signal),
      getAccountNotes(account.accountNumber, controller.signal),
    ])
      .then(([evidenceResponse, notesResponse]) => {
        setEvidence(evidenceResponse)
        setNotes(notesResponse)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setDetailError({
          key: accountKey(account),
          message: errorMessage(error, 'Unable to load account evidence.'),
        })
      })
    setBalances(null)
    setTransactions(null)
    return () => controller.abort()
  }, [selectedAccount])

  useEffect(() => {
    if (view === 'templates') {
      const controller = new AbortController()
      listTemplates(templateQuery, controller.signal)
        .then((response) => {
          setTemplates(response.templates)
          setTemplateError('')
        })
        .catch((error: unknown) => {
          if (isAbortError(error)) return
          setTemplateError(errorMessage(error, 'Unable to load templates.'))
        })
      return () => controller.abort()
    }
    return undefined
  }, [view, templateQuery])

  useEffect(() => {
    if (!selectedTemplateName) {
      setTemplateDetail(null)
      return undefined
    }
    const controller = new AbortController()
    getTemplateDetail(selectedTemplateName, controller.signal)
      .then((detail) => {
        setTemplateDetail(detail)
        setTemplateDetailError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setTemplateDetailError(errorMessage(error, 'Unable to load the template.'))
      })
    return () => controller.abort()
  }, [selectedTemplateName])

  async function loadBalances(event: FormEvent) {
    event.preventDefault()
    if (!selectedAccount) return
    setBalanceLoading(true)
    setBalanceError('')
    try {
      const response = await getAccountBalances(
        selectedAccount.accountNumber,
        selectedAccount.division,
        selectedAccount.department,
        yearFrom,
        periodFrom,
        yearTo,
        periodTo,
      )
      setBalances(response)
    } catch (error) {
      setBalanceError(errorMessage(error, 'Unable to load balances.'))
    } finally {
      setBalanceLoading(false)
    }
  }

  async function loadTransactions(event: FormEvent) {
    event.preventDefault()
    if (!selectedAccount) return
    setTxLoading(true)
    setTxError('')
    try {
      const response = await getAccountTransactions(
        selectedAccount.accountNumber,
        selectedAccount.division,
        selectedAccount.department,
        txYear,
        txPeriod,
      )
      setTransactions(response)
    } catch (error) {
      setTxError(errorMessage(error, 'Unable to load transactions.'))
    } finally {
      setTxLoading(false)
    }
  }

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (!selectedAccount) return
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createAccountNote(selectedAccount.accountNumber, {
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
        division: selectedAccount.division,
        department: selectedAccount.department,
        period: notePeriod.trim() ? Number(notePeriod) : null,
        year: noteYear.trim() ? Number(noteYear) : null,
      })
      const refreshed = await getAccountNotes(selectedAccount.accountNumber)
      setNotes(refreshed)
      setNoteText('')
      setNotePeriod('')
      setNoteYear('')
      setNoteSaveStatus('success')
      setNoteSaveMessage('Note saved. It is append-only and creates no ERP change.')
    } catch (error) {
      setNoteSaveStatus('error')
      setNoteSaveMessage(errorMessage(error, 'Unable to save the note.'))
    }
  }

  const balanceRows = useMemo(() => balances?.balances ?? [], [balances])

  return (
    <section className="gl-shell">
      <header className="gl-header">
        <div>
          <span className="gl-kicker">Read-only MaddenCo evidence</span>
          <h2>General Ledger</h2>
          <p>Chart of accounts, period balances, and posted transaction evidence — no automatic balance verdict or ERP write.</p>
        </div>
        <div className="gl-view-toggle">
          <button type="button" className={view === 'accounts' ? 'active' : ''} onClick={() => setView('accounts')}>
            Chart of accounts
          </button>
          <button type="button" className={view === 'templates' ? 'active' : ''} onClick={() => setView('templates')}>
            Standard JE templates
          </button>
        </div>
      </header>

      {view === 'accounts' && (
        <div className="gl-layout">
          <div className="gl-results">
            <label className="gl-search">
              Search accounts
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Account number, name, or short name"
              />
            </label>
            <label className="gl-checkbox">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(event) => setActiveOnly(event.target.checked)}
              />
              Active accounts only
            </label>
            {searchError && <p className="gl-error">{searchError}</p>}
            {results.length === 0 ? (
              <p className="gl-empty">No accounts matched.</p>
            ) : (
              <ul className="gl-result-list">
                {results.map((account) => {
                  const key = accountKey({
                    accountNumber: account.account_number,
                    division: account.division,
                    department: account.department,
                  })
                  return (
                    <li key={key}>
                      <button
                        type="button"
                        className={key === selectedKey ? 'gl-result gl-result--active' : 'gl-result'}
                        onClick={() =>
                          setSelectedAccount({
                            accountNumber: account.account_number,
                            division: account.division,
                            department: account.department,
                          })
                        }
                      >
                        <strong>{account.description || 'Unnamed account'}</strong>
                        <span>
                          #{account.account_number} · Div {account.division} · Dept {account.department} ·{' '}
                          {account.debit_or_credit || 'Unavailable'}
                        </span>
                        {!account.active && <em className="gl-tag gl-tag--inactive">Inactive</em>}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="gl-detail">
            {selectedAccount == null && (
              <div className="gl-empty-state">
                <strong>Select an account to view evidence.</strong>
              </div>
            )}

            {isLoadingDetail && (
              <div className="gl-loading"><span className="gl-spinner" /> Loading account evidence…</div>
            )}

            {selectedAccount != null && currentDetailError && (
              <div className="gl-message gl-message--error">
                <strong>Account evidence is unavailable.</strong>
                <span>{currentDetailError}</span>
              </div>
            )}

            {currentEvidence && (
              <div className="gl-evidence">
                <div className="gl-identity-card">
                  <div>
                    <h3>{currentEvidence.identity.description}</h3>
                    <span>
                      Account #{currentEvidence.identity.account_number} · Div {currentEvidence.identity.division} ·
                      Dept {currentEvidence.identity.department} · {currentEvidence.identity.active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <dl>
                    <div><dt>Short name</dt><dd>{currentEvidence.identity.short_name || 'Unavailable'}</dd></div>
                    <div><dt>Normal side</dt><dd>{currentEvidence.identity.debit_or_credit || 'Unavailable'}</dd></div>
                    <div><dt>Account type</dt><dd>{currentEvidence.identity.account_type || 'Unavailable'}</dd></div>
                    <div><dt>Company #</dt><dd>{currentEvidence.identity.company_number ?? 'Unavailable'}</dd></div>
                    <div><dt>Requires customer</dt><dd>{currentEvidence.identity.requires_customer ? 'Yes' : 'No'}</dd></div>
                    <div><dt>Requires employee</dt><dd>{currentEvidence.identity.requires_employee ? 'Yes' : 'No'}</dd></div>
                    <div><dt>Requires job</dt><dd>{currentEvidence.identity.requires_job ? 'Yes' : 'No'}</dd></div>
                    <div><dt>Requires PO</dt><dd>{currentEvidence.identity.requires_po ? 'Yes' : 'No'}</dd></div>
                    <div><dt>Created</dt><dd>{formatDate(currentEvidence.identity.date_created)} {currentEvidence.identity.created_by && `(${currentEvidence.identity.created_by})`}</dd></div>
                    <div><dt>Last changed</dt><dd>{formatDate(currentEvidence.identity.date_changed)} {currentEvidence.identity.changed_by && `(${currentEvidence.identity.changed_by})`}</dd></div>
                  </dl>
                </div>

                <div className="gl-section">
                  <h4>Period balances</h4>
                  <p className="gl-section-note">GMBL.GBAMT (G/L Net Balance) per period/year, exactly as MaddenCo recorded it.</p>
                  <form className="gl-range-form" onSubmit={loadBalances}>
                    <label>Year from<input type="number" value={yearFrom} onChange={(event) => setYearFrom(Number(event.target.value))} /></label>
                    <label>Period from<input type="number" min={0} max={13} value={periodFrom} onChange={(event) => setPeriodFrom(Number(event.target.value))} /></label>
                    <label>Year to<input type="number" value={yearTo} onChange={(event) => setYearTo(Number(event.target.value))} /></label>
                    <label>Period to<input type="number" min={0} max={13} value={periodTo} onChange={(event) => setPeriodTo(Number(event.target.value))} /></label>
                    <button type="submit" disabled={balanceLoading}>{balanceLoading ? 'Loading…' : 'Load balances'}</button>
                  </form>
                  {balanceError && <p className="gl-error">{balanceError}</p>}
                  {balanceRows.length > 0 && (
                    <div className="gl-table-wrap">
                      <table className="gl-table">
                        <thead><tr><th>Year</th><th>Period</th><th>Net balance</th></tr></thead>
                        <tbody>
                          {balanceRows.map((row) => (
                            <tr key={`${row.year}-${row.period}`}>
                              <td>{row.year}</td>
                              <td>{row.period}</td>
                              <td>{formatMoney(row.net_balance)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div className="gl-section">
                  <h4>Posted transactions</h4>
                  <p className="gl-section-note">
                    GMAD posted detail for one year/period, left joined to GTJT (actual journal entry totals) where
                    GANBREF=GJHNBREF and period/year match.
                  </p>
                  <form className="gl-range-form" onSubmit={loadTransactions}>
                    <label>Year<input type="number" value={txYear} onChange={(event) => setTxYear(Number(event.target.value))} /></label>
                    <label>Period<input type="number" min={0} max={13} value={txPeriod} onChange={(event) => setTxPeriod(Number(event.target.value))} /></label>
                    <button type="submit" disabled={txLoading}>{txLoading ? 'Loading…' : 'Load transactions'}</button>
                  </form>
                  {txError && <p className="gl-error">{txError}</p>}

                  {transactions && (
                    <>
                      <div className="gl-recon-card">
                        <strong>Reconciliation check ({transactions.year} / period {transactions.period})</strong>
                        <p className="gl-section-note">{transactions.reconciliation.formula}</p>
                        <dl>
                          <div><dt>Posted debit total</dt><dd>{formatMoney(transactions.reconciliation.posted_debit_total)}</dd></div>
                          <div><dt>Posted credit total</dt><dd>{formatMoney(transactions.reconciliation.posted_credit_total)}</dd></div>
                          <div><dt>Posted net total</dt><dd>{formatMoney(transactions.reconciliation.posted_net_total)}</dd></div>
                          <div><dt>GMBL period balance</dt><dd>{formatMoney(transactions.reconciliation.period_balance)}</dd></div>
                          <div><dt>Difference</dt><dd>{formatMoney(transactions.reconciliation.difference)}</dd></div>
                        </dl>
                      </div>

                      {transactions.transactions.length === 0 ? (
                        <p className="gl-empty">No posted transactions for this account/period.</p>
                      ) : (
                        <div className="gl-table-wrap">
                          <table className="gl-table">
                            <thead>
                              <tr>
                                <th>Seq</th><th>Amount</th><th>DB/CR</th><th>System</th><th>Description</th>
                                <th>Posted</th><th>Matched JE total</th>
                              </tr>
                            </thead>
                            <tbody>
                              {transactions.transactions.map((line) => (
                                <tr key={line.sequence}>
                                  <td>{line.sequence}</td>
                                  <td>{formatMoney(line.amount)}</td>
                                  <td>{line.debit_or_credit}</td>
                                  <td>{line.system_source || 'Unavailable'}</td>
                                  <td>{line.description || 'Unavailable'}</td>
                                  <td>{formatDate(line.date_posted)}</td>
                                  <td>
                                    {line.matched_journal_entry
                                      ? `DB ${formatMoney(line.matched_journal_entry.total_debit)} / CR ${formatMoney(line.matched_journal_entry.total_credit)}`
                                      : 'No matching GTJT header'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      <div className="gl-unposted">
                        <strong>Unposted journal entry lines (GTJD)</strong>
                        <p className="gl-section-note">{transactions.unposted_explanation}</p>
                        {transactions.unposted_journal_entry_lines.length === 0 ? (
                          <p className="gl-empty">None currently in progress for this account.</p>
                        ) : (
                          <div className="gl-table-wrap">
                            <table className="gl-table">
                              <thead><tr><th>Ref #</th><th>Seq</th><th>Debit</th><th>Credit</th><th>Description</th></tr></thead>
                              <tbody>
                                {transactions.unposted_journal_entry_lines.map((line) => (
                                  <tr key={`${line.reference_number}-${line.sequence}`}>
                                    <td>{line.reference_number}</td>
                                    <td>{line.sequence}</td>
                                    <td>{formatMoney(line.debit_amount)}</td>
                                    <td>{formatMoney(line.credit_amount)}</td>
                                    <td>{line.description || 'Unavailable'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>

                <div className="gl-gaps">
                  <strong>What this evidence does not include</strong>
                  <ul>
                    {currentEvidence.gaps.map((gap) => (
                      <li key={gap.code}><strong>{gap.label}:</strong> {gap.explanation}</li>
                    ))}
                  </ul>
                </div>

                <div className="gl-notes">
                  <h4>Reconciliation notes</h4>
                  <p className="gl-section-note">Append-only. A note creates no ERP change, approval, or recommendation.</p>
                  <form className="gl-note-form" onSubmit={submitNote}>
                    <label>Your name<input value={authorIdentity} onChange={(event) => setAuthorIdentity(event.target.value)} placeholder="Name" /></label>
                    <div className="gl-note-scope">
                      <label>Period (optional)<input type="number" min={0} max={13} value={notePeriod} onChange={(event) => setNotePeriod(event.target.value)} /></label>
                      <label>Year (optional)<input type="number" value={noteYear} onChange={(event) => setNoteYear(event.target.value)} /></label>
                    </div>
                    <label>Note<textarea rows={3} value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="What did you observe or confirm about this account?" /></label>
                    <button type="submit" disabled={noteSaveStatus === 'saving'}>{noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}</button>
                    {noteSaveMessage && (
                      <p className={noteSaveStatus === 'error' ? 'gl-form-error' : 'gl-form-success'}>{noteSaveMessage}</p>
                    )}
                  </form>
                  {notes && notes.count > 0 && (
                    <ul className="gl-note-list">
                      {notes.notes.map((note) => (
                        <li key={note.note_id}>
                          <div>
                            <strong>{note.author_identity}</strong>
                            <span>
                              {formatDateTime(note.created_at)}
                              {note.period != null && note.year != null && ` · Period ${note.period}/${note.year}`}
                            </span>
                          </div>
                          <p>{note.note}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {view === 'templates' && (
        <div className="gl-layout">
          <div className="gl-results">
            <label className="gl-search">
              Search templates
              <input
                type="search"
                value={templateQuery}
                onChange={(event) => setTemplateQuery(event.target.value)}
                placeholder="Template name or description"
              />
            </label>
            {templateError && <p className="gl-error">{templateError}</p>}
            {templates.length === 0 ? (
              <p className="gl-empty">No templates matched.</p>
            ) : (
              <ul className="gl-result-list">
                {templates.map((template) => (
                  <li key={template.name}>
                    <button
                      type="button"
                      className={template.name === selectedTemplateName ? 'gl-result gl-result--active' : 'gl-result'}
                      onClick={() => setSelectedTemplateName(template.name)}
                    >
                      <strong>{template.description || template.name}</strong>
                      <span>{template.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="gl-detail">
            {selectedTemplateName == null && (
              <div className="gl-empty-state">
                <strong>Select a template to view its lines.</strong>
              </div>
            )}
            {templateDetailError && (
              <div className="gl-message gl-message--error">
                <strong>Template is unavailable.</strong>
                <span>{templateDetailError}</span>
              </div>
            )}
            {templateDetail && (
              <div className="gl-evidence">
                <div className="gl-identity-card">
                  <div>
                    <h3>{templateDetail.description || templateDetail.name}</h3>
                    <span>Template {templateDetail.name} · Reference template, not an actual posting</span>
                  </div>
                  <dl>
                    <div><dt>JE description</dt><dd>{templateDetail.je_description || 'Unavailable'}</dd></div>
                    <div><dt>Status</dt><dd>{templateDetail.status_code || 'Unavailable'}</dd></div>
                    <div><dt>Created by</dt><dd>{templateDetail.created_by || 'Unavailable'}</dd></div>
                    <div><dt>Last changed by</dt><dd>{templateDetail.last_changed_by || 'Unavailable'}</dd></div>
                  </dl>
                </div>
                <div className="gl-section">
                  <h4>Template lines</h4>
                  <p className="gl-section-note">{templateDetail.explanation}</p>
                  <div className="gl-table-wrap">
                    <table className="gl-table">
                      <thead><tr><th>Seq</th><th>Account</th><th>Div</th><th>Dept</th><th>Debit</th><th>Credit</th><th>Description</th></tr></thead>
                      <tbody>
                        {templateDetail.lines.map((line) => (
                          <tr key={line.sequence}>
                            <td>{line.sequence}</td>
                            <td>{line.account_number}</td>
                            <td>{line.division}</td>
                            <td>{line.department}</td>
                            <td>{formatMoney(line.debit_amount)}</td>
                            <td>{formatMoney(line.credit_amount)}</td>
                            <td>{line.description || 'Unavailable'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="gl-total">
                      Line totals: debit {formatMoney(templateDetail.line_debit_total)} / credit {formatMoney(templateDetail.line_credit_total)}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
