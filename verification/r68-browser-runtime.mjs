import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { EventEmitter } from 'node:events'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

export const BROWSER_STAGE = Object.freeze({
  passed: 'R68_BROWSER_STAGE_PASSED',
  edgeValidation: 'R68_BROWSER_STAGE_EDGE_VALIDATION_FAILED',
  taskkillValidation: 'R68_BROWSER_STAGE_TASKKILL_VALIDATION_FAILED',
  temporaryRoot: 'R68_BROWSER_STAGE_TEMP_ROOT_FAILED',
  profileCreation: 'R68_BROWSER_STAGE_PROFILE_CREATION_FAILED',
  edgeSpawn: 'R68_BROWSER_STAGE_EDGE_SPAWN_FAILED',
  edgeTimeout: 'R68_BROWSER_STAGE_EDGE_TIMEOUT',
  edgeOutputLimit: 'R68_BROWSER_STAGE_EDGE_OUTPUT_LIMIT',
  edgeTermination: 'R68_BROWSER_STAGE_EDGE_TERMINATION_FAILED',
  edgeExit: 'R68_BROWSER_STAGE_EDGE_EXIT_FAILED',
  edgeMarker: 'R68_BROWSER_STAGE_EDGE_MARKER_FAILED',
  profileCleanup: 'R68_BROWSER_STAGE_PROFILE_CLEANUP_FAILED',
  internal: 'R68_BROWSER_STAGE_INTERNAL_FAILED',
})

const BROWSER_STAGE_VALUES = new Set(Object.values(BROWSER_STAGE))

export class BrowserStageFailure extends Error {
  constructor(stage) {
    super(stage)
    this.name = 'BrowserStageFailure'
    this.stage = stage
  }
}

const failStage = (stage) => {
  throw new BrowserStageFailure(stage)
}

export const sanitizedBrowserStage = (error) => (
  error instanceof BrowserStageFailure
    && BROWSER_STAGE_VALUES.has(error.stage)
    ? error.stage
    : BROWSER_STAGE.internal
)

export const normalizeWindowsIdentity = (candidate) => {
  if (typeof candidate !== 'string' || candidate.length === 0) return ''
  let normalized = candidate
  if (/^\\\\\?\\UNC\\/i.test(normalized)) {
    normalized = `\\\\${normalized.slice(8)}`
  } else if (/^\\\\\?\\/.test(normalized)) {
    normalized = normalized.slice(4)
  }
  if (!path.win32.isAbsolute(normalized) || /^\\\\\.\\/.test(normalized)) {
    return ''
  }
  return path.win32.normalize(normalized).toLowerCase()
}

const nativeRealPath = (fileSystem, candidate) => {
  if (typeof fileSystem.realpathSync?.native !== 'function') {
    throw new Error('native realpath unavailable')
  }
  return fileSystem.realpathSync.native(candidate)
}

const hasExactNonReparsePathChain = (candidate, fileSystem) => {
  if (!normalizeWindowsIdentity(candidate)) return false
  try {
    let current = path.win32.normalize(candidate)
    while (true) {
      const metadata = fileSystem.lstatSync(current)
      if (metadata.isSymbolicLink()) return false
      if (
        normalizeWindowsIdentity(nativeRealPath(fileSystem, current))
        !== normalizeWindowsIdentity(current)
      ) return false
      const parent = path.win32.dirname(current)
      if (normalizeWindowsIdentity(parent) === normalizeWindowsIdentity(current)) {
        break
      }
      current = parent
    }
    return true
  } catch {
    return false
  }
}

const inspectExactWindowsExecutable = (
  candidate,
  expected,
  { fileSystem = fs, requireSingleLink = false } = {},
) => {
  if (
    !normalizeWindowsIdentity(candidate)
    || normalizeWindowsIdentity(candidate) !== normalizeWindowsIdentity(expected)
  ) return false
  try {
    const metadata = fileSystem.lstatSync(candidate)
    if (!metadata.isFile() || metadata.isSymbolicLink()) return false
    if (requireSingleLink && metadata.nlink !== 1) return false
    if (
      normalizeWindowsIdentity(nativeRealPath(fileSystem, candidate))
      !== normalizeWindowsIdentity(expected)
    ) return false
    return hasExactNonReparsePathChain(candidate, fileSystem)
  } catch {
    return false
  }
}

export const canonicalTaskkillPath = (systemRoot) => {
  if (!normalizeWindowsIdentity(systemRoot)) return ''
  return path.win32.join(systemRoot, 'System32', 'taskkill.exe')
}

export const validateInstalledTaskkill = (
  candidate,
  systemRoot,
  fileSystem = fs,
) => {
  const expected = canonicalTaskkillPath(systemRoot)
  return Boolean(expected) && inspectExactWindowsExecutable(candidate, expected, {
    fileSystem,
    // Serviced Windows inbox binaries may be hardlinked and some Node/Windows
    // combinations report nlink as zero. Exact path and realpath identity are
    // the trust boundary for canonical System32 taskkill.exe.
    requireSingleLink: false,
  })
}

export const edgeProgramFilesAllowlist = (environment) => {
  const roots = [
    environment['PROGRAMFILES(X86)'],
    environment.PROGRAMFILES,
  ]
  const allowedRootNames = new Set(['program files', 'program files (x86)'])
  const candidates = []
  for (const value of roots) {
    if (!normalizeWindowsIdentity(value)) continue
    const normalized = path.win32.normalize(value)
    const parsed = path.win32.parse(normalized)
    const relative = path.win32.relative(parsed.root, normalized).toLowerCase()
    if (!allowedRootNames.has(relative)) continue
    candidates.push(path.win32.join(
      normalized,
      'Microsoft',
      'Edge',
      'Application',
      'msedge.exe',
    ))
  }
  return [...new Map(candidates.map((candidate) => (
    [normalizeWindowsIdentity(candidate), candidate]
  ))).values()]
}

export const validateInstalledEdge = (
  candidate,
  allowlist,
  fileSystem = fs,
) => allowlist.some((expected) => inspectExactWindowsExecutable(
  candidate,
  expected,
  { fileSystem, requireSingleLink: true },
))

const waitForMilliseconds = (milliseconds) => new Promise((resolve) => {
  setTimeout(resolve, milliseconds)
})

const childCompletion = (child) => new Promise((resolve) => {
  let completed = false
  const finish = (outcome) => {
    if (completed) return
    completed = true
    resolve(outcome)
  }
  child.once('error', () => finish({ kind: 'spawn_error' }))
  child.once('close', (code) => finish({ kind: 'close', code }))
})

const raceWithBoundedTimer = async (promise, timeoutMilliseconds) => {
  let timer
  const timeout = new Promise((resolve) => {
    timer = setTimeout(
      () => resolve({ kind: 'bounded_timeout' }),
      timeoutMilliseconds,
    )
  })
  const outcome = await Promise.race([promise, timeout])
  clearTimeout(timer)
  return outcome
}

const disposeChildHandle = (child) => {
  try { child.stdout?.destroy?.() } catch { /* sanitized failure boundary */ }
  try { child.stderr?.destroy?.() } catch { /* sanitized failure boundary */ }
  try { child.unref?.() } catch { /* sanitized failure boundary */ }
}

export const runExactPidTreeKill = async ({
  taskkillPath,
  targetProcessId,
  spawnProcess = spawn,
  timeoutMilliseconds = 15_000,
}) => {
  if (!Number.isSafeInteger(targetProcessId) || targetProcessId <= 0) {
    failStage(BROWSER_STAGE.edgeTermination)
  }
  let killer
  try {
    killer = spawnProcess(taskkillPath, [
      '/PID',
      String(targetProcessId),
      '/T',
      '/F',
    ], {
      shell: false,
      stdio: ['ignore', 'ignore', 'ignore'],
      windowsHide: true,
    })
  } catch {
    failStage(BROWSER_STAGE.edgeTermination)
  }
  const completion = childCompletion(killer)
  const outcome = await raceWithBoundedTimer(completion, timeoutMilliseconds)
  if (outcome.kind === 'bounded_timeout') {
    try { killer.kill?.() } catch { /* exact killer process only */ }
    disposeChildHandle(killer)
    failStage(BROWSER_STAGE.edgeTermination)
  }
  disposeChildHandle(killer)
  if (outcome.kind !== 'close' || outcome.code !== 0) {
    failStage(BROWSER_STAGE.edgeTermination)
  }
}

export const classifyCompletedBrowser = ({
  kind,
  code,
  stdout,
  outputExceeded,
}) => {
  if (kind === 'spawn_error') return BROWSER_STAGE.edgeSpawn
  if (kind !== 'close' || code !== 0) return BROWSER_STAGE.edgeExit
  if (outputExceeded) return BROWSER_STAGE.edgeOutputLimit
  if (
    typeof stdout !== 'string'
    || !stdout.includes('data-r67-status="passed"')
    || !stdout.includes('R67_BROWSER_HARNESS_PASS')
  ) return BROWSER_STAGE.edgeMarker
  return BROWSER_STAGE.passed
}

export const runBoundedEdge = async ({
  edgePath,
  edgeArguments,
  taskkillPath,
  spawnProcess = spawn,
  timeoutMilliseconds = 45_000,
  terminationTimeoutMilliseconds = 15_000,
  closeGraceMilliseconds = 5_000,
  maximumStdoutBytes = 16 * 1024 * 1024,
}) => {
  let browser
  try {
    browser = spawnProcess(edgePath, edgeArguments, {
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
  } catch {
    failStage(BROWSER_STAGE.edgeSpawn)
  }

  const stdoutChunks = []
  let stdoutBytes = 0
  let outputExceeded = false
  let signalOutputExceeded
  const outputExceededPromise = new Promise((resolve) => {
    signalOutputExceeded = resolve
  })
  browser.stdout?.on('data', (chunk) => {
    if (outputExceeded) return
    const boundedChunk = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    stdoutBytes += boundedChunk.length
    if (stdoutBytes > maximumStdoutBytes) {
      outputExceeded = true
      stdoutChunks.length = 0
      signalOutputExceeded({ kind: 'output_exceeded' })
      return
    }
    stdoutChunks.push(boundedChunk)
  })
  // Raw browser diagnostics can include local paths and runtime identifiers.
  // They are deliberately consumed and discarded, never logged or thrown.
  browser.stderr?.on('data', () => {})

  const completion = childCompletion(browser)
  let deadlineTimer
  const deadline = new Promise((resolve) => {
    deadlineTimer = setTimeout(
      () => resolve({ kind: 'browser_timeout' }),
      timeoutMilliseconds,
    )
  })
  const firstOutcome = await Promise.race([
    completion,
    deadline,
    outputExceededPromise,
  ])
  clearTimeout(deadlineTimer)

  if (
    firstOutcome.kind === 'browser_timeout'
    || firstOutcome.kind === 'output_exceeded'
  ) {
    const terminalStage = firstOutcome.kind === 'browser_timeout'
      ? BROWSER_STAGE.edgeTimeout
      : BROWSER_STAGE.edgeOutputLimit
    try {
      await runExactPidTreeKill({
        taskkillPath,
        targetProcessId: Number(browser.pid),
        spawnProcess,
        timeoutMilliseconds: terminationTimeoutMilliseconds,
      })
      const closed = await raceWithBoundedTimer(
        completion,
        closeGraceMilliseconds,
      )
      if (closed.kind === 'bounded_timeout') {
        failStage(BROWSER_STAGE.edgeTermination)
      }
    } catch (error) {
      try { browser.kill?.() } catch { /* exact child fallback only */ }
      disposeChildHandle(browser)
      if (error instanceof BrowserStageFailure) throw error
      failStage(BROWSER_STAGE.edgeTermination)
    }
    disposeChildHandle(browser)
    // This state is fixed before termination begins. A late close(0) cannot
    // turn a deadline or output-overflow run into a pass.
    failStage(terminalStage)
  }

  disposeChildHandle(browser)
  const stdout = Buffer.concat(stdoutChunks).toString('utf8')
  const stage = classifyCompletedBrowser({
    ...firstOutcome,
    stdout,
    outputExceeded,
  })
  if (stage !== BROWSER_STAGE.passed) failStage(stage)
}

export const cleanupProfileWithRetries = async (
  profileRoot,
  {
    removeDirectory = (candidate) => fs.promises.rm(candidate, {
      recursive: true,
      force: true,
    }),
    wait = waitForMilliseconds,
    retryScheduleMilliseconds = [100, 200, 400, 800, 1_000, 1_000],
  } = {},
) => {
  for (let attempt = 0; attempt <= retryScheduleMilliseconds.length; attempt += 1) {
    try {
      await removeDirectory(profileRoot)
      return attempt + 1
    } catch {
      if (attempt === retryScheduleMilliseconds.length) {
        failStage(BROWSER_STAGE.profileCleanup)
      }
      await wait(retryScheduleMilliseconds[attempt])
    }
  }
  failStage(BROWSER_STAGE.profileCleanup)
}

const createPrivateProfile = ({
  environment,
  fileSystem,
}) => {
  if (!environment.TEMP) failStage(BROWSER_STAGE.temporaryRoot)
  let temporaryRoot
  try {
    temporaryRoot = nativeRealPath(
      fileSystem,
      path.resolve(environment.TEMP),
    )
    const metadata = fileSystem.lstatSync(temporaryRoot)
    if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
      failStage(BROWSER_STAGE.temporaryRoot)
    }
  } catch (error) {
    if (error instanceof BrowserStageFailure) throw error
    failStage(BROWSER_STAGE.temporaryRoot)
  }

  let profileRoot
  try {
    profileRoot = fileSystem.mkdtempSync(
      path.join(temporaryRoot, 'etop-r68-edge-'),
    )
    const realProfileRoot = nativeRealPath(fileSystem, profileRoot)
    const profileRelative = path.relative(temporaryRoot, realProfileRoot)
    if (
      !profileRelative
      || profileRelative.startsWith(`..${path.sep}`)
      || profileRelative === '..'
      || path.isAbsolute(profileRelative)
    ) failStage(BROWSER_STAGE.profileCreation)
  } catch (error) {
    if (error instanceof BrowserStageFailure) throw error
    failStage(BROWSER_STAGE.profileCreation)
  }
  return profileRoot
}

export const runMandatoryWindowsBrowser = async ({
  environment = process.env,
  fileSystem = fs,
  spawnProcess = spawn,
} = {}) => {
  const edgeAllowlist = edgeProgramFilesAllowlist(environment)
  const edgePath = edgeAllowlist.find((candidate) => (
    validateInstalledEdge(candidate, edgeAllowlist, fileSystem)
  ))
  if (!edgePath) failStage(BROWSER_STAGE.edgeValidation)

  const taskkillPath = canonicalTaskkillPath(environment.SystemRoot)
  if (
    !taskkillPath
    || !validateInstalledTaskkill(
      taskkillPath,
      environment.SystemRoot,
      fileSystem,
    )
  ) failStage(BROWSER_STAGE.taskkillValidation)

  const profileRoot = createPrivateProfile({ environment, fileSystem })
  let primaryFailure = null
  try {
    await runBoundedEdge({
      edgePath,
      edgeArguments: [
        '--headless=new',
        '--disable-background-networking',
        '--disable-breakpad',
        '--disable-client-side-phishing-detection',
        '--disable-component-update',
        '--disable-crash-reporter',
        '--disable-default-apps',
        '--disable-domain-reliability',
        '--disable-extensions',
        '--disable-gpu',
        '--disable-sync',
        '--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE 127.0.0.1',
        '--metrics-recording-only',
        '--no-default-browser-check',
        '--no-first-run',
        '--no-proxy-server',
        '--safebrowsing-disable-auto-update',
        `--user-data-dir=${profileRoot}`,
        '--virtual-time-budget=15000',
        '--dump-dom',
        'http://127.0.0.1:5174/verification/r67-browser-harness.html',
      ],
      taskkillPath,
      spawnProcess,
    })
  } catch (error) {
    primaryFailure = error
  }
  try {
    await cleanupProfileWithRetries(profileRoot, {
      removeDirectory: (candidate) => fileSystem.promises.rm(candidate, {
        recursive: true,
        force: true,
      }),
    })
  } catch (error) {
    // Failure to remove the private browser profile is independently fatal.
    primaryFailure = error
  }
  if (primaryFailure) throw primaryFailure
}

const fakeMetadata = ({
  file = false,
  directory = false,
  symbolicLink = false,
  nlink = 1,
} = {}) => ({
  isFile: () => file,
  isDirectory: () => directory,
  isSymbolicLink: () => symbolicLink,
  nlink,
})

const fakeWindowsFileSystem = ({
  executable,
  executableMetadata,
  executableRealPath = executable,
  symbolicParent = '',
}) => {
  const executableIdentity = normalizeWindowsIdentity(executable)
  const realPaths = new Map([[executableIdentity, executableRealPath]])
  const metadata = new Map([[executableIdentity, executableMetadata]])
  let current = path.win32.dirname(executable)
  while (true) {
    const identity = normalizeWindowsIdentity(current)
    const isSymbolicParent = identity === normalizeWindowsIdentity(symbolicParent)
    metadata.set(identity, fakeMetadata({
      directory: true,
      symbolicLink: isSymbolicParent,
    }))
    realPaths.set(identity, current)
    const parent = path.win32.dirname(current)
    if (normalizeWindowsIdentity(parent) === identity) break
    current = parent
  }
  const realpathSync = () => { throw new Error('native realpath required') }
  realpathSync.native = (candidate) => {
    const value = realPaths.get(normalizeWindowsIdentity(candidate))
    if (!value) throw new Error('missing fake realpath')
    return value
  }
  return {
    lstatSync: (candidate) => {
      const value = metadata.get(normalizeWindowsIdentity(candidate))
      if (!value) throw new Error('missing fake metadata')
      return value
    },
    realpathSync,
  }
}

class FakeChild extends EventEmitter {
  constructor(processId) {
    super()
    this.pid = processId
    this.stdout = new EventEmitter()
    this.stderr = new EventEmitter()
    this.stdout.destroy = () => {}
    this.stderr.destroy = () => {}
    this.kill = () => true
    this.unref = () => {}
  }
}

const expectRunnerStage = async (promise, stage) => {
  await assert.rejects(
    promise,
    (error) => sanitizedBrowserStage(error) === stage,
  )
}

export const runBrowserRuntimeRegressions = async () => {
  const systemRoot = 'C:\\Windows'
  const taskkill = 'C:\\Windows\\System32\\taskkill.exe'

  for (const nlink of [0, 2]) {
    const fileSystem = fakeWindowsFileSystem({
      executable: taskkill,
      executableMetadata: fakeMetadata({ file: true, nlink }),
    })
    assert.equal(
      validateInstalledTaskkill(taskkill, systemRoot, fileSystem),
      true,
      'Canonical System32 taskkill accepts serviced hardlink metadata.',
    )
  }
  assert.equal(
    validateInstalledTaskkill(
      taskkill,
      systemRoot,
      fakeWindowsFileSystem({
        executable: taskkill,
        executableMetadata: fakeMetadata({ file: true, symbolicLink: true }),
      }),
    ),
    false,
  )
  assert.equal(
    validateInstalledTaskkill(
      taskkill,
      systemRoot,
      fakeWindowsFileSystem({
        executable: taskkill,
        executableMetadata: fakeMetadata({ file: true }),
        symbolicParent: 'C:\\Windows\\System32',
      }),
    ),
    false,
  )
  assert.equal(
    validateInstalledTaskkill(
      'C:\\Temp\\taskkill.exe',
      systemRoot,
      fakeWindowsFileSystem({
        executable: 'C:\\Temp\\taskkill.exe',
        executableMetadata: fakeMetadata({ file: true }),
        executableRealPath: taskkill,
      }),
    ),
    false,
  )
  assert.equal(
    validateInstalledTaskkill(
      taskkill,
      systemRoot,
      fakeWindowsFileSystem({
        executable: taskkill,
        executableMetadata: fakeMetadata({ directory: true }),
      }),
    ),
    false,
  )
  assert.equal(
    validateInstalledTaskkill(
      taskkill,
      systemRoot,
      fakeWindowsFileSystem({
        executable: taskkill,
        executableMetadata: fakeMetadata({ file: true }),
        executableRealPath: 'C:\\Windows\\WinSxS\\taskkill.exe',
      }),
    ),
    false,
  )

  const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
  const edgeAllowlist = edgeProgramFilesAllowlist({
    'PROGRAMFILES(X86)': 'C:\\Program Files (x86)',
    PROGRAMFILES: 'C:\\Program Files',
  })
  assert.deepEqual(edgeAllowlist, [
    edge,
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ])
  assert.equal(
    validateInstalledEdge(
      edge,
      edgeAllowlist,
      fakeWindowsFileSystem({
        executable: edge,
        executableMetadata: fakeMetadata({ file: true, nlink: 1 }),
      }),
    ),
    true,
  )
  assert.equal(
    validateInstalledEdge(
      edge,
      edgeAllowlist,
      fakeWindowsFileSystem({
        executable: edge,
        executableMetadata: fakeMetadata({ file: true, nlink: 2 }),
      }),
    ),
    false,
  )
  assert.deepEqual(
    edgeProgramFilesAllowlist({
      PROGRAMFILES: 'C:\\Untrusted\\Program Files',
      'PROGRAMFILES(X86)': 'C:\\Temp',
    }),
    [],
  )

  const successfulBrowser = new FakeChild(4101)
  const successfulSpawnCalls = []
  const successfulSpawn = (executable, arguments_, options) => {
    successfulSpawnCalls.push({ executable, arguments_, options })
    queueMicrotask(() => {
      successfulBrowser.stdout.emit(
        'data',
        Buffer.from('<main data-r67-status="passed">R67_BROWSER_HARNESS_PASS</main>'),
      )
      successfulBrowser.emit('close', 0)
    })
    return successfulBrowser
  }
  await runBoundedEdge({
    edgePath: edge,
    edgeArguments: ['--synthetic-regression'],
    taskkillPath: taskkill,
    spawnProcess: successfulSpawn,
    timeoutMilliseconds: 25,
  })
  assert.equal(successfulSpawnCalls.length, 1)
  assert.equal(successfulSpawnCalls[0].options.shell, false)

  const timeoutBrowser = new FakeChild(4202)
  const timeoutSpawnCalls = []
  const timeoutSpawn = (executable, arguments_, options) => {
    timeoutSpawnCalls.push({ executable, arguments_, options })
    if (executable === edge) return timeoutBrowser
    const killer = new FakeChild(4303)
    queueMicrotask(() => {
      killer.emit('close', 0)
      // A successful close after the deadline must not rescue the run.
      timeoutBrowser.emit('close', 0)
    })
    return killer
  }
  await expectRunnerStage(runBoundedEdge({
    edgePath: edge,
    edgeArguments: ['--synthetic-regression'],
    taskkillPath: taskkill,
    spawnProcess: timeoutSpawn,
    timeoutMilliseconds: 1,
    terminationTimeoutMilliseconds: 25,
    closeGraceMilliseconds: 25,
  }), BROWSER_STAGE.edgeTimeout)
  assert.equal(timeoutSpawnCalls.length, 2)
  assert.deepEqual(timeoutSpawnCalls[1].arguments_, [
    '/PID',
    '4202',
    '/T',
    '/F',
  ])
  assert.equal(timeoutSpawnCalls[1].options.shell, false)

  const rejectedCases = [
    {
      stage: BROWSER_STAGE.edgeSpawn,
      finish: (browser) => browser.emit('error', new Error('private spawn error')),
    },
    {
      stage: BROWSER_STAGE.edgeExit,
      finish: (browser) => browser.emit('close', 9),
    },
    {
      stage: BROWSER_STAGE.edgeMarker,
      finish: (browser) => {
        browser.stdout.emit('data', Buffer.from('<main>private DOM</main>'))
        browser.emit('close', 0)
      },
    },
  ]
  for (const [index, browserCase] of rejectedCases.entries()) {
    const rejectedBrowser = new FakeChild(4400 + index)
    const rejectedSpawn = () => {
      queueMicrotask(() => browserCase.finish(rejectedBrowser))
      return rejectedBrowser
    }
    await expectRunnerStage(runBoundedEdge({
      edgePath: edge,
      edgeArguments: ['--synthetic-regression'],
      taskkillPath: taskkill,
      spawnProcess: rejectedSpawn,
      timeoutMilliseconds: 25,
    }), browserCase.stage)
  }

  const overflowBrowser = new FakeChild(4504)
  const overflowSpawnCalls = []
  const overflowSpawn = (executable, arguments_, options) => {
    overflowSpawnCalls.push({ executable, arguments_, options })
    if (executable === edge) {
      queueMicrotask(() => {
        overflowBrowser.stdout.emit('data', Buffer.from('12345'))
      })
      return overflowBrowser
    }
    const killer = new FakeChild(4505)
    queueMicrotask(() => {
      killer.emit('close', 0)
      overflowBrowser.emit('close', 0)
    })
    return killer
  }
  await expectRunnerStage(runBoundedEdge({
    edgePath: edge,
    edgeArguments: ['--synthetic-regression'],
    taskkillPath: taskkill,
    spawnProcess: overflowSpawn,
    timeoutMilliseconds: 25,
    terminationTimeoutMilliseconds: 25,
    closeGraceMilliseconds: 25,
    maximumStdoutBytes: 4,
  }), BROWSER_STAGE.edgeOutputLimit)
  assert.deepEqual(overflowSpawnCalls[1].arguments_, [
    '/PID',
    '4504',
    '/T',
    '/F',
  ])

  const failedKillBrowser = new FakeChild(4606)
  let exactFallbackKills = 0
  failedKillBrowser.kill = () => {
    exactFallbackKills += 1
    return true
  }
  const failedKillSpawn = (executable) => {
    if (executable === edge) return failedKillBrowser
    const killer = new FakeChild(4607)
    queueMicrotask(() => killer.emit('close', 1))
    return killer
  }
  await expectRunnerStage(runBoundedEdge({
    edgePath: edge,
    edgeArguments: ['--synthetic-regression'],
    taskkillPath: taskkill,
    spawnProcess: failedKillSpawn,
    timeoutMilliseconds: 1,
    terminationTimeoutMilliseconds: 25,
    closeGraceMilliseconds: 25,
  }), BROWSER_STAGE.edgeTermination)
  assert.equal(exactFallbackKills, 1)

  const hungKiller = new FakeChild(4708)
  let hungKillerFallbacks = 0
  hungKiller.kill = () => {
    hungKillerFallbacks += 1
    return true
  }
  await expectRunnerStage(runExactPidTreeKill({
    taskkillPath: taskkill,
    targetProcessId: 4707,
    spawnProcess: () => hungKiller,
    timeoutMilliseconds: 1,
  }), BROWSER_STAGE.edgeTermination)
  assert.equal(hungKillerFallbacks, 1)

  const noCloseBrowser = new FakeChild(4809)
  let noCloseFallbacks = 0
  noCloseBrowser.kill = () => {
    noCloseFallbacks += 1
    return true
  }
  const noCloseSpawn = (executable) => {
    if (executable === edge) return noCloseBrowser
    const killer = new FakeChild(4810)
    queueMicrotask(() => killer.emit('close', 0))
    return killer
  }
  await expectRunnerStage(runBoundedEdge({
    edgePath: edge,
    edgeArguments: ['--synthetic-regression'],
    taskkillPath: taskkill,
    spawnProcess: noCloseSpawn,
    timeoutMilliseconds: 1,
    terminationTimeoutMilliseconds: 25,
    closeGraceMilliseconds: 1,
  }), BROWSER_STAGE.edgeTermination)
  assert.equal(noCloseFallbacks, 1)

  let transientCleanupAttempts = 0
  assert.equal(await cleanupProfileWithRetries('synthetic-profile', {
    removeDirectory: async () => {
      transientCleanupAttempts += 1
      if (transientCleanupAttempts < 3) throw new Error('synthetic busy')
    },
    wait: async () => {},
    retryScheduleMilliseconds: [0, 0],
  }), 3)
  await expectRunnerStage(cleanupProfileWithRetries('synthetic-profile', {
    removeDirectory: async () => { throw new Error('synthetic permanent') },
    wait: async () => {},
    retryScheduleMilliseconds: [0],
  }), BROWSER_STAGE.profileCleanup)

  assert.equal(classifyCompletedBrowser({
    kind: 'close',
    code: 0,
    stdout: '<main data-r67-status="passed">R67_BROWSER_HARNESS_PASS</main>',
    outputExceeded: false,
  }), BROWSER_STAGE.passed)
  assert.equal(classifyCompletedBrowser({
    kind: 'close', code: 0, stdout: '', outputExceeded: false,
  }), BROWSER_STAGE.edgeMarker)
  assert.equal(classifyCompletedBrowser({
    kind: 'close', code: 1, stdout: 'private data', outputExceeded: false,
  }), BROWSER_STAGE.edgeExit)
  assert.equal(classifyCompletedBrowser({
    kind: 'spawn_error', code: null, stdout: '', outputExceeded: false,
  }), BROWSER_STAGE.edgeSpawn)
  assert.equal(
    sanitizedBrowserStage(new Error('private path and runtime identifier')),
    BROWSER_STAGE.internal,
  )
}
