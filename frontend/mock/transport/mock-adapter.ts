// mock/transport/mock-adapter.ts — the in-memory axios adapter that stands in for the AERIS backend.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : An axios adapter that resolves requests from the mock route table instead of the network,
//         complete with artificial latency, upload progress and 404s for unmapped paths.
// where : Installed onto the shared axios instance by mock/index.ts.
// how   : Intercepting at the adapter layer — below services, hooks, stores and components — is what keeps
//         the rest of the codebase completely free of mock awareness. Every consumer writes the real call
//         and handles the real response shape; only this file knows the backend is not there yet.
//         Latency is deliberate: without it, loading skeletons never render and would ship untested.

import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosHeaders } from "axios";

import { env } from "@/lib/env";

import { MOCK_ROUTES, type MockResponse } from "./routes";

const UPLOAD_PROGRESS_TICK_COUNT = 12;
const UPLOAD_TOTAL_DURATION_MS = 1_400;

export const mockAxiosAdapter: AxiosAdapter = async (config) => {
  const { pathname } = resolveRequestUrl(config);
  const method = (config.method ?? "get").toUpperCase();

  await simulateLatency();

  if (method === "PUT") {
    await simulateUploadProgress(config);
  }

  const route = MOCK_ROUTES.find(
    (candidate) => candidate.method === method && candidate.match(pathname) !== null,
  );

  if (!route) {
    return buildResponse(config, {
      status: 404,
      data: {
        message: `No mock route is registered for ${method} ${pathname}.`,
        code: "MOCK_ROUTE_NOT_FOUND",
        status: 404,
      },
    });
  }

  const result = route.handle({
    pathname,
    query: normaliseQuery(config.params),
    body: parseRequestBody(config.data),
    pathParameters: route.match(pathname) ?? [],
  });

  return buildResponse(config, result);
};

function resolveRequestUrl(config: InternalAxiosRequestConfig): { pathname: string } {
  const rawUrl = config.url ?? "";
  const isAbsolute = /^https?:\/\//i.test(rawUrl);

  try {
    const url = isAbsolute
      ? new URL(rawUrl)
      : new URL(rawUrl, config.baseURL ?? env.NEXT_PUBLIC_API_URL);
    return { pathname: url.pathname };
  } catch {
    return { pathname: rawUrl };
  }
}

function normaliseQuery(params: unknown): Record<string, string | undefined> {
  if (!params || typeof params !== "object") {
    return {};
  }

  const normalised: Record<string, string | undefined> = {};
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    normalised[key] = value === undefined || value === null ? undefined : String(value);
  }
  return normalised;
}

function parseRequestBody(data: unknown): unknown {
  if (typeof data !== "string") {
    return data;
  }

  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

async function simulateLatency(): Promise<void> {
  const baseLatency = env.NEXT_PUBLIC_MOCK_LATENCY_MS;
  if (baseLatency <= 0) {
    return;
  }

  // Jitter keeps every panel from resolving on the same frame, which is what real networks do and what
  // makes staggered loading states worth testing.
  const jitter = Math.random() * baseLatency * 0.5;
  await new Promise((resolve) => window.setTimeout(resolve, baseLatency + jitter));
}

async function simulateUploadProgress(config: InternalAxiosRequestConfig): Promise<void> {
  const onUploadProgress = config.onUploadProgress;
  if (!onUploadProgress) {
    return;
  }

  const total = config.data instanceof File ? config.data.size : 1_000_000;
  const tickDelayMs = UPLOAD_TOTAL_DURATION_MS / UPLOAD_PROGRESS_TICK_COUNT;

  for (let tick = 1; tick <= UPLOAD_PROGRESS_TICK_COUNT; tick += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, tickDelayMs));
    onUploadProgress({
      loaded: Math.round((total * tick) / UPLOAD_PROGRESS_TICK_COUNT),
      total,
      bytes: Math.round(total / UPLOAD_PROGRESS_TICK_COUNT),
      lengthComputable: true,
    });
  }
}

function buildResponse(
  config: InternalAxiosRequestConfig,
  result: MockResponse,
): Promise<AxiosResponse> {
  const response: AxiosResponse = {
    data: result.data,
    status: result.status,
    statusText: result.status >= 400 ? "Error" : "OK",
    headers: new AxiosHeaders({ "content-type": "application/json" }),
    config,
  };

  if (result.status >= 400) {
    const error = new Error(`Request failed with status code ${result.status}`) as Error & {
      isAxiosError: boolean;
      response: AxiosResponse;
      config: InternalAxiosRequestConfig;
      toJSON: () => object;
    };
    error.isAxiosError = true;
    error.response = response;
    error.config = config;
    error.toJSON = () => ({ message: error.message });
    return Promise.reject(error);
  }

  return Promise.resolve(response);
}
