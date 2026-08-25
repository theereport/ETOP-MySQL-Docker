import {
  useEffect,
  useState,
} from 'react'

import type {
  TrainingProfile,
} from '../types'

const STORAGE_KEY =
  'etop.document-intelligence.training-profiles'

function loadProfiles():
  TrainingProfile[] {
  try {
    const stored =
      window.localStorage.getItem(
        STORAGE_KEY,
      )

    if (!stored) {
      return []
    }

    const parsed: unknown =
      JSON.parse(stored)

    return Array.isArray(parsed)
      ? parsed as TrainingProfile[]
      : []
  } catch {
    return []
  }
}

export function useTrainingProfiles() {
  const [
    profiles,
    setProfiles,
  ] = useState<
    TrainingProfile[]
  >(() => loadProfiles())

  useEffect(() => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(profiles),
    )
  }, [profiles])

  return {
    profiles,
    setProfiles,
  }
}
