// lib/axios/parse-api-response.ts — validates every backend payload at the transport boundary.
//
// what  : Runs a Zod schema over a raw response body and converts a schema failure into an ApiError.
// where : Called by every service function immediately after the request resolves.
// how   : A contract violation is a transport failure, not a programming error, so it must reach the UI as
//         an ApiError like any 500 would — that way ErrorState renders it and the query retry policy
//         applies. Throwing a raw ZodError here would escape both of those paths and blank the panel.

import type { ZodType } from "zod";

import { ApiError } from "./api-error";

export const CONTRACT_VIOLATION_CODE = "CONTRACT_VIOLATION";

export function parseApiResponse<TOutput>(
  schema: ZodType<TOutput>,
  payload: unknown,
  endpointDescription: string,
): TOutput {
  const result = schema.safeParse(payload);

  if (!result.success) {
    throw new ApiError({
      message: `The response from ${endpointDescription} did not match the expected contract.`,
      code: CONTRACT_VIOLATION_CODE,
      status: 502,
      details: result.error.issues,
    });
  }

  return result.data;
}
