// features/voice/components/voice-control-bar.tsx — floating aerospace HUD voice control bar.
//
// what  : Docked HUD bar on the canvas displaying live voice state telemetry (IDLE, LISTENING,
//         THINKING, SPEAKING, STANDBY), dynamic reactive waveform visualizer, push-to-talk,
//         instant barge-in interrupt, and standby mute control.
// where : Rendered inside the free center column of InvestigationScreen above scene controls.
// how   : Reads reactive state from useVoiceSession and useVoiceStore, providing tactile audio feedback
//         and micro-interactions with zero layout shifting.

"use client";

import { Hand, Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { useCallback } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useVoiceSession } from "../hooks/use-voice-session";
import type { VoiceState } from "../store/voice-store";

interface VoiceControlBarProps {
  className?: string;
}

const STATE_CONFIG: Record<
  VoiceState,
  { label: string; badgeClass: string; dotClass: string; description: string }
> = {
  idle: {
    label: "IDLE",
    badgeClass: "border-border text-muted-foreground bg-muted/40",
    dotClass: "bg-muted-foreground/60",
    description: "Voice uplink active. Ready for query.",
  },
  listening: {
    label: "LISTENING",
    badgeClass: "border-aeris-teal/60 text-aeris-teal bg-aeris-teal/15 shadow-[0_0_12px_rgba(0,229,255,0.25)]",
    dotClass: "bg-aeris-teal animate-ping",
    description: "Capturing 16 kHz PCM audio stream...",
  },
  transcribing: {
    label: "TRANSCRIBING",
    badgeClass: "border-aeris-blue/60 text-aeris-blue bg-aeris-blue/15",
    dotClass: "bg-aeris-blue animate-pulse",
    description: "Whisper transcribing speech...",
  },
  thinking: {
    label: "THINKING",
    badgeClass: "border-aeris-amber/60 text-aeris-amber bg-aeris-amber/15 shadow-[0_0_12px_rgba(245,158,11,0.25)]",
    dotClass: "bg-aeris-amber animate-pulse",
    description: "Synthesizing response & executing investigation graph...",
  },
  speaking: {
    label: "SPEAKING",
    badgeClass: "border-aeris-green/60 text-aeris-green bg-aeris-green/15 shadow-[0_0_12px_rgba(16,185,129,0.25)]",
    dotClass: "bg-aeris-green animate-pulse",
    description: "Streaming Kokoro neural speech...",
  },
  standby: {
    label: "STANDBY",
    badgeClass: "border-border text-muted-foreground/60 bg-muted/20",
    dotClass: "bg-muted-foreground/30",
    description: "Voice narration muted while background runs proceed.",
  },
};

export function VoiceControlBar({ className }: VoiceControlBarProps) {
  const {
    connectionStatus,
    voiceState,
    transcript,
    isFinalTranscript,
    audioLevel,
    startTurn,
    endTurn,
    interrupt,
    toggleStandby,
  } = useVoiceSession();

  const handleTalkToggle = useCallback(() => {
    if (voiceState === "listening") {
      endTurn();
    } else {
      startTurn();
    }
  }, [voiceState, startTurn, endTurn]);

  if (connectionStatus !== "connected") {
    return null;
  }

  const currentConfig = STATE_CONFIG[voiceState] || STATE_CONFIG.idle;
  const isListening = voiceState === "listening";
  const isSpeaking = voiceState === "speaking";
  const isStandby = voiceState === "standby";

  return (
    <div
      className={cn(
        "pointer-events-auto flex flex-col items-center gap-1.5 transition-all duration-base",
        className,
      )}
      role="region"
      aria-label="Voice Session Control Bar"
    >
      {/* Real-time transcript popover preview */}
      {transcript ? (
        <div className="max-w-md rounded-md border border-border bg-surface-2/95 px-3 py-1.5 shadow-panel backdrop-blur-md transition-all">
          <p className="font-mono text-xs text-foreground/90 leading-relaxed">
            <span className="text-aeris-teal mr-1.5 font-bold">›</span>
            {transcript}
            {!isFinalTranscript && <span className="inline-block w-1.5 h-3 ml-1 bg-aeris-teal animate-pulse" />}
          </p>
        </div>
      ) : null}

      {/* Main Docked Aerospace HUD Bar */}
      <div className="flex items-center gap-2 rounded-lg border border-border/90 bg-surface-2/95 p-1.5 px-3 shadow-panel backdrop-blur-md">
        {/* Live State Badge */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className={cn(
                "flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[11px] font-medium tracking-widest transition-all",
                currentConfig.badgeClass,
              )}
            >
              <span className="relative flex size-1.5">
                <span className={cn("size-1.5 rounded-full", currentConfig.dotClass)} />
              </span>
              <span>{currentConfig.label}</span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="top" className="font-mono text-xs">
            {currentConfig.description}
          </TooltipContent>
        </Tooltip>

        {/* Audio Waveform / Level Meter */}
        <div
          className="flex h-5 items-center gap-0.5 px-1.5"
          aria-label={`Audio level meter: ${Math.round(audioLevel * 100)}%`}
        >
          {Array.from({ length: 8 }).map((_, i) => {
            // Calculate dynamic height for each bar based on audio level and frequency distribution
            const multiplier = Math.sin((i / 7) * Math.PI) * 0.8 + 0.2;
            const barLevel = isListening
              ? Math.max(0.15, Math.min(1.0, audioLevel * multiplier * 2.2))
              : isSpeaking
                ? 0.25 + Math.sin(Date.now() / 150 + i) * 0.2
                : 0.12;

            const heightPct = Math.round(barLevel * 100);

            return (
              <span
                key={i}
                className={cn(
                  "w-1 rounded-full transition-all duration-75",
                  isListening
                    ? "bg-aeris-teal"
                    : isSpeaking
                      ? "bg-aeris-green"
                      : isStandby
                        ? "bg-muted-foreground/30"
                        : "bg-muted-foreground/50",
                )}
                style={{ height: `${heightPct}%`, minHeight: "3px" }}
              />
            );
          })}
        </div>

        <span className="h-4 w-px bg-border/80" aria-hidden="true" />

        {/* Tap-to-Talk / Push-to-Talk Button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="sm"
              variant={isListening ? "default" : "outline"}
              onClick={handleTalkToggle}
              className={cn(
                "h-7 gap-1.5 rounded px-2.5 font-mono text-xs transition-all",
                isListening
                  ? "bg-aeris-teal text-aeris-black hover:bg-aeris-teal/90 shadow-[0_0_10px_rgba(0,229,255,0.4)]"
                  : "border-border/80 text-foreground hover:border-aeris-teal/60 hover:text-aeris-teal",
              )}
              aria-label={isListening ? "Stop listening" : "Start speaking"}
              aria-pressed={isListening}
            >
              <Mic className="size-3.5" />
              <span>{isListening ? "RELEASE" : "TALK"}</span>
              <kbd className="ml-1 rounded bg-black/20 px-1 text-[9px] font-sans text-foreground/80">
                Ctrl+P
              </kbd>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="font-mono text-xs">
            {isListening
              ? "Click or release Ctrl+P to finish query"
              : "Click to start query or hold Ctrl+P"}
          </TooltipContent>
        </Tooltip>

        {/* Instant Hardware Barge-In (Interrupt) Button when speaking */}
        {isSpeaking ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={interrupt}
                className="h-7 gap-1 rounded border-aeris-orange/50 bg-aeris-orange/10 px-2 font-mono text-xs text-aeris-orange hover:bg-aeris-orange/25"
                aria-label="Interrupt speech"
              >
                <Hand className="size-3" />
                <span>BARGE-IN</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" className="font-mono text-xs">
              Instantly interrupt speech output without canceling background calculations
            </TooltipContent>
          </Tooltip>
        ) : null}

        {/* Standby / Mute Toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={toggleStandby}
              className={cn(
                "size-7 rounded transition-colors",
                isStandby ? "text-aeris-amber hover:text-aeris-amber" : "text-muted-foreground hover:text-foreground",
              )}
              aria-label={isStandby ? "Resume narration" : "Standby (mute narration)"}
              aria-pressed={isStandby}
            >
              {isStandby ? <VolumeX className="size-3.5" /> : <Volume2 className="size-3.5" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="font-mono text-xs">
            {isStandby
              ? "Resume audio narration"
              : "Standby: mute audio narration while runs continue"}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
