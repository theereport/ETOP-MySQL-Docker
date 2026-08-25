import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  configuredBackendOrigins,
  rewriteLegacyETOPRequestUrl,
  shouldAttachETOPSession,
} from '../src/features/security-access/backendOriginPolicy.ts'

test('a configured test backend is the only bearer-token origin', () => {
  const origins = configuredBackendOrigins(
    'http://127.0.0.1:8123/api/v1',
    'http://127.0.0.1:5174',
  )
  assert.deepEqual([...origins], ['http://127.0.0.1:8123'])
  assert.equal(
    shouldAttachETOPSession(
      'http://127.0.0.1:8123/api/v1/accounts-payable',
      origins,
      'http://127.0.0.1:5174',
    ),
    true,
  )
  assert.equal(
    shouldAttachETOPSession(
      'http://127.0.0.1:8000/api/v1/accounts-payable',
      origins,
      'http://127.0.0.1:5174',
    ),
    false,
  )
  assert.equal(
    shouldAttachETOPSession(
      'https://example.com/analytics',
      origins,
      'http://127.0.0.1:5174',
    ),
    false,
  )
  assert.equal(
    rewriteLegacyETOPRequestUrl(
      'http://127.0.0.1:8000/api/v1/accounts-payable?limit=10',
      'http://127.0.0.1:8123',
      'http://127.0.0.1:5174',
    ),
    'http://127.0.0.1:8123/api/v1/accounts-payable?limit=10',
  )
  assert.equal(
    rewriteLegacyETOPRequestUrl(
      'https://example.com/analytics',
      'http://127.0.0.1:8123',
      'http://127.0.0.1:5174',
    ),
    'https://example.com/analytics',
  )
})

test('default local API origins are used only with no configured base URL', () => {
  const origins = configuredBackendOrigins(undefined, 'http://127.0.0.1:5173')
  assert.deepEqual(
    [...origins],
    ['http://127.0.0.1:8000', 'http://localhost:8000'],
  )
})

test('invalid configured backend fails closed instead of using defaults', () => {
  const origins = configuredBackendOrigins(
    'http://[invalid',
    'http://127.0.0.1:5174',
  )
  assert.equal(origins.size, 0)
})

test('every ready App module is registered in backend access contracts', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const schemaSource = readFileSync(
    new URL('../backend/modules/workflow_foundation/schemas.py', import.meta.url),
    'utf8',
  )
  const repositorySource = readFileSync(
    new URL('../backend/modules/workflow_foundation/repository.py', import.meta.url),
    'utf8',
  )
  const moduleArray = appSource.slice(
    appSource.indexOf('const modules: WorkbenchModule[] = ['),
    appSource.indexOf('\n]\n\nconst navigationGroups') + 2,
  )
  const readyEntries = moduleArray
    .split('\n  {')
    .filter((entry) => entry.includes("status: 'Ready'"))
  const readyModuleIds = readyEntries.map((entry) => {
    const match = entry.match(/moduleId: '([a-z0-9_]+)'/)
    assert.ok(match, `Ready module is missing moduleId: ${entry.slice(0, 100)}`)
    return match[1]
  })

  assert.equal(new Set(readyModuleIds).size, readyModuleIds.length)
  for (const moduleId of readyModuleIds) {
    assert.match(schemaSource, new RegExp(`\\s+"${moduleId}",`))
    assert.match(repositorySource, new RegExp(`\\n\\s+\\(\\n\\s+"${moduleId}",`))
  }
  assert.ok(readyModuleIds.includes('security_administration'))
  assert.ok(readyModuleIds.includes('payment_notes'))
})

test('Payment Notes is discoverable in active and compatibility platform registries', () => {
  const frontendRegistry = readFileSync(
    new URL('../src/platform/registry.ts', import.meta.url),
    'utf8',
  )
  const compatibilitySeed = readFileSync(
    new URL('../src/platform/registry/modules.ts', import.meta.url),
    'utf8',
  )
  const backendRegistry = readFileSync(
    new URL('../backend/etop_platform/registry.py', import.meta.url),
    'utf8',
  )

  for (const registry of [frontendRegistry, compatibilitySeed, backendRegistry]) {
    assert.match(registry, /payment-notes/)
    assert.match(registry, /Payment Notes/)
  }
})

test('Payment Notes router is wired into the canonical backend application', () => {
  const mainSource = readFileSync(
    new URL('../backend/main.py', import.meta.url),
    'utf8',
  )

  assert.match(
    mainSource,
    /from modules\.payment_notes\.api import router as payment_notes_router/,
  )
  assert.match(mainSource, /app\.include_router\(payment_notes_router\)/)
})
