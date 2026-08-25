import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const root = process.cwd()
const featureRoot = path.resolve(root, 'src/features/credit-risk')

const readFeature = (fileName) =>
  fs.readFileSync(path.join(featureRoot, fileName), 'utf8')

for (const fileName of [
  'CreditRiskWorkspace.tsx',
  'CreditRiskWorkspace.css',
  'api.ts',
  'types.ts',
  'validation.ts',
  'index.ts',
]) {
  assert.ok(
    fs.existsSync(path.join(featureRoot, fileName)),
    `Missing Credit Risk frontend file: ${fileName}`,
  )
}

const validationSource = readFeature('validation.ts')
const validationTranspiled = ts.transpileModule(validationSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const validationModule = { exports: {} }

new Function('module', 'exports', validationTranspiled)(
  validationModule,
  validationModule.exports,
)

const {
  findBandForRating,
  ratingOptions,
  toCreateAssessmentRequest,
  validateAssessmentDraft,
} = validationModule.exports

const bands = [
  {
    sequence: 1,
    rating_min: 1,
    rating_max: 2,
    meaning: 'Very low risk',
    typical_response: 'Normal terms',
  },
  {
    sequence: 2,
    rating_min: 3,
    rating_max: 4,
    meaning: 'Low risk',
    typical_response: 'Routine monitoring',
  },
  {
    sequence: 3,
    rating_min: 5,
    rating_max: 10,
    meaning: 'Additional governed bands',
    typical_response: 'Professional response',
  },
]

assert.deepEqual(ratingOptions(bands), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
assert.equal(findBandForRating(bands, 4).meaning, 'Low risk')
assert.equal(findBandForRating(bands, 11), null)

const validDraft = {
  rating: '7',
  reviewDate: '2026-08-06',
  nextReviewDate: '2026-09-06',
  analystIdentity: '  Credit Professional  ',
  rationale: '  Evidence-based professional judgment.  ',
}

assert.deepEqual(validateAssessmentDraft(validDraft, bands), {})
assert.deepEqual(toCreateAssessmentRequest(validDraft), {
  manual_rating: 7,
  review_date: '2026-08-06',
  next_review_date: '2026-09-06',
  analyst_identity: 'Credit Professional',
  rationale: 'Evidence-based professional judgment.',
})

const invalidDraft = {
  rating: '6.5',
  reviewDate: '2026-02-30',
  nextReviewDate: '2026-01-01',
  analystIdentity: '   ',
  rationale: '',
}
const invalidErrors = validateAssessmentDraft(invalidDraft, bands)

assert.ok(invalidErrors.rating)
assert.ok(invalidErrors.reviewDate)
assert.ok(invalidErrors.analystIdentity)
assert.ok(invalidErrors.rationale)

const backwardDateErrors = validateAssessmentDraft(
  {
    ...validDraft,
    nextReviewDate: '2026-08-05',
  },
  bands,
)
assert.match(backwardDateErrors.nextReviewDate, /cannot be before/)

const apiSource = readFeature('api.ts')
const workspaceSource = readFeature('CreditRiskWorkspace.tsx')
const typesSource = readFeature('types.ts')
const appSource = fs.readFileSync(path.join(root, 'src/App.tsx'), 'utf8')
const frontendRegistrySource = fs.readFileSync(
  path.join(root, 'src/platform/registry.ts'),
  'utf8',
)
const searchSeedSource = fs.readFileSync(
  path.join(root, 'src/platform/registry/modules.ts'),
  'utf8',
)
const backendRegistrySource = fs.readFileSync(
  path.join(root, 'backend/etop_platform/registry.py'),
  'utf8',
)
const backendMainSource = fs.readFileSync(
  path.join(root, 'backend/main.py'),
  'utf8',
)

assert.match(apiSource, /searchSharedCustomers\(search, signal, true\)/)
assert.match(apiSource, /'\/credit-risk\/bands'/)
assert.match(apiSource, /`\/credit-risk\/customers\/\$\{customer\}`/)
assert.match(
  apiSource,
  /`\/credit-risk\/customers\/\$\{customer\}\/assessments`/,
)
assert.match(apiSource, /method: 'POST'/)
assert.match(apiSource, /detail\.message/)

assert.match(workspaceSource, /saveInFlight\.current/)
assert.match(workspaceSource, /searchGeneration\.current/)
assert.match(workspaceSource, /customerGeneration\.current/)
assert.match(workspaceSource, /Promise\.allSettled/)
assert.match(workspaceSource, /getCustomerRiskAssessments/)
assert.match(workspaceSource, /Live ERP evidence is unavailable/)
assert.match(workspaceSource, /Existing local history remains separate/)
assert.match(workspaceSource, /Save append-only assessment/)
assert.match(workspaceSource, /evidence_snapshot_sha256/)
assert.match(workspaceSource, /operation === 'informational'/)
assert.match(workspaceSource, /last_payment_explanation/)
assert.match(workspaceSource, /Required full formula/)
assert.match(workspaceSource, /partial exposure/i)
assert.match(workspaceSource, /Unavail(?:able|ability)/i)
assert.match(workspaceSource, /operator supplied/i)
assert.match(workspaceSource, /does not independently verify/i)
assert.match(workspaceSource, /does not approve a review/i)
assert.match(workspaceSource, /does not.*write to ERP/is)
assert.match(workspaceSource, /No placeholder customer was opened/)

assert.match(typesSource, /operation: 'add' \| 'subtract' \| 'informational'/)
assert.match(typesSource, /calculation_value: number \| null/)
assert.match(typesSource, /automatic_score: boolean/)
assert.match(typesSource, /evidence_snapshot_sha256: string/)

assert.doesNotMatch(apiSource, /customer-risk\/review/)
assert.doesNotMatch(workspaceSource, /calculateHealth/)
assert.doesNotMatch(workspaceSource, /buildRecommendations/)
assert.doesNotMatch(workspaceSource, /risk_score/)
assert.doesNotMatch(workspaceSource, /Priority Review/)

assert.match(appSource, /import CreditRiskWorkspace from '.\/features\/credit-risk'/)
assert.match(appSource, /title: 'Credit Risk'/)
assert.match(appSource, /selectedModule === 'Credit Risk'/)
assert.match(frontendRegistrySource, /id: 'credit-risk'/)
assert.match(searchSeedSource, /module: 'Credit Risk'/)
assert.match(backendRegistrySource, /"id": "credit-risk"/)
assert.match(backendRegistrySource, /"action": "Credit Risk"/)
assert.match(backendMainSource, /credit_risk_foundation_router/)
assert.match(backendMainSource, /include_router\(credit_risk_foundation_router\)/)

const requestFields = Object.keys(toCreateAssessmentRequest(validDraft)).sort()
assert.deepEqual(requestFields, [
  'analyst_identity',
  'manual_rating',
  'next_review_date',
  'rationale',
  'review_date',
])

console.log(
  'Credit Risk frontend workflow passed: shared customer search, generation-owned loading, exact governed APIs, partial-exposure and missing-evidence presentation, strict manual-assessment validation, duplicate-submit guard, append-only reload/history, local-only degraded history, and snapshot/hash reconstruction are present without legacy scoring or Priority Review policy.',
)
