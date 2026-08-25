import { ApiError, requestJson } from '../../api/client'
import type {
  AccountBalanceEvidence,
  AccountEvidenceResponse,
  AccountSearchResponse,
  CreateGLNoteRequest,
  GLNoteHistoryResponse,
  GLNoteRecord,
  StandardJournalEntryTemplateDetail,
  StandardJournalEntryTemplateResponse,
  TransactionEvidence,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function generalLedgerRequest<T>(
  path: string,
  options: Parameters<typeof requestJson<T>>[1] = {},
): Promise<T> {
  try {
    return await requestJson<T>(path, options)
  } catch (error) {
    if (error instanceof ApiError && isRecord(error.details)) {
      const detail = error.details.detail
      if (isRecord(detail) && typeof detail.message === 'string') {
        throw new ApiError(detail.message, error.status, detail)
      }
    }
    throw error
  }
}

export function searchAccounts(
  search: string,
  activeOnly: boolean,
  signal?: AbortSignal,
): Promise<AccountSearchResponse> {
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  params.set('active_only', String(activeOnly))
  return generalLedgerRequest<AccountSearchResponse>(
    `/general-ledger/accounts/search?${params.toString()}`,
    { signal },
  )
}

export function getAccountEvidence(
  accountNumber: number | string,
  division: number,
  department: number,
  signal?: AbortSignal,
): Promise<AccountEvidenceResponse> {
  const account = encodeURIComponent(String(accountNumber))
  const params = new URLSearchParams({
    division: String(division),
    department: String(department),
  })
  return generalLedgerRequest<AccountEvidenceResponse>(
    `/general-ledger/accounts/${account}?${params.toString()}`,
    { signal },
  )
}

export function getAccountBalances(
  accountNumber: number | string,
  division: number,
  department: number,
  yearFrom: number,
  periodFrom: number,
  yearTo: number,
  periodTo: number,
  signal?: AbortSignal,
): Promise<AccountBalanceEvidence> {
  const account = encodeURIComponent(String(accountNumber))
  const params = new URLSearchParams({
    division: String(division),
    department: String(department),
    year_from: String(yearFrom),
    period_from: String(periodFrom),
    year_to: String(yearTo),
    period_to: String(periodTo),
  })
  return generalLedgerRequest<AccountBalanceEvidence>(
    `/general-ledger/accounts/${account}/balances?${params.toString()}`,
    { signal },
  )
}

export function getAccountTransactions(
  accountNumber: number | string,
  division: number,
  department: number,
  year: number,
  period: number,
  signal?: AbortSignal,
): Promise<TransactionEvidence> {
  const account = encodeURIComponent(String(accountNumber))
  const params = new URLSearchParams({
    division: String(division),
    department: String(department),
    year: String(year),
    period: String(period),
  })
  return generalLedgerRequest<TransactionEvidence>(
    `/general-ledger/accounts/${account}/transactions?${params.toString()}`,
    { signal },
  )
}

export function getAccountNotes(
  accountNumber: number | string,
  signal?: AbortSignal,
): Promise<GLNoteHistoryResponse> {
  const account = encodeURIComponent(String(accountNumber))
  return generalLedgerRequest<GLNoteHistoryResponse>(
    `/general-ledger/accounts/${account}/notes`,
    { signal },
  )
}

export function createAccountNote(
  accountNumber: number | string,
  payload: CreateGLNoteRequest,
  signal?: AbortSignal,
): Promise<GLNoteRecord> {
  const account = encodeURIComponent(String(accountNumber))
  return generalLedgerRequest<GLNoteRecord>(
    `/general-ledger/accounts/${account}/notes`,
    { method: 'POST', body: payload, signal },
  )
}

export function listTemplates(
  search: string,
  signal?: AbortSignal,
): Promise<StandardJournalEntryTemplateResponse> {
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  return generalLedgerRequest<StandardJournalEntryTemplateResponse>(
    `/general-ledger/templates?${params.toString()}`,
    { signal },
  )
}

export function getTemplateDetail(
  name: string,
  signal?: AbortSignal,
): Promise<StandardJournalEntryTemplateDetail> {
  const templateName = encodeURIComponent(name)
  return generalLedgerRequest<StandardJournalEntryTemplateDetail>(
    `/general-ledger/templates/${templateName}`,
    { signal },
  )
}
