// components/sharedUI/functionalComponent/feedback/ErrorState.tsx — a failed data surface, with a way out.
//
// what  : Renders an error message, its transport code, and a retry affordance when retrying can help.
// where : Rendered by any panel whose query has failed.
// how   : It reads ApiError specifically so it can show the backend error code and suppress the retry
//         button on non-retryable failures — offering "Try again" on a 400 teaches operators to distrust
//         the button. Anything that is not an ApiError degrades to a generic message rather than throwing.

import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/axios/api-error";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({ error, onRetry, className }: ErrorStateProps) {
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError?.message ?? "Something went wrong loading this panel.";
  const canRetry = Boolean(onRetry) && (apiError === null || apiError.isRetryable);

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-10 text-center",
        className,
      )}
    >
      <span className="flex size-9 items-center justify-center rounded-md border border-aeris-red/35 bg-aeris-red/10">
        <TriangleAlert className="size-4 text-aeris-red" aria-hidden="true" />
      </span>
      <p className="max-w-[30ch] text-[11px] leading-relaxed text-foreground">{message}</p>
      {apiError ? (
        <p className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
          {apiError.code}
          {apiError.status > 0 ? ` · ${apiError.status}` : ""}
        </p>
      ) : null}
      {canRetry ? (
        <Button size="xs" variant="outline" onClick={onRetry} className="mt-1">
          Try again
        </Button>
      ) : null}
    </div>
  );
}
