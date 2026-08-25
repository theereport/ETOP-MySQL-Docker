import {
  useRef,
  useState,
} from 'react'

type Props = {
  isUploading: boolean
  onFiles: (
    files: FileList | File[],
  ) => void
}

export default function DocumentUpload({
  isUploading,
  onFiles,
}: Props) {
  const [
    dragActive,
    setDragActive,
  ] = useState(false)

  const fileInputRef =
    useRef<HTMLInputElement | null>(
      null,
    )

  return (
    <section className="ed-upload-layout">
      <article
        className={
          dragActive
            ? 'ed-dropzone active'
            : 'ed-dropzone'
        }
        onDragEnter={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragOver={(event) =>
          event.preventDefault()
        }
        onDragLeave={() =>
          setDragActive(false)
        }
        onDrop={(event) => {
          event.preventDefault()
          setDragActive(false)
          onFiles(
            event.dataTransfer.files,
          )
        }}
      >
        <span className="ed-upload-icon">
          ⇧
        </span>
        <h2>
          Drop PDF documents here
        </h2>
        <p>
          Documents are stored and
          processed locally.
        </p>

        <button
          type="button"
          className="primary"
          disabled={isUploading}
          onClick={() =>
            fileInputRef.current
              ?.click()
          }
        >
          {isUploading
            ? 'Processing…'
            : 'Browse Files'}
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(event) => {
            if (
              event.target.files
            ) {
              onFiles(
                event.target.files,
              )
            }

            event.target.value = ''
          }}
        />
      </article>

      <article className="ed-card">
        <div className="ed-card-heading">
          <div>
            <strong>
              Supported Workflow
            </strong>
            <span>
              Automatic after upload
            </span>
          </div>
        </div>

        <ol className="ed-step-list">
          <li>
            PDF saved to secure local
            storage
          </li>
          <li>
            Text extracted from native
            PDF content
          </li>
          <li>
            Document type classified
            using rules
          </li>
          <li>
            Matching parser selected
          </li>
          <li>
            Structured JSON result
            stored
          </li>
          <li>
            Low-confidence items sent
            to review
          </li>
        </ol>
      </article>
    </section>
  )
}
