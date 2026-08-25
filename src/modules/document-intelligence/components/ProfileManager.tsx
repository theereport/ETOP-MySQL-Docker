import type {
  TrainingProfile,
} from '../types'

import {
  formatDocumentType,
} from '../utils'

type Props = {
  profiles: TrainingProfile[]
}

export default function ProfileManager({
  profiles,
}: Props) {
  return (
    <section className="ed-profile-grid">
      {profiles.map(
        (profile) => (
          <article
            className="ed-card ed-profile-card"
            key={profile.id}
          >
            <div>
              <span>
                {formatDocumentType(
                  profile.documentType,
                )}
              </span>
              <strong>
                {profile.name}
              </strong>
              <p>
                Parser:{' '}
                {profile.parserKey ||
                  'Not selected'}
              </p>
            </div>

            <dl>
              <div>
                <dt>Template</dt>
                <dd>
                  {profile.outputTemplate ||
                    '—'}
                </dd>
              </div>
              <div>
                <dt>Destination</dt>
                <dd>
                  {profile.destination ||
                    '—'}
                </dd>
              </div>
              <div>
                <dt>Signals</dt>
                <dd>
                  {
                    profile.signals
                      .length
                  }
                </dd>
              </div>
            </dl>
          </article>
        ),
      )}

      {profiles.length === 0 && (
        <div className="ed-empty ed-large-empty">
          No training profiles have
          been created.
        </div>
      )}
    </section>
  )
}
