// features/voice/components/voice-activation-button.tsx — aerospace voice uplink activator.
//
// what  : Activates bidirectional voice communication with AERIS: unlocks browser AudioContext,
//         prompts mic permission, establishes WebSocket uplink, and plays the audio chime.
// where : Mounted in the top header / identity strip of the workspace.
// how   : Connects to useVoiceSession, reflecting current link state with tactile telemetry styling.

"use client";

import { AlertCircle, Loader2, Mic, MicOff, Radio } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useVoiceSession } from "../hooks/use-voice-session";

interface VoiceActivationButtonProps {
  className?: string;
}

export function VoiceActivationButton({ className }: VoiceActivationButtonProps) {
  const { connectionStatus, connect, disconnect } = useVoiceSession();

  const handleClick = () => {
    if (connectionStatus === "connected") {
      disconnect();
    } else if (connectionStatus === "disconnected" || connectionStatus === "error") {
      void connect();
    }
  };

  if (connectionStatus === "connected") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleClick}
            className={cn(
              "group relative h-8 gap-2 border-aeris-teal/40 bg-aeris-teal/10 px-2.5 font-mono text-xs text-aeris-teal hover:border-aeris-teal/70 hover:bg-aeris-teal/20 transition-all duration-fast",
              className,
            )}
            aria-label="Voice uplink active. Click to disconnect."
          >
            <span className="relative flex size-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-aeris-teal opacity-75" />
              <span className="relative inline-flex size-2 rounded-full bg-aeris-teal" />
            </span>
            <Radio className="size-3.5 text-aeris-teal transition-transform group-hover:scale-110" />
            <span className="tracking-wide">VOICE UPLINK</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="font-mono text-xs">
          AERIS voice link active. Hold <kbd className="rounded bg-muted px-1 text-[10px]">Ctrl+P</kbd> to talk. Click to disconnect.
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
        aria-label="Establishing voice uplink..."
      >
        <Loader2 className="size-3.5 animate-spin text-aeris-amber" />
        <span className="tracking-wide">LINKING...</span>
      </Button>
    );
  }

  if (connectionStatus === "error") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleClick}
            className={cn(
              "h-8 gap-2 border-aeris-red/50 bg-aeris-red/10 px-2.5 font-mono text-xs text-aeris-red hover:bg-aeris-red/20",
              className,
            )}
            aria-label="Voice uplink error. Click to retry."
          >
            <AlertCircle className="size-3.5" />
            <span className="tracking-wide">LINK RETRY</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="font-mono text-xs text-destructive">
          Microphone access denied or connection lost. Click to retry.
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleClick}
          className={cn(
            "group h-8 gap-2 border-border/80 bg-surface-2/80 px-2.5 font-mono text-xs text-muted-foreground hover:border-aeris-teal/50 hover:bg-aeris-teal/10 hover:text-foreground transition-all duration-fast",
            className,
          )}
          aria-label="Activate AERIS Voice"
        >
          <Mic className="size-3.5 text-muted-foreground transition-colors group-hover:text-aeris-teal" />
          <span className="tracking-wide">VOICE UPLINK</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="font-mono text-xs">
        Activate AERIS real-time voice streaming uplink
      </TooltipContent>
    </Tooltip>
  );
}
