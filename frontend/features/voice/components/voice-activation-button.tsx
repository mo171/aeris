// features/voice/components/voice-activation-button.tsx — VOICE UPLINK activator.
//
// what  : Identity strip button indicating VOICE UPLINK status. OFF by default, activated on user click
//         to unlock browser audio and enable Ctrl+P voice command mode.
// where : Mounted in the top header / identity strip of the workspace.

"use client";

import { Loader2, Radio } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useVoiceSession } from "../hooks/use-voice-session";

interface VoiceActivationButtonProps {
  className?: string;
}

export function VoiceActivationButton({ className }: VoiceActivationButtonProps) {
  const { connectionStatus, voiceState, connect, disconnect } = useVoiceSession();

  const isListening = voiceState === "listening";

  if (connectionStatus === "connected") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={disconnect}
            className={cn(
              "group relative h-8 gap-2 border-aeris-teal/50 bg-aeris-teal/15 px-2.5 font-mono text-xs text-aeris-teal hover:border-aeris-teal/70 hover:bg-aeris-teal/25 transition-all duration-fast shadow-[0_0_10px_rgba(0,229,255,0.2)]",
              isListening && "border-aeris-teal bg-aeris-teal/30 text-aeris-teal shadow-[0_0_15px_rgba(0,229,255,0.4)]",
              className,
            )}
            aria-label="Voice Uplink active. Click to turn off."
          >
            <span className="relative flex size-2">
              <span
                className={cn(
                  "absolute inline-flex h-full w-full rounded-full bg-aeris-teal opacity-75",
                  isListening ? "animate-ping" : "animate-pulse",
                )}
              />
              <span className="relative inline-flex size-2 rounded-full bg-aeris-teal" />
            </span>
            <Radio className="size-3.5 text-aeris-teal transition-transform group-hover:scale-110" />
            <span className="tracking-wide">
              {isListening ? "LISTENING..." : "VOICE UPLINK"}
            </span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="font-mono text-xs">
          Voice command mode activated. Hold <kbd className="rounded bg-muted px-1 text-[10px]">Ctrl+P</kbd> to talk. Click to turn off.
        </TooltipContent>
      </Tooltip>
    );
  }

  if (connectionStatus === "connecting") {
    return (
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled
        className={cn(
          "h-8 gap-2 border-aeris-amber/50 bg-aeris-amber/10 px-2.5 font-mono text-xs text-aeris-amber",
          className,
        )}
        aria-label="Activating Voice Uplink..."
      >
        <Loader2 className="size-3.5 animate-spin text-aeris-amber" />
        <span className="tracking-wide">CONNECTING...</span>
      </Button>
    );
  }

  // Disconnected / Off by default
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void connect()}
          className={cn(
            "group h-8 gap-2 border-border/80 bg-surface-2/60 px-2.5 font-mono text-xs text-muted-foreground hover:border-aeris-teal/60 hover:text-aeris-teal hover:bg-aeris-teal/10 transition-all",
            className,
          )}
          aria-label="Voice Uplink is off. Click to activate."
        >
          <Radio className="size-3.5 opacity-60 group-hover:opacity-100" />
          <span className="tracking-wide">VOICE UPLINK</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="font-mono text-xs">
        Click to activate Voice Uplink and enable <kbd className="rounded bg-muted px-1 text-[10px]">Ctrl+P</kbd> voice commands.
      </TooltipContent>
    </Tooltip>
  );
}
