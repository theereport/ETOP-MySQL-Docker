import {
  useEffect,
  useRef,
  useState,
} from 'react'

import {
  deleteDocumentJob,
  getDocumentResult,
  processDocument,
  uploadDocument,
} from './api'

import type {
  DocumentJob,
  DocumentResult,
  TrainingProfile,
} from './types'

import APDashboard from './components/APDashboard'
import DocumentDashboard from './components/DocumentDashboard'
import DocumentQueue from './components/DocumentQueue'
import DocumentViewer from './components/DocumentViewer'
import LearningEngine from './components/LearningEngine'
import LockboxAutomationCenter from './components/LockboxAutomationCenter'
import AIStudio from './components/AIStudio'
import DocumentUpload from './components/DocumentUpload'
import ParserManager from './components/ParserManager'
import ProfileManager from './components/ProfileManager'
import TemplateStudio from './components/TemplateStudio'
import TrainingStudio from './components/TrainingStudio'
import DocumentExplorer from './DocumentExplorer'

import {
  useDocumentData,
} from './hooks/useDocumentData'

import {
  useTrainingProfiles,
} from './hooks/useTrainingProfiles'
import { useLearningData } from './hooks/useLearningData'

import './DocumentIntelligence.css'
import './DocumentExplorer.css'
import './DocumentViewer.css'

type DocumentView =
  | 'dashboard'
  | 'explorer'
  | 'upload'
  | 'queue'
  | 'review'
  | 'result'
  | 'training'
  | 'learning'
  | 'ai_studio'
  | 'lockbox'
  | 'profiles'
  | 'templates'
  | 'parsers'
  | 'ap'

export type DocumentWorkspace =
  | 'documents'
  | 'lockbox'
  | 'studio'

type Props = {
  workspace?: DocumentWorkspace
  initialJobId?: string
}

type NavigationItem = {
  key: DocumentView
  label: string
  icon: string
}

type NavigationGroup = {
  label: string
  items: NavigationItem[]
}

const DOCUMENT_NAVIGATION: NavigationGroup[] = [
  {
    label: 'Daily Work',
    items: [
      { key: 'dashboard', label: 'Overview', icon: '⌂' },
      { key: 'explorer', label: 'All Documents', icon: '⌕' },
      { key: 'upload', label: 'Upload Documents', icon: '⇧' },
      { key: 'review', label: 'Review Queue', icon: '✓' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { key: 'queue', label: 'Processing History', icon: '≡' },
      { key: 'ap', label: 'Accounts Payable', icon: '$' },
    ],
  },
]

const STUDIO_NAVIGATION: NavigationGroup[] = [
  {
    label: 'Quality',
    items: [
      { key: 'ai_studio', label: 'Studio Overview', icon: '✦' },
      { key: 'learning', label: 'Learning Review', icon: '↻' },
    ],
  },
  {
    label: 'Training',
    items: [
      { key: 'training', label: 'Profile Builder', icon: '◇' },
      { key: 'profiles', label: 'Saved Profiles', icon: '▣' },
    ],
  },
  {
    label: 'Configuration',
    items: [
      { key: 'templates', label: 'Output Templates', icon: '▤' },
      { key: 'parsers', label: 'Parser Manager', icon: '⚙' },
    ],
  },
]

const TITLES:
  Record<DocumentView, string> = {
    dashboard:
      'Document Command Center',
    explorer:
      'Document Explorer',
    upload:
      'Upload Documents',
    queue:
      'Processing Queue',
    review:
      'Review Queue',
    result:
      'Document Result',
    training:
      'Training Studio',
    learning:
      'Manual Learning',
    ai_studio:
      'AI Studio',
    lockbox:
      'Lockbox Automation Center',
    profiles:
      'Document Profiles',
    templates:
      'Output Templates',
    parsers:
      'Parser Manager',
    ap:
      'Accounts Payable Dashboard',
  }

const DESCRIPTIONS:
  Record<DocumentView, string> = {
    dashboard:
      'See document volume, review demand, recent activity, and engine health.',
    explorer:
      'Find every uploaded document and open its current processing result.',
    upload:
      'Add documents to the local intake pipeline for classification and extraction.',
    queue:
      'Monitor document processing status and rerun jobs that need attention.',
    review:
      'Resolve unknown documents and low-confidence extraction results.',
    result:
      'Inspect the source file, extracted fields, confidence, and structured output.',
    training:
      'Create a reusable extraction profile from a known document layout.',
    learning:
      'Review saved corrections and the examples used to improve extraction.',
    ai_studio:
      'Measure parser quality and manage the document-learning lifecycle.',
    lockbox:
      'Process PNC lockbox PDFs from upload through review, export, and training.',
    profiles:
      'Review the extraction profiles available to the document engine.',
    templates:
      'Control how validated document data is formatted for downstream use.',
    parsers:
      'Inspect the extraction engines available for each document type.',
    ap:
      'Review accounts payable documents and open the items that need action.',
  }

const WORKSPACE_START: Record<DocumentWorkspace, DocumentView> = {
  documents: 'dashboard',
  lockbox: 'lockbox',
  studio: 'ai_studio',
}

function EnterpriseDocuments({
  workspace = 'documents',
  initialJobId,
}: Props) {
  const [
    view,
    setView,
  ] = useState<DocumentView>(
    WORKSPACE_START[workspace],
  )

  const [
    selectedJob,
    setSelectedJob,
  ] = useState<DocumentJob | null>(
    null,
  )

  const [
    selectedResult,
    setSelectedResult,
  ] = useState<DocumentResult | null>(
    null,
  )

  const [
    noticeMessage,
    setNoticeMessage,
  ] = useState('')

  const [
    isUploading,
    setIsUploading,
  ] = useState(false)

  const openedSearchJobId = useRef<string | null>(null)

  const {
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
  } = useDocumentData()

  const {
    profiles,
    setProfiles,
  } = useTrainingProfiles()

  const { summary: learningSummary, examples: learningExamples, isLoading: isLearningLoading, errorMessage: learningErrorMessage, refreshLearning } = useLearningData()

  const clearMessages = () => {
    setErrorMessage('')
    setNoticeMessage('')
  }

  const navigate = (
    next: DocumentView,
  ) => {
    clearMessages()
    setView(next)
  }

  const openJob = async (
    job: DocumentJob,
  ) => {
    setSelectedJob(job)
    setSelectedResult(null)
    clearMessages()

    if (
      job.status !== 'completed'
    ) {
      setView('queue')
      return
    }

    try {
      const result =
        await getDocumentResult(
          job.job_id,
        )

      setSelectedResult(result)
      setView('result')
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load the document result.',
      )
    }
  }

  useEffect(() => {
    if (
      !initialJobId ||
      openedSearchJobId.current === initialJobId
    ) {
      return
    }

    const requestedJob = jobs.find(
      (job) => job.job_id === initialJobId,
    )

    if (!requestedJob) {
      return
    }

    openedSearchJobId.current = initialJobId
    const timeoutId = window.setTimeout(() => {
      void openJob(requestedJob)
    }, 0)

    return () => window.clearTimeout(timeoutId)
    // openJob intentionally uses the latest component closure for this job.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialJobId, jobs])

  const runJob = async (
    job: DocumentJob,
  ) => {
    clearMessages()

    try {
      const result =
        await processDocument(
          job.job_id,
        )

      setSelectedJob(result.job)
      setSelectedResult(result)
      setNoticeMessage(
        'Document processing completed.',
      )
      setView('result')
      await refreshData()
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Document processing failed.',
      )
    }
  }

  const deleteJobs = async (
    jobIds: string[],
  ) => {
    clearMessages()

    try {
      for (const jobId of jobIds) {
        await deleteDocumentJob(jobId)
      }

      setNoticeMessage(
        jobIds.length === 1
          ? 'Document deleted.'
          : `${jobIds.length} documents deleted.`,
      )
      await refreshData()
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to delete the selected document(s).',
      )
      await refreshData()
    }
  }

  const handleFiles = async (
    fileList: FileList | File[],
  ) => {
    const files =
      Array.from(fileList)

    if (files.length === 0) {
      return
    }

    setIsUploading(true)
    clearMessages()

    let uploaded = 0

    try {
      for (const file of files) {
        const job =
          await uploadDocument(file)

        const result =
          await processDocument(
            job.job_id,
          )

        uploaded += 1
        setSelectedJob(result.job)
        setSelectedResult(result)
      }

      setNoticeMessage(
        `${uploaded} document${
          uploaded === 1
            ? ''
            : 's'
        } uploaded and processed.`,
      )

      await refreshData()
      setView('explorer')
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Document upload failed.',
      )
    } finally {
      setIsUploading(false)
    }
  }

  const uploadLockboxPdf = async (file: File): Promise<DocumentJob> => {
    setIsUploading(true)
    clearMessages()

    try {
      const job = await uploadDocument(file)
      setNoticeMessage('PNC PDF uploaded and ready for lockbox processing.')
      await refreshData()
      return job
    } catch (error) {
      const message = error instanceof Error ? error.message : 'PNC PDF upload failed.'
      setErrorMessage(message)
      throw error
    } finally {
      setIsUploading(false)
    }
  }

  const saveProfile = (
    profile: TrainingProfile,
  ) => {
    setProfiles(
      (current) => [
        profile,
        ...current,
      ],
    )

    setNoticeMessage(
      'Training profile saved locally.',
    )
    setView('profiles')
  }

  if (workspace === 'lockbox') {
    return (
      <div className="enterprise-documents ed-focus-workspace">
        <main className="ed-workspace">
          <div className="ed-focus-toolbar">
            <div>
              <span>DAILY OPERATIONS</span>
              <strong>Lockbox Automation</strong>
            </div>

            <button
              type="button"
              className="secondary"
              onClick={() => void refreshData()}
              disabled={isLoading}
            >
              {isLoading ? 'Refreshing…' : 'Refresh lockboxes'}
            </button>
          </div>

          {errorMessage && (
            <div className="ed-banner error">
              {errorMessage}
            </div>
          )}

          {noticeMessage && (
            <div className="ed-banner notice">
              {noticeMessage}
            </div>
          )}

          <LockboxAutomationCenter
            jobs={jobs}
            isUploading={isUploading}
            onUploadPdf={uploadLockboxPdf}
            onRefresh={refreshData}
          />
        </main>
      </div>
    )
  }

  const navigationGroups =
    workspace === 'studio'
      ? STUDIO_NAVIGATION
      : DOCUMENT_NAVIGATION

  return (
    <div className={`enterprise-documents ${workspace === 'studio' ? 'ed-studio-workspace' : ''}`}>
      <aside className="ed-sidebar">
        <div className="ed-sidebar-heading">
          <span>
            {workspace === 'studio'
              ? 'DOCUMENT INTELLIGENCE'
              : 'OPERATIONAL WORKSPACE'}
          </span>
          <strong>
            {workspace === 'studio'
              ? 'Document AI Studio'
              : 'Document Operations'}
          </strong>
        </div>

        <nav aria-label={workspace === 'studio' ? 'Document AI Studio' : 'Document operations'}>
          {navigationGroups.map((group) => (
            <section className="ed-navigation-group" key={group.label}>
              <h2>{group.label}</h2>

              {group.items.map((item) => (
                <button
                  type="button"
                  key={item.key}
                  className={view === item.key ? 'active' : ''}
                  onClick={() => navigate(item.key)}
                >
                  <span>{item.icon}</span>
                  {item.label}

                  {item.key === 'review' &&
                    reviewJobs.length > 0 && (
                      <b>{reviewJobs.length}</b>
                    )}
                </button>
              ))}
            </section>
          ))}
        </nav>

        <div className="ed-engine-card">
          <span
            className={
              health?.status ===
              'healthy'
                ? 'healthy'
                : ''
            }
          />

          <div>
            <strong>
              Document Engine
            </strong>
            <small>
              {health?.status ??
                'Checking'}
            </small>
          </div>
        </div>
      </aside>

      <main className="ed-workspace">
        <header className="ed-header">
          <div>
            <span className="ed-eyebrow">
              {workspace === 'studio'
                ? 'DOCUMENT AI GOVERNANCE'
                : 'DOCUMENT OPERATIONS'}
            </span>

            <h1>
              {TITLES[view]}
            </h1>

            <p>
              {DESCRIPTIONS[view]}
            </p>
          </div>

          <div className="ed-header-actions">
            <button
              type="button"
              className="secondary"
              onClick={() =>
                void refreshData()
              }
              disabled={isLoading}
            >
              {isLoading
                ? 'Refreshing…'
                : 'Refresh'}
            </button>

            {workspace === 'documents' && view !== 'upload' && (
              <button
                type="button"
                className="primary"
                onClick={() => navigate('upload')}
              >
                Upload Document
              </button>
            )}
          </div>
        </header>

        {errorMessage && (
          <div className="ed-banner error">
            {errorMessage}
          </div>
        )}

        {noticeMessage && (
          <div className="ed-banner notice">
            {noticeMessage}
          </div>
        )}

        {view === 'dashboard' && (
          <DocumentDashboard
            health={health}
            jobs={jobs}
            reviewCount={
              reviewJobs.length
            }
            completedCount={
              completedJobs.length
            }
            failedCount={
              failedJobs.length
            }
            averageConfidence={
              averageConfidence
            }
            onOpen={(job) => {
              void openJob(job)
            }}
            onViewAll={() =>
              navigate('explorer')
            }
          />
        )}

        {view === 'explorer' && (
          <DocumentExplorer
            jobs={jobs}
            onOpen={(job) => {
              void openJob(job)
            }}
            onProcess={(job) => {
              void runJob(job)
            }}
            onDelete={(jobIds) => {
              void deleteJobs(jobIds)
            }}
            isBusy={
              isLoading ||
              isUploading
            }
          />
        )}

        {view === 'upload' && (
          <DocumentUpload
            isUploading={
              isUploading
            }
            onFiles={(files) => {
              void handleFiles(files)
            }}
          />
        )}

        {view === 'queue' && (
          <DocumentQueue
            title="All Document Jobs"
            subtitle="Upload and processing history"
            jobs={jobs}
            onOpen={(job) => {
              void openJob(job)
            }}
            onProcess={(job) => {
              void runJob(job)
            }}
          />
        )}

        {view === 'review' && (
          <DocumentQueue
            title="Documents Requiring Review"
            subtitle="Unknown or below 90% confidence"
            jobs={reviewJobs}
            onOpen={(job) => {
              void openJob(job)
            }}
            onProcess={(job) => {
              void runJob(job)
            }}
          />
        )}

        {view === 'result' &&
          selectedJob && (
            <DocumentViewer
              job={selectedJob}
              result={
                selectedResult
              }
              onBack={() =>
                navigate('explorer')
              }
            />
          )}

        {view === 'training' && (
          <TrainingStudio
            parsers={parsers}
            onSave={saveProfile}
          />
        )}

        {view === 'learning' && (
          <LearningEngine summary={learningSummary} examples={learningExamples} isLoading={isLearningLoading} errorMessage={learningErrorMessage} onRefresh={() => { void refreshLearning() }} />
        )}

        {view === 'ai_studio' && (
          <AIStudio />
        )}

        {view === 'profiles' && (
          <ProfileManager
            profiles={profiles}
          />
        )}

        {view === 'templates' && (
          <TemplateStudio />
        )}

        {view === 'parsers' && (
          <ParserManager
            parsers={parsers}
          />
        )}

        {view === 'ap' && (
          <APDashboard
            jobs={apJobs}
            onOpen={(job) => {
              void openJob(job)
            }}
          />
        )}
      </main>
    </div>
  )
}

export default EnterpriseDocuments
