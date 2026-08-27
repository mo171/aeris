// features/investigation/components/report/ReportDrawer.tsx — the intelligence report, assembling live.
//
// what  : A side drawer where the report builds section by section as the backend emits it, ending with
//         the trace id and the three export formats.
// where : Opened by the investigation.openReport command from the header or the palette.
// how   : Sections appear as they arrive rather than all at once. A report that materialises whole reads
//         as a template being filled in; one that builds in front of the operator reads as a document
//         being written from the run that just happened — which is what it is.
//
//         Exports are ordinary links rather than fetched blobs. The file is generated server-side with the
//         trace id embedded, and letting the browser fetch it directly keeps a potentially large PDF out
//         of page memory entirely.
//
//         Generation starts when the drawer opens and is aborted when it closes, so dismissing it actually
//         stops the work instead of hiding it.

"use client";

import { Download, FileJson, FileText, Map } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { formatAbsoluteDate } from "@/lib/formatters";

import { useReport } from "../../hooks/use-report";
import { useInvestigationStore } from "../../store/investigation-store";
import type { ReportExportFormat } from "../../types/report.types";

const EXPORT_FORMATS: readonly { format: ReportExportFormat; label: string; icon: typeof FileText }[] =
  [
    { format: "pdf", label: "PDF", icon: FileText },
    { format: "json", label: "JSON", icon: FileJson },
    { format: "geojson", label: "GeoJSON", icon: Map },
  ];

interface ReportDrawerProps {
  investigationId: string;
  investigationName: string;
}

export function ReportDrawer({ investigationId, investigationName }: ReportDrawerProps) {
  const isOpen = useInvestigationStore((state) => state.isReportOpen);
  const setReportOpen = useInvestigationStore((state) => state.setReportOpen);
  const { title, traceId, sections, isGenerating, error, generate, exportUrlFor } =
    useReport(investigationId);

  useEffect(() => {
    if (isOpen) {
      generate();
    }
  }, [generate, isOpen]);

  return (
    <Sheet open={isOpen} onOpenChange={setReportOpen}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{title ?? `${investigationName} — intelligence report`}</SheetTitle>
          <SheetDescription>
            {isGenerating
              ? "Assembling from the analysis that just ran."
              : `Generated ${formatAbsoluteDate(new Date().toISOString())}.`}
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-4">
          {error ? (
            <p className="rounded-md border border-aeris-red/40 bg-aeris-red/5 p-3 text-sm text-foreground">
              {error}
            </p>
          ) : null}

          <div className="flex flex-col gap-4 pb-4">
            {sections.map((section) => (
              <section key={section.id}>
                <h3 className="aeris-technical">{section.heading}</h3>
                <p className="mt-1 text-sm leading-relaxed whitespace-pre-line text-muted-foreground">
                  {section.body}
                </p>
              </section>
            ))}

            {isGenerating ? (
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                <Spinner className="size-3" />
                Writing the next section…
              </span>
            ) : null}
          </div>
        </div>

        <footer className="flex flex-col gap-2 border-t border-border-soft p-4">
          {traceId ? (
            <p className="font-mono text-[10px] text-muted-foreground/70">
              Every figure in this report resolves through trace {traceId}.
            </p>
          ) : null}

          <div className="flex flex-wrap gap-1.5">
            {EXPORT_FORMATS.map(({ format, label, icon: Icon }) => (
              <Button key={format} type="button" size="sm" variant="outline" asChild>
                <a href={exportUrlFor(format)} download>
                  <Icon />
                  {label}
                  <Download className="opacity-60" />
                </a>
              </Button>
            ))}
          </div>
        </footer>
      </SheetContent>
    </Sheet>
  );
}
