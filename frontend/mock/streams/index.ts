// mock/streams/index.ts — routes a mock stream request to the right scripted transport.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : One StreamTransport that dispatches on the request path — assistant, analysis run, or report.
// where : Installed onto lib/streaming by mock/index.ts.
// how   : lib/streaming holds a single transport slot, and the application now has three streaming
//         endpoints. Rather than widening that slot into a registry the live code has no use for, the mock
//         does its own dispatch here. The seam stays one line, and Phase 2 deletes this file along with
//         everything else in /mock.
//
//         Paths are matched against the same REST_API registry the services call, so a renamed endpoint
//         cannot leave the mock silently answering the wrong route.

import { REST_API } from "@/lib/constants/rest.api";
import type { StreamRequestConfig, StreamTransport } from "@/lib/streaming/stream-client";

import { mockAnalysisStream } from "./analysis-stream";
import { mockAssistantStreamTransport } from "./assistant-stream";
import { mockReportStream } from "./report-stream";

const RUN_PATH_PATTERN = /\/investigations\/[^/]+\/runs$/;
const REPORT_PATH_PATTERN = /\/investigations\/[^/]+\/report$/;

export const mockStreamTransport: StreamTransport = async (config: StreamRequestConfig) => {
  if (config.path === REST_API.assistant.stream) {
    return mockAssistantStreamTransport(config);
  }

  if (RUN_PATH_PATTERN.test(config.path)) {
    return mockAnalysisStream(config);
  }

  if (REPORT_PATH_PATTERN.test(config.path)) {
    return mockReportStream(config);
  }

  throw new Error(`No mock stream is registered for ${config.path}`);
};
