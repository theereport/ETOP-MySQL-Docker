export const paymentNotesCurrency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const paymentNotesInteger = new Intl.NumberFormat('en-US')

const paymentNotesDate = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
})

const paymentNotesDateTime = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function formatCents(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? 'Unavailable'
    : paymentNotesCurrency.format(value / 100)
}

export function formatCount(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? 'Unavailable'
    : paymentNotesInteger.format(value)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const parsed = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value)
  return Number.isNaN(parsed.valueOf()) ? value : paymentNotesDate.format(parsed)
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : paymentNotesDateTime.format(parsed)
}

export function readableStatus(value: string): string {
  return value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function shortHash(value: string | null | undefined): string {
  return value ? `${value.slice(0, 10)}…${value.slice(-6)}` : 'Unavailable'
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export function toDateInput(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function calendarWindowSuggestion(mode: 'same_day' | 'prior_calendar_day'): {
  dateFrom: string
  dateTo: string
} {
  const end = new Date()
  end.setHours(12, 0, 0, 0)
  if (mode === 'prior_calendar_day') {
    end.setDate(end.getDate() - 1)
  }
  const start = new Date(end)
  start.setDate(start.getDate() - 7)
  return { dateFrom: toDateInput(start), dateTo: toDateInput(end) }
}
