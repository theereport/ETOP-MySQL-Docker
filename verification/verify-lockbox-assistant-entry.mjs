import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const sourcePath = path.resolve(process.cwd(), 'src/App.tsx')
const source = fs.readFileSync(sourcePath, 'utf8')

const openModuleStart = source.indexOf('  function openModule(')
const nextHookStart = source.indexOf('\n  useEffect(', openModuleStart)

assert.notEqual(
  openModuleStart,
  -1,
  'App must retain the centralized openModule navigation owner.',
)
assert.notEqual(
  nextHookStart,
  -1,
  'The retained verifier could not determine the end of openModule.',
)

const openModuleSource = source.slice(openModuleStart, nextHookStart)
const assistantStateCalls = (
  openModuleSource.match(/setAssistantPanelOpen\s*\(/g) ?? []
)

assert.equal(
  assistantStateCalls.length,
  1,
  'Central navigation must close assistant visibility exactly once.',
)
assert.match(
  openModuleSource,
  /setAssistantPanelOpen\(false\)\s*\n\s*setSelectedModule\(moduleName\)/,
  'Every successful centralized workspace navigation must close the right Local AI panel before changing workspaces.',
)
assert.doesNotMatch(
  openModuleSource,
  /moduleName\s*===\s*'Lockbox Automation'/,
  'Assistant closing must not be restricted to Lockbox navigation.',
)

assert.match(
  source,
  /\[assistantPanelOpen, setAssistantPanelOpen\]\s*=\s*useState\(false\)/,
  'The local assistant panel must start closed.',
)
assert.doesNotMatch(
  source,
  /setAssistantPanelOpen\(true\)/,
  'No code path may directly open the local assistant panel.',
)
assert.match(
  source,
  /setTimeout\(\(\)\s*=>\s*\{\s*setAssistantPanelOpen\(false\)\s*setSelectedModule\(fallbackModule\)/,
  'Permission fallback navigation must also close the local assistant panel.',
)

assert.match(
  source,
  /onClick=\{\(\)\s*=>\s*setAssistantPanelOpen\(\(current\)\s*=>\s*!current\)\s*\}/,
  'The top-right manual assistant toggle must remain available.',
)
assert.match(
  source,
  /onClick=\{\(\)\s*=>\s*openModule\('AI Assistant'\)\}/,
  'Ask AI must retain its existing full-workspace navigation.',
)
assert.match(
  source,
  /onClick=\{\(\)\s*=>\s*openModule\(module\.title\)\}/,
  'Sidebar navigation must continue to use the centralized openModule owner.',
)

assert.match(
  source,
  /<WorkspaceErrorBoundary[\s\S]*key=\{selectedModule\}[\s\S]*onReturnHome=\{\(\) => openModule\('Dashboard'\)\}/,
  'Each selected workspace must render inside a resettable visible error boundary.',
)

const boundaryPath = path.resolve(
  process.cwd(),
  'src/components/WorkspaceErrorBoundary.tsx',
)
const boundarySource = fs.readFileSync(boundaryPath, 'utf8')
assert.match(boundarySource, /getDerivedStateFromError/)
assert.match(boundarySource, /role="alert"/)
assert.match(
  boundarySource,
  /display fallback does not perform an ERP write or financial action/,
)
assert.match(
  boundarySource,
  /this\.props\.onReturnHome\(\)[\s\S]*this\.setState\(\{ failed: false \}\)/,
  'The dashboard action must remove the throwing workspace before clearing the boundary.',
)
assert.match(boundarySource, /Preserve the current test environment and its logs/)
assert.doesNotMatch(
  boundarySource,
  /error\.message|String\(error\)|errorInfo|componentStack/,
  'The visible fallback must not expose raw runtime or business-data details.',
)

console.log(
  'Assistant visibility and workspace containment regression passed: the assistant starts closed, every successful navigation closes it, only the titlebar toggle can open it, and workspace render failures remain visible without raw error details.',
)
