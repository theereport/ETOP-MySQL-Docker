import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

import {
  getDocumentHealth,
  getDocumentJobs,
  getDocumentParsers,
} from '../api'

import type {
  DocumentHealth,
  DocumentJob,
  DocumentParser,
} from '../types'

export function useDocumentData() {
  const [
    health,
    setHealth,
  ] = useState<DocumentHealth | null>(
    null,
  )

  const [
    jobs,
    setJobs,
  ] = useState<DocumentJob[]>([])

  const [
    parsers,
    setParsers,
  ] = useState<DocumentParser[]>([])

  const [
    isLoading,
    setIsLoading,
  ] = useState(false)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState('')

  const refreshData =
    useCallback(async () => {
      setIsLoading(true)
      setErrorMessage('')

      try {
        const [
          nextHealth,
          nextJobs,
          nextParsers,
        ] = await Promise.all([
          getDocumentHealth(),
          getDocumentJobs(200),
          getDocumentParsers(),
        ])

        setHealth(nextHealth)
        setJobs(nextJobs)
        setParsers(nextParsers)
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'Unable to load Document Operations.',
        )
      } finally {
        setIsLoading(false)
      }
    }, [])

  useEffect(() => {
    // The hook intentionally performs its initial external API synchronization
    // when the consumer mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshData()

    const timer =
      window.setInterval(
        () => {
          void refreshData()
        },
        15000,
      )

    return () =>
      window.clearInterval(timer)
  }, [refreshData])

  const completedJobs =
    useMemo(
      () =>
        jobs.filter(
          (job) =>
            job.status ===
            'completed',
        ),
      [jobs],
    )

  const reviewJobs =
    useMemo(
      () =>
        jobs.filter(
          (job) =>
            job.status ===
              'completed' &&
            (
              job.document_type ===
                'unknown' ||
              job.confidence < 0.9
            ),
        ),
      [jobs],
    )

  const failedJobs =
    useMemo(
      () =>
        jobs.filter(
          (job) =>
            job.status === 'failed',
        ),
      [jobs],
    )

  const averageConfidence =
    useMemo(() => {
      if (
        completedJobs.length === 0
      ) {
        return 0
      }

      return (
        completedJobs.reduce(
          (total, job) =>
            total +
            job.confidence,
          0,
        ) /
        completedJobs.length
      )
    }, [completedJobs])

  const apJobs =
    useMemo(
      () =>
        completedJobs.filter(
          (job) =>
            job.document_type ===
            'vendor_invoice',
        ),
      [completedJobs],
    )

  return {
    health,
    jobs,
    parsers,
    completedJobs,
    reviewJobs,
    failedJobs,
    averageConfidence,
    apJobs,
    isLoading,
    errorMessage,
    setErrorMessage,
    refreshData,
  }
}
