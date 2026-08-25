export function formatBytes(
  value: number,
): string {
  if (value < 1024) {
    return `${value} B`
  }

  if (value < 1024 * 1024) {
    return `${(
      value / 1024
    ).toFixed(1)} KB`
  }

  return `${(
    value /
    (1024 * 1024)
  ).toFixed(1)} MB`
}

export function formatDocumentType(
  value: string,
): string {
  return value
    .split('_')
    .map(
      (part) =>
        part.charAt(0).toUpperCase() +
        part.slice(1),
    )
    .join(' ')
}

export function confidencePercent(
  value: number,
): string {
  return `${Math.round(
    value * 100,
  )}%`
}

export function objectEntries(
  value: unknown,
): [string, unknown][] {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value)
  ) {
    return []
  }

  return Object.entries(
    value as Record<
      string,
      unknown
    >,
  )
}
