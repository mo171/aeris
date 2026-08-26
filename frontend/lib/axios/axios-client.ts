// lib/axios/axios-client.ts — THE http client. Exactly one axios instance exists in this application.
//
// what  : Configures base URL, timeout, default headers, and the interceptors that normalise every error.
// where : Imported only by feature service files and by the Phase 1 mock bridge. Components and hooks must
//         never import it — that rule is what keeps the transport swappable.
// how   : The response interceptor rejects with ApiError, so every consumer downstream handles one error
//         shape. The request interceptor is where auth headers will attach once the auth feature lands.

import axios, { type AxiosInstance } from "axios";

import { env } from "@/lib/env";

import { toApiError } from "./api-error";

export const apiClient: AxiosInstance = axios.create({
  baseURL: env.NEXT_PUBLIC_API_URL,
  timeout: env.NEXT_PUBLIC_API_TIMEOUT_MS,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(toApiError(error)),
);
