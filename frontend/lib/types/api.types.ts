// lib/types/api.types.ts — shared transport-level shapes every service and hook speaks.
//
// what  : Defines the envelope, cursor pagination and error contracts used by every AERIS endpoint.
// where : Imported by lib/axios, every feature service, and every TanStack Query hook. Keeping these here
//         means a backend contract change is a one-file edit rather than a sweep through the features.
// how   : The backend returns a bare resource for single reads and a CursorPage<T> for collections.
//         Cursor (not offset) pagination is mandatory — the imagery catalogue is unbounded and offset
//         pagination breaks under concurrent writes.

/** A single page of a cursor-paginated collection. */
export interface CursorPage<TItem> {
  items: TItem[];
  /** Opaque token for the next page. `null` means the caller has reached the end. */
  nextCursor: string | null;
  /** Total matching records when the backend can compute it cheaply; otherwise null. */
  totalCount: number | null;
}

/** Query parameters accepted by every cursor-paginated endpoint. */
export interface CursorPageRequest {
  cursor?: string | null;
  limit?: number;
  search?: string;
}

/** Normalised error shape produced by lib/axios/api-error.ts, regardless of transport failure mode. */
export interface ApiErrorPayload {
  message: string;
  code: string;
  status: number;
  details?: unknown;
}

/** Generic option shape for selects, filters and chips. */
export interface SelectOption<TValue extends string = string> {
  value: TValue;
  label: string;
  description?: string;
}
