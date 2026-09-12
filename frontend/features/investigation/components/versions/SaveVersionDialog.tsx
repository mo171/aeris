import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { dispatchCommand } from "@/lib/command-bus";

interface SaveVersionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SaveVersionDialog({ open, onOpenChange }: SaveVersionDialogProps) {
  const [label, setLabel] = useState("");

  const handleSave = () => {
    if (!label.trim()) return;
    
    void dispatchCommand(COMMAND_IDS.investigation.saveVersion, {
      label: label.trim(),
    });
    
    setLabel("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Save Version</DialogTitle>
          <DialogDescription>
            Create a snapshot of the current investigation state. You can compare this version with others later.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="version-label">Version Label</Label>
            <Input
              id="version-label"
              placeholder="e.g., Threshold 0.35 baseline"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleSave();
                }
              }}
              autoFocus
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!label.trim()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
