import {
  useState,
} from 'react'

import type {
  DocumentParser,
  DocumentType,
  TrainingProfile,
} from '../types'

type Props = {
  parsers: DocumentParser[]
  onSave: (
    profile: TrainingProfile,
  ) => void
}

export default function TrainingStudio({
  parsers,
  onSave,
}: Props) {
  const [
    profileName,
    setProfileName,
  ] = useState('')

  const [
    profileType,
    setProfileType,
  ] = useState<DocumentType>(
    'pnc_lockbox',
  )

  const [
    profileParser,
    setProfileParser,
  ] = useState('')

  const [
    profileTemplate,
    setProfileTemplate,
  ] = useState('')

  const [
    profileDestination,
    setProfileDestination,
  ] = useState('')

  const [
    profileSignals,
    setProfileSignals,
  ] = useState('')

  const save = () => {
    const name =
      profileName.trim()

    if (!name) {
      return
    }

    const now =
      new Date().toISOString()

    onSave({
      id: crypto.randomUUID(),
      name,
      documentType:
        profileType,
      parserKey:
        profileParser.trim(),
      outputTemplate:
        profileTemplate.trim(),
      destination:
        profileDestination.trim(),
      signals: profileSignals
        .split('\n')
        .map(
          (signal) =>
            signal.trim(),
        )
        .filter(Boolean),
      createdAt: now,
      updatedAt: now,
    })

    setProfileName('')
    setProfileTemplate('')
    setProfileDestination('')
    setProfileSignals('')
  }

  return (
    <section className="ed-training-layout">
      <article className="ed-card">
        <div className="ed-card-heading">
          <div>
            <strong>
              Create Document Profile
            </strong>
            <span>
              Define what ETOP should
              recognize and produce
            </span>
          </div>
        </div>

        <div className="ed-form-grid">
          <label>
            Profile Name
            <input
              value={profileName}
              onChange={(event) =>
                setProfileName(
                  event.target.value,
                )
              }
              placeholder="PNC Lockbox"
            />
          </label>

          <label>
            Document Type
            <select
              value={profileType}
              onChange={(event) =>
                setProfileType(
                  event.target
                    .value as DocumentType,
                )
              }
            >
              <option value="pnc_lockbox">
                PNC Lockbox
              </option>
              <option value="vendor_invoice">
                Vendor Invoice
              </option>
              <option value="bank_report">
                Bank Report
              </option>
              <option value="statement">
                Statement
              </option>
              <option value="unknown">
                New Type
              </option>
            </select>
          </label>

          <label>
            Parser
            <select
              value={profileParser}
              onChange={(event) =>
                setProfileParser(
                  event.target.value,
                )
              }
            >
              <option value="">
                Select parser
              </option>

              {parsers.map(
                (
                  parser,
                  index,
                ) => {
                  const key =
                    parser.key ??
                    parser.name ??
                    parser.document_type ??
                    `parser-${index}`

                  return (
                    <option
                      key={key}
                      value={key}
                    >
                      {parser.name ??
                        parser.description ??
                        key}
                    </option>
                  )
                },
              )}
            </select>
          </label>

          <label>
            Output Template
            <input
              value={profileTemplate}
              onChange={(event) =>
                setProfileTemplate(
                  event.target.value,
                )
              }
              placeholder="PNC Standard Excel"
            />
          </label>

          <label>
            Destination
            <input
              value={
                profileDestination
              }
              onChange={(event) =>
                setProfileDestination(
                  event.target.value,
                )
              }
              placeholder="Cash Application Queue"
            />
          </label>

          <label className="wide">
            Recognition Signals
            <textarea
              value={profileSignals}
              onChange={(event) =>
                setProfileSignals(
                  event.target.value,
                )
              }
              placeholder={
                'One signal per line\nPNC logo\nLockbox number\nDeposit date\nBatch total'
              }
            />
          </label>
        </div>

        <div className="ed-form-actions">
          <button
            type="button"
            className="primary"
            onClick={save}
          >
            Save Training Profile
          </button>
        </div>
      </article>

      <article className="ed-card ed-training-note">
        <div className="ed-card-heading">
          <div>
            <strong>
              Training Foundation
            </strong>
            <span>
              Current and upcoming
              behavior
            </span>
          </div>
        </div>

        <p>
          Profiles are stored locally
          in the browser during this
          frontend phase.
        </p>

        <p>
          The backend phase will store
          profiles, examples,
          corrections, mappings, and
          parser versions.
        </p>
      </article>
    </section>
  )
}
