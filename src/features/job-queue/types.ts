export type JobQueueStatus = 'queued' | 'running' | 'completed' | 'failed'

export type JobQueueJob = {
  job_id: string
  job_type: string
  title: string
  status: JobQueueStatus
  created_by: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  message: string | null
  result_module: string | null
  result_reference: string | null
  acknowledged_at: string | null
}

export type JobQueueSummary = {
  queued_count: number
  running_count: number
  unacknowledged_count: number
  recent: JobQueueJob[]
}
