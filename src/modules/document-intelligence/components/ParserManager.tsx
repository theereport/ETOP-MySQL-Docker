import type {
  DocumentParser,
} from '../types'

type Props = {
  parsers: DocumentParser[]
}

export default function ParserManager({
  parsers,
}: Props) {
  return (
    <section className="ed-profile-grid">
      {parsers.map(
        (
          parser,
          index,
        ) => (
          <article
            className="ed-card ed-profile-card"
            key={
              parser.key ??
              parser.name ??
              index
            }
          >
            <div>
              <span>
                REGISTERED PARSER
              </span>
              <strong>
                {parser.name ??
                  parser.key ??
                  parser.document_type ??
                  `Parser ${
                    index + 1
                  }`}
              </strong>
              <p>
                {parser.description ??
                  'Document parser registered with the local engine.'}
              </p>
            </div>

            <pre>
              {JSON.stringify(
                parser,
                null,
                2,
              )}
            </pre>
          </article>
        ),
      )}

      {parsers.length === 0 && (
        <div className="ed-empty ed-large-empty">
          No registered parsers were
          returned.
        </div>
      )}
    </section>
  )
}
