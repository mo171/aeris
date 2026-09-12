import { useEffect, useState } from "react";
import { X, ArrowRightLeft, Target } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { diffVersions } from "../../lib/version-diff";
import type { InvestigationVersion, DiffSection } from "../../types/version.types";

interface VersionCompareSheetProps {
  versionAId: string | null;
  versionBId: string | null;
  versions: InvestigationVersion[];
  onClose: () => void;
}

export function VersionCompareSheet({ versionAId, versionBId, versions, onClose }: VersionCompareSheetProps) {
  const [diffSections, setDiffSections] = useState<DiffSection[]>([]);
  
  const vA = versions.find(v => v.id === versionAId);
  const vB = versions.find(v => v.id === versionBId);

  useEffect(() => {
    if (vA && vB) {
      // Sort chronologically so 'before' is older, 'after' is newer
      const isAOlder = new Date(vA.createdAt) < new Date(vB.createdAt);
      const older = isAOlder ? vA : vB;
      const newer = isAOlder ? vB : vA;
      
      setDiffSections(diffVersions(older, newer));
    }
  }, [vA, vB]);

  const open = Boolean(versionAId && versionBId && vA && vB);

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent className="w-[400px] sm:w-[540px] overflow-y-auto">
        <SheetHeader className="mb-6">
          <SheetTitle className="flex items-center gap-2">
            <ArrowRightLeft className="size-4" />
            Compare Versions
          </SheetTitle>
          {vA && vB && (
            <SheetDescription>
              Comparing <span className="font-medium text-foreground">{vA.label}</span> and <span className="font-medium text-foreground">{vB.label}</span>
            </SheetDescription>
          )}
        </SheetHeader>

        <div className="space-y-6">
          {diffSections.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 text-center bg-muted/30 rounded-lg border border-dashed">
              <Target className="size-8 text-muted-foreground mb-3" />
              <p className="text-sm font-medium">No differences found.</p>
              <p className="text-xs text-muted-foreground mt-1">These versions are identical.</p>
            </div>
          ) : (
            diffSections.map((section) => (
              <div key={section.kind} className="space-y-3">
                <h3 className="text-sm font-semibold tracking-tight text-foreground border-b pb-1">
                  {section.title}
                </h3>
                <div className="rounded-md border bg-card text-card-foreground shadow-sm">
                  <div className="grid grid-cols-12 text-xs font-medium text-muted-foreground border-b bg-muted/30 p-2">
                    <div className="col-span-4">Property</div>
                    <div className="col-span-4 pl-2">Before</div>
                    <div className="col-span-4 pl-2">After</div>
                  </div>
                  <div className="divide-y">
                    {section.rows.map((row, i) => (
                      <div key={i} className="grid grid-cols-12 text-sm p-2 items-center">
                        <div className="col-span-4 font-medium text-xs pr-2 truncate" title={row.label}>
                          {row.label}
                        </div>
                        <div className="col-span-4 pl-2 border-l">
                          <span className="bg-red-500/10 text-red-600 dark:text-red-400 px-1.5 py-0.5 rounded font-mono text-xs">
                            {row.before}
                          </span>
                        </div>
                        <div className="col-span-4 pl-2 border-l">
                          <span className="bg-green-500/10 text-green-600 dark:text-green-400 px-1.5 py-0.5 rounded font-mono text-xs">
                            {row.after}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
