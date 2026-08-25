export type ModuleState =
  | "registered"
  | "configured"
  | "starting"
  | "running"
  | "stopping"
  | "stopped"
  | "failed"
  | "disabled"
  | string;

export interface LifecycleTiming {
  name: string;
  duration_ms: number;
  succeeded: boolean;
  error: string | null;
}

export interface PlatformModule {
  name: string;
  display_name: string;
  version: string;
  state: ModuleState;
  enabled: boolean;
  dependencies: string[];
  healthy: boolean;
  health_message: string | null;
  last_error: string | null;
}

export interface ModuleDiscoveryFailure {
  package_name: string;
  error_type: string;
  message: string;
}

export interface ModuleDiscovery {
  completed: boolean;
  discovered: number;
  scanned_packages: string[];
  skipped_packages: string[];
  failures: ModuleDiscoveryFailure[];
}

export interface LegacyModuleStatus {
  key: string;
  name: string;
  version: string;
  enabled: boolean;
  state: string;
  message: string;
  dependencies: string[];
}

export interface PlatformHealth {
  platform: string;
  state: string;
  version: string;
  ready: boolean;
  started_at: string | null;
  stopped_at: string | null;
  startup_duration_ms: number | null;
  shutdown_duration_ms: number | null;
  uptime_seconds: number;
  last_error: string | null;

  lifecycle_timings: LifecycleTiming[];

  services: {
    registered: number;
    singletons: number;
    transients: number;
    initialized: number;
    registry_frozen: boolean;
  };

  modules: {
    registered: number;
    running: number;
    failed: number;
    items: PlatformModule[];
  };

  event_bus: {
    running: boolean;
    subscriptions: number;
    enabled_subscriptions: number;
    published_events: number;
    failed_handlers: number;
    history_entries: number;
    history_limit: number;
    concurrent_handlers: boolean;
  };

  module_discovery: ModuleDiscovery;

  legacy_modules: {
    summary: {
      total: number;
      healthy: number;
      degraded: number;
      failed: number;
      disabled: number;
    };
    modules: LegacyModuleStatus[];
  };
}

export interface PlatformService {
  key: string;
  lifetime: string;
  implementation: string | null;
  initialized: boolean;
  metadata: Record<string, unknown>;
}

export interface PlatformServicesResponse {
  registry_frozen: boolean;
  services: PlatformService[];
}

export interface PlatformEvent {
  event_id: string;
  event_name: string;
  event_type: string;
  source: string | null;
  occurred_at: string;
  published_at: string;
  duration_ms: number;
  subscriber_count: number;
  succeeded_count: number;
  failed_count: number;
  correlation_id: string | null;
  causation_id: string | null;
}

export interface PlatformEventsResponse {
  running: boolean;
  diagnostics: Record<string, unknown>;
  recent_events: PlatformEvent[];
}

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

async function requestJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    const detail = await response.text();

    throw new Error(
      detail ||
        `Platform request failed with status ${response.status}.`,
    );
  }

  return (await response.json()) as T;
}

export function getPlatformHealth(
  signal?: AbortSignal,
): Promise<PlatformHealth> {
  return requestJson<PlatformHealth>(
    "/api/v1/platform/health",
    signal,
  );
}

export function getPlatformServices(
  signal?: AbortSignal,
): Promise<PlatformServicesResponse> {
  return requestJson<PlatformServicesResponse>(
    "/api/v1/platform/services",
    signal,
  );
}

export function getPlatformEvents(
  signal?: AbortSignal,
): Promise<PlatformEventsResponse> {
  return requestJson<PlatformEventsResponse>(
    "/api/v1/platform/events",
    signal,
  );
}