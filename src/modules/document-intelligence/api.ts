import type {
  DocumentHealth,
  DocumentJob,
  DocumentJobListResponse,
  DocumentParser,
  DocumentResult,
  DocumentReviewResponse,
  SaveDocumentReviewRequest,
  GenerateLearningExamplesResponse,
  LearningExampleListResponse,
  LearningSummaryResponse,
  LockboxProcessingResult,
  TrainingSession,
  TrainingSummary,
  LockboxReviewResult,
  SaveLockboxTransactionReviewRequest,
  AppendLockboxCustomerNoteRequest,
  LockboxCustomerNoteList,
  CustomerMatchRequest,
  CustomerMatchResponse,
  BulkInvoiceOwnerResponse,
  LinkedCustomerAccountsResponse,
  DurableLockboxPreparation,
} from './types'

const API_BASE =
  'http://127.0.0.1:8000/api/v1/documents'
const PLATFORM_API_BASE =
  'http://127.0.0.1:8000/api/v1'

async function readError(
  response: Response,
): Promise<string> {
  const payload = await response
    .json()
    .catch(() => null)

  return (
    payload?.detail ??
    payload?.message ??
    `Request failed with status ${response.status}.`
  )
}

export async function getDocumentHealth(
  signal?: AbortSignal,
): Promise<DocumentHealth> {
  const response = await fetch(
    `${API_BASE}/health`,
    { signal },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}

export async function getDocumentParsers(
  signal?: AbortSignal,
): Promise<DocumentParser[]> {
  const response = await fetch(
    `${API_BASE}/parsers`,
    { signal },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  const payload = await response.json()

  return payload.parsers ?? []
}

export async function getDocumentJobs(
  limit = 100,
  signal?: AbortSignal,
): Promise<DocumentJob[]> {
  const response = await fetch(
    `${API_BASE}/jobs?limit=${limit}`,
    { signal },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  const payload = await response.json()

  return payload.jobs ?? []
}

export async function deleteDocumentJob(
  jobId: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}`,
    { method: 'DELETE' },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }
}

export async function getVendorInvoiceJobs(
  limit = 1,
  offset = 0,
  signal?: AbortSignal,
): Promise<DocumentJobListResponse> {
  const response = await fetch(
    `${API_BASE}/vendor-invoices/jobs?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`,
    { signal },
  )

  if (!response.ok) {
    throw new Error(await readError(response))
  }

  const payload = await response.json()
  return {
    jobs: payload.jobs ?? [],
    total: Number(payload.total ?? 0),
    limit: Number(payload.limit ?? limit),
    offset: Number(payload.offset ?? offset),
  }
}

export async function uploadDocument(
  file: File,
): Promise<DocumentJob> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_BASE}/upload`,
    {
      method: 'POST',
      body: formData,
    },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}

export async function processDocument(
  jobId: string,
): Promise<DocumentResult> {
  const response = await fetch(
    `${API_BASE}/jobs/${jobId}/process`,
    {
      method: 'POST',
    },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}

export async function getDocumentResult(
  jobId: string,
): Promise<DocumentResult> {
  const response = await fetch(
    `${API_BASE}/jobs/${jobId}/result`,
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}


export function getDocumentFileUrl(
  jobId: string,
): string {
  return `${API_BASE}/jobs/${encodeURIComponent(jobId)}/file`
}

export async function getDocumentFile(
  jobId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(
    getDocumentFileUrl(jobId),
    { signal },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.blob()
}


export async function getDocumentReview(
  jobId: string,
  signal?: AbortSignal,
): Promise<DocumentReviewResponse> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/review`,
    { signal },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}

export async function saveDocumentReview(
  jobId: string,
  payload: SaveDocumentReviewRequest,
): Promise<DocumentReviewResponse> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/review`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}

export async function getLearningSummary(signal?:AbortSignal):Promise<LearningSummaryResponse>{const r=await fetch(`${API_BASE}/learning/summary`,{signal});if(!r.ok)throw new Error(await readError(r));return r.json()}
export async function getLearningExamples(limit=100,signal?:AbortSignal):Promise<LearningExampleListResponse>{const r=await fetch(`${API_BASE}/learning/examples?limit=${encodeURIComponent(limit)}`,{signal});if(!r.ok)throw new Error(await readError(r));return r.json()}
export async function generateLearningExamples(jobId:string):Promise<GenerateLearningExamplesResponse>{const r=await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}/learning`,{method:'POST'});if(!r.ok)throw new Error(await readError(r));return r.json()}


export async function processLockboxJob(
  jobId: string,
): Promise<LockboxProcessingResult> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/process`,
    { method: 'POST' },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}

export async function getLockboxResult(
  jobId: string,
  signal?: AbortSignal,
): Promise<LockboxProcessingResult> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/result`,
    { signal },
  )

  if (!response.ok) {
    throw new Error(
      await readError(response),
    )
  }

  return response.json()
}

export function getLockboxExportUrl(
  jobId: string,
): string {
  return `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/export`
}

async function downloadBlobResponse(
  url: string,
  fallbackFileName: string,
): Promise<void> {
  // Fetched as an authenticated blob (same Bearer-token fetch every other
  // API call uses) rather than pointed at directly with a raw <a href> -
  // a plain anchor navigation can't carry an Authorization header, so it
  // would 401 unless the session cookie fallback happens to apply.
  const response = await fetch(url)
  if (!response.ok) throw new Error(await readError(response))

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') ?? ''
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quotedName = disposition.match(/filename="([^"]+)"/i)?.[1]
  const fileName = encodedName
    ? decodeURIComponent(encodedName)
    : quotedName || fallbackFileName
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  try {
    anchor.href = objectUrl
    anchor.download = fileName
    document.body.appendChild(anchor)
    anchor.click()
  } finally {
    anchor.remove()
    URL.revokeObjectURL(objectUrl)
  }
}

export function downloadLockboxExport(jobId: string): Promise<void> {
  return downloadBlobResponse(
    getLockboxExportUrl(jobId),
    'Lockbox_Parser_Export.xlsx',
  )
}


export async function uploadLockboxGroundTruth(
  jobId: string,
  file: File,
): Promise<TrainingSession> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(
    `${API_BASE}/training/jobs/${encodeURIComponent(jobId)}/ground-truth`,
    { method: 'POST', body: formData },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function getTrainingSessions(
  limit = 100,
  signal?: AbortSignal,
): Promise<TrainingSession[]> {
  const response = await fetch(
    `${API_BASE}/training/sessions?limit=${encodeURIComponent(limit)}`,
    { signal },
  )
  if (!response.ok) throw new Error(await readError(response))
  const payload = await response.json()
  return payload.sessions ?? []
}

export async function getTrainingSummary(
  signal?: AbortSignal,
): Promise<TrainingSummary> {
  const response = await fetch(`${API_BASE}/training/summary`, { signal })
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}


export async function getLockboxReview(
  jobId: string,
  signal?: AbortSignal,
): Promise<LockboxReviewResult> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/review`,
    { signal },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function startDurableLockboxPreparation(
  jobId: string,
  signal?: AbortSignal,
): Promise<DurableLockboxPreparation> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/preparation/start`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal,
    },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function getDurableLockboxPreparation(
  preparationJobId: string,
  includeTransactions = true,
  signal?: AbortSignal,
): Promise<DurableLockboxPreparation> {
  const response = await fetch(
    `${API_BASE}/lockbox/preparation/${encodeURIComponent(preparationJobId)}`
    + `?include_transactions=${includeTransactions ? 'true' : 'false'}`,
    { signal },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function getCurrentDurableLockboxPreparation(
  jobId: string,
  signal?: AbortSignal,
): Promise<DurableLockboxPreparation> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/preparation/current?include_transactions=false`,
    { signal },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function saveLockboxTransactionReview(
  jobId: string,
  transactionId: string,
  payload: SaveLockboxTransactionReviewRequest,
  signal?: AbortSignal,
): Promise<LockboxReviewResult> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/review/${encodeURIComponent(transactionId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function getLockboxCustomerNotes(
  jobId: string,
  transactionId: string,
  signal?: AbortSignal,
): Promise<LockboxCustomerNoteList> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/review/`
    + `${encodeURIComponent(transactionId)}/customer-notes`,
    { signal },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function appendLockboxCustomerNote(
  jobId: string,
  transactionId: string,
  payload: AppendLockboxCustomerNoteRequest,
  signal?: AbortSignal,
): Promise<LockboxCustomerNoteList> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/review/`
    + `${encodeURIComponent(transactionId)}/customer-notes`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export function getReviewedLockboxExportUrl(jobId: string): string {
  return `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/reviewed-export`
}

export function downloadReviewedLockboxExport(jobId: string): Promise<void> {
  return downloadBlobResponse(
    getReviewedLockboxExportUrl(jobId),
    'Lockbox_Reviewed_PNC_Export.xlsx',
  )
}

export type LockboxReviewQueueExportRequest = {
  transaction_ids: string[]
  queue_label: string
  reason_code: string
}

export async function downloadLockboxReviewQueueExport(
  jobId: string,
  payload: LockboxReviewQueueExportRequest,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/lockbox/review-queue-export`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
  if (!response.ok) throw new Error(await readError(response))

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') ?? ''
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quotedName = disposition.match(/filename="([^"]+)"/i)?.[1]
  const fileName = encodedName
    ? decodeURIComponent(encodedName)
    : quotedName || 'Lockbox_Transaction_Review_Queue.xlsx'
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  try {
    anchor.href = url
    anchor.download = fileName
    document.body.appendChild(anchor)
    anchor.click()
  } finally {
    anchor.remove()
    URL.revokeObjectURL(url)
  }
}

export async function resolveLockboxCustomer(
  payload: CustomerMatchRequest,
  signal?: AbortSignal,
): Promise<CustomerMatchResponse> {
  const response = await fetch(
    `${PLATFORM_API_BASE}/customer-match/resolve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function resolveLockboxInvoiceOwners(
  invoiceNumbers: string[],
  signal?: AbortSignal,
): Promise<BulkInvoiceOwnerResponse> {
  const response = await fetch(
    `${PLATFORM_API_BASE}/customer-match/resolve-invoices`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invoice_numbers: invoiceNumbers }),
      signal,
    },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function getLinkedCustomerAccounts(
  customerNumber: string,
  signal?: AbortSignal,
): Promise<LinkedCustomerAccountsResponse> {
  const response = await fetch(
    `${PLATFORM_API_BASE}/customer-match/linked-customers/`
    + `${encodeURIComponent(customerNumber)}`,
    { signal },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function linkCustomerAsEnterprise(
  customerNumber: string,
  linkToCustomerNumber: string,
  linkedBy: string,
): Promise<LinkedCustomerAccountsResponse> {
  const response = await fetch(
    `${PLATFORM_API_BASE}/customer-match/linked-customers/`
    + `${encodeURIComponent(customerNumber)}/link`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        link_to_customer_number: linkToCustomerNumber,
        linked_by: linkedBy,
      }),
    },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function unlinkCustomerFromManualEnterprise(
  customerNumber: string,
): Promise<LinkedCustomerAccountsResponse> {
  const response = await fetch(
    `${PLATFORM_API_BASE}/customer-match/linked-customers/`
    + `${encodeURIComponent(customerNumber)}/link`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}
