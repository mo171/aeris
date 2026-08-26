// lib/axios/api-error.ts — one error type for every failure mode the transport can produce.
//
// what  : ApiError class plus a normaliser that converts axios errors, network failures, timeouts and
//         unknown throwables into a single predictable shape.
// where : Thrown by the axios response interceptor, caught by TanStack Query, rendered by ErrorState.
// how   : UI must be able to branch on `status` and `code` without knowing axios exists. Every error the
//         app surfaces therefore passes through toApiError() exactly once, at the transport boundary.

import { isAxiosError } from "axios";

import type { ApiErrorPayload } from "@/lib/types/api.types";

export const API_ERROR_CODES = {
  network: "NETWORK_ERROR",
  timeout: "TIMEOUT",
  cancelled: "CANCELLED",
  unknown: "UNKNOWN_ERROR",
} as const;

export class ApiError extends Error implements ApiErrorPayload {
  readonly code: string;
  readonly status: number;
  readonly details?: unknown;

  constructor({ message, code, status, details }: ApiErrorPayload) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }

  /** True when retrying could plausibly succeed — drives the retry affordance in ErrorState. */
  get isRetryable(): boolean {
    return this.status === 0 || this.status === 408 || this.status === 429 || this.status >= 500;
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }

  if (isAxiosError(error)) {
    if (error.code === "ECONNABORTED") {
      return new ApiError({
        message: "The request timed out before the server responded.",
        code: API_ERROR_CODES.timeout,
        status: 408,
      });
    }

    if (error.code === "ERR_CANCELED") {
      return new ApiError({
        message: "Request cancelled.",
        code: API_ERROR_CODES.cancelled,
        status: 0,
      });
    }

    const response = error.response;
    if (!response) {
      return new ApiError({
        message: "Cannot reach the AERIS backend.",
        code: API_ERROR_CODES.network,
        status: 0,
      });
    }

    const payload = response.data as Partial<ApiErrorPayload> | undefined;
    return new ApiError({
      message: payload?.message ?? error.message ?? "The request failed.",
      code: payload?.code ?? `HTTP_${response.status}`,
      status: response.status,
      details: payload?.details,
    });
  }

  return new ApiError({
    message: error instanceof Error ? error.message : "An unexpected error occurred.",
    code: API_ERROR_CODES.unknown,
    status: 0,
  });
}
