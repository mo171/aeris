import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Check, ArrowRightLeft, Clock, Save } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { dispatchCommand } from "@/lib/command-bus";
import type { InvestigationVersion } from "../../types/version.types";
import { SaveVersionDialog } from "./SaveVersionDialog";

interface VersionListPopoverProps {
  versions: InvestigationVersion[];
  children: React.ReactNode;
}

export function VersionListPopover({ versions, children }: VersionListPopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedVersionIds, setSelectedVersionIds] = useState<Set<string>>(new Set());
  const [isSaveDialogOpen, setIsSaveDialogOpen] = useState(false);

  const toggleSelection = (id: string) => {
    const next = new Set(selectedVersionIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      if (next.size < 2) {
        next.add(id);
      }
    }
    setSelectedVersionIds(next);
  };

  const handleCompare = () => {
    if (selectedVersionIds.size !== 2) return;
    const [versionAId, versionBId] = Array.from(selectedVersionIds);
    
    void dispatchCommand(COMMAND_IDS.investigation.compareVersions, {
      versionAId,
      versionBId,
    });
    setIsOpen(false);
  };

  const handleRestore = (versionId: string) => {
    void dispatchCommand(COMMAND_IDS.investigation.restoreVersion, {
      versionId,
    });
    setIsOpen(false);
  };

  return (
    <>
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger asChild>
          {children}
        </PopoverTrigger>
        <PopoverContent className="w-80 p-0" align="start">
          <div className="flex flex-col">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <span className="font-semibold text-sm">Versions</span>
              <Button 
                variant="ghost" 
                size="sm" 
                className="h-7 text-xs px-2"
                onClick={() => setIsSaveDialogOpen(true)}
              >
                <Save className="size-3 mr-1" />
                Save current
              </Button>
            </div>
            
            <div className="max-h-[300px] overflow-y-auto">
              {versions.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">
                  No versions saved yet.
                </div>
              ) : (
                <div className="flex flex-col divide-y">
                  {versions.slice().reverse().map((version) => (
                    <div key={version.id} className="flex flex-col p-3 hover:bg-muted/50 transition-colors">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2">
                          <Checkbox 
                            id={`select-${version.id}`}
                            checked={selectedVersionIds.has(version.id)}
                            onCheckedChange={() => toggleSelection(version.id)}
                            disabled={!selectedVersionIds.has(version.id) && selectedVersionIds.size >= 2}
                            className="mt-1"
                          />
                          <div className="flex flex-col">
                            <label 
                              htmlFor={`select-${version.id}`}
                              className="text-sm font-medium leading-none cursor-pointer"
                            >
                              {version.label}
                            </label>
                            <span className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                              <Clock className="size-3" />
                              {formatDistanceToNow(new Date(version.createdAt), { addSuffix: true })}
                              <span className="mx-1">·</span>
                              <span className="capitalize">{version.actor}</span>
                            </span>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs"
                          onClick={() => handleRestore(version.id)}
                        >
                          Restore
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="border-t p-3">
              <Button 
                className="w-full" 
                disabled={selectedVersionIds.size !== 2}
                onClick={handleCompare}
              >
                <ArrowRightLeft className="size-4 mr-2" />
                Compare {selectedVersionIds.size}/2
              </Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>

      <SaveVersionDialog 
        open={isSaveDialogOpen} 
        onOpenChange={setIsSaveDialogOpen} 
      />
    </>
  );
}
