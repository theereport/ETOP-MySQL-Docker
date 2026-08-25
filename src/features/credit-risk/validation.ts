import type {
  AssessmentDraft,
  AssessmentErrors,
  CreateAssessmentRequest,
  RiskBand,
} from './types'

export function findBandForRating(
  bands: RiskBand[],
  rating: number,
): RiskBand | null {
  return (
    bands.find(
      (band) =>
        rating >= band.rating_min && rating <= band.rating_max,
    ) ?? null
  )
}

export function ratingOptions(bands: RiskBand[]): number[] {
  const values = new Set<number>()

  bands.forEach((band) => {
    for (
      let rating = band.rating_min;
      rating <= band.rating_max;
      rating += 1
    ) {
      values.add(rating)
    }
  })

  return Array.from(values).sort((left, right) => left - right)
}

function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false
  }

  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}

export function validateAssessmentDraft(
  draft: AssessmentDraft,
  bands: RiskBand[],
): AssessmentErrors {
  const errors: AssessmentErrors = {}
  const rating = Number(draft.rating)

  if (!draft.rating) {
    errors.rating = 'Select a manual risk rating.'
  } else if (!Number.isInteger(rating) || !findBandForRating(bands, rating)) {
    errors.rating = 'Select a rating defined by the current band configuration.'
  }

  if (!draft.reviewDate) {
    errors.reviewDate = 'Enter the assessment review date.'
  } else if (!isIsoDate(draft.reviewDate)) {
    errors.reviewDate = 'Enter a valid review date.'
  }

  if (!draft.nextReviewDate) {
    errors.nextReviewDate = 'Enter the next review date.'
  } else if (!isIsoDate(draft.nextReviewDate)) {
    errors.nextReviewDate = 'Enter a valid next review date.'
  } else if (
    isIsoDate(draft.reviewDate) &&
    draft.nextReviewDate < draft.reviewDate
  ) {
    errors.nextReviewDate = 'The next review date cannot be before the review date.'
  }

  if (!draft.analystIdentity.trim()) {
    errors.analystIdentity = 'Enter the analyst identity used for this assessment.'
  }

  if (!draft.rationale.trim()) {
    errors.rationale = 'Document the professional rationale for the manual rating.'
  }

  return errors
}

export function toCreateAssessmentRequest(
  draft: AssessmentDraft,
): CreateAssessmentRequest {
  return {
    manual_rating: Number(draft.rating),
    review_date: draft.reviewDate,
    next_review_date: draft.nextReviewDate,
    analyst_identity: draft.analystIdentity.trim(),
    rationale: draft.rationale.trim(),
  }
}
