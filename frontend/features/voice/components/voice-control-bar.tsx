// features/voice/components/voice-control-bar.tsx — floating aerospace HUD voice control bar.
//
// what  : Docked HUD bar on the canvas displaying live AERIS voice telemetry (IDLE, LISTENING,
//         THINKING, SPEAKING), reactive waveform visualizer, push-to-talk, barge-in interrupt,
//         recent action summaries, and quick query dispatch.
// persona : Authentic British aerospace AI assistant (AERIS).

"use client";

import { Hand, Mic, Sparkles, Volume2, VolumeX, Send, Bot } from "lucide-react";
import { useCallback, useState } from "react";

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
    label: "AERIS ONLINE",
    badgeClass: "border-aeris-teal/40 text-aeris-teal bg-aeris-teal/10",
    dotClass: "bg-aeris-teal",
    description: "AERIS voice uplink active. Hold Ctrl+P to speak.",
  },
  listening: {
    label: "LISTENING",
    badgeClass: "border-aeris-teal text-aeris-teal bg-aeris-teal/20 shadow-[0_0_15px_rgba(0,229,255,0.4)]",
    dotClass: "bg-aeris-teal animate-ping",
    description: "Capturing speech audio stream...",
  },
  transcribing: {
    label: "TRANSCRIBING",
    badgeClass: "border-aeris-blue/60 text-aeris-blue bg-aeris-blue/15",
    dotClass: "bg-aeris-blue animate-pulse",
    description: "Whisper transcribing audio...",
  },
  thinking: {
    label: "ANALYZING",
    badgeClass: "border-aeris-amber/60 text-aeris-amber bg-aeris-amber/15 shadow-[0_0_12px_rgba(245,158,11,0.25)]",
    dotClass: "bg-aeris-amber animate-pulse",
    description: "AERIS reasoning & generating UI execution plan...",
  },
  speaking: {
    label: "SPEAKING",
    badgeClass: "border-emerald-400 text-emerald-400 bg-emerald-500/15 shadow-[0_0_15px_rgba(52,211,153,0.3)]",
    dotClass: "bg-emerald-400 animate-pulse",
    description: "AERIS speaking via British neural synthesis...",
  },
  standby: {
    label: "MUTED",
    badgeClass: "border-border text-muted-foreground/60 bg-muted/20",
    dotClass: "bg-muted-foreground/30",
    description: "Voice narration muted.",
  },
};

export function VoiceControlBar({ className }: VoiceControlBarProps) {
  const {
    connectionStatus,
    voiceState,
    transcript,
    lastAerisReply,
    activeActionSummary,
    isFinalTranscript,
    audioLevel,
    isMuted,
    startTurn,
    endTurn,
    sendTextQuery,
    interrupt,
    toggleMute,
  } = useVoiceSession();

  const [textInput, setTextInput] = useState("");
  const [showTextInput, setShowTextInput] = useState(false);

  const handleTalkToggle = useCallback(() => {
    if (voiceState === "listening") {
      void endTurn();
    } else {
      void startTurn();
    }
  }, [voiceState, startTurn, endTurn]);

  const handleTextSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!textInput.trim()) return;
      void sendTextQuery(textInput.trim());
      setTextInput("");
      setShowTextInput(false);
    },
    [textInput, sendTextQuery],
  );

  if (connectionStatus !== "connected") {
    return null;
  }

  const currentConfig = STATE_CONFIG[voiceState] || STATE_CONFIG.idle;
  const isListening = voiceState === "listening";
  const isSpeaking = voiceState === "speaking";

  return (
    <div
      className={cn(
        "pointer-events-auto flex flex-col items-center gap-2 transition-all duration-base max-w-xl",
        className,
      )}
      role="region"
      aria-label="AERIS Voice Control Bar"
    >
      {/* AERIS Spoken Response Popover */}
      {lastAerisReply ? (
        <div className="w-full rounded-md border border-aeris-teal/30 bg-surface-2/95 p-2 px-3 shadow-panel backdrop-blur-md transition-all">
          <div className="flex items-start gap-2">
            <Bot className="size-4 shrink-0 text-aeris-teal mt-0.5" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] font-semibold tracking-wider text-aeris-teal uppercase">
                  AERIS
                </span>
                {activeActionSummary ? (
                  <span className="truncate text-[9px] font-mono text-muted-foreground max-w-[240px]">
                    {activeActionSummary}
                  </span>
                ) : null}
              </div>
              <p className="mt-0.5 font-sans text-xs text-foreground/95 leading-relaxed">
                {lastAerisReply}
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {/* User Live Transcript Popover */}
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
      <div className="flex items-center gap-2 rounded-lg border border-aeris-teal/40 bg-surface-2/95 p-1.5 px-3 shadow-panel backdrop-blur-md">
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

        {/* Dynamic Audio Waveform / Level Meter */}
        <div
          className="flex h-5 items-center gap-0.5 px-1.5"
          aria-label={`Audio level meter: ${Math.round(audioLevel * 100)}%`}
        >
          {Array.from({ length: 8 }).map((_, i) => {
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
                      ? "bg-emerald-400"
                      : isMuted
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
                  ? "bg-aeris-teal text-aeris-black hover:bg-aeris-teal/90 shadow-[0_0_12px_rgba(0,229,255,0.5)]"
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
              ? "Click or release Ctrl+P to dispatch query to AERIS."
              : "Hold Ctrl+P or click to speak directly to AERIS."}
          </TooltipContent>
        </Tooltip>

        {/* Text Input Toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={() => setShowTextInput((prev) => !prev)}
              className={cn(
                "size-7 rounded transition-colors",
                showTextInput ? "text-aeris-teal bg-aeris-teal/10" : "text-muted-foreground hover:text-foreground",
              )}
              aria-label="Toggle text prompt to AERIS"
            >
              <Sparkles className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="font-mono text-xs">
            Type command to AERIS
          </TooltipContent>
        </Tooltip>

        {/* Instant Barge-In (Interrupt) Button when speaking */}
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
                <span>STOP</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" className="font-mono text-xs">
              Instantly silence AERIS
            </TooltipContent>
          </Tooltip>
        ) : null}

        {/* Mute Toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={toggleMute}
              className={cn(
                "size-7 rounded transition-colors",
                isMuted ? "text-aeris-amber hover:text-aeris-amber" : "text-muted-foreground hover:text-foreground",
              )}
              aria-label={isMuted ? "Unmute AERIS" : "Mute AERIS"}
              aria-pressed={isMuted}
            >
              {isMuted ? <VolumeX className="size-3.5" /> : <Volume2 className="size-3.5" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="top" className="font-mono text-xs">
            {isMuted ? "Unmute speech narration" : "Mute speech narration"}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Expandable Text Command Bar */}
      {showTextInput ? (
        <form
          onSubmit={handleTextSubmit}
          className="flex w-full items-center gap-1.5 rounded-md border border-border bg-surface-2/95 p-1 px-2 shadow-panel backdrop-blur-md"
        >
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Command AERIS (e.g. 'Zoom to Mazgaon and isolate radar structures')..."
            className="flex-1 bg-transparent px-1.5 py-0.5 font-sans text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
            autoFocus
          />
          <Button type="submit" size="icon-sm" variant="ghost" className="size-6 text-aeris-teal">
            <Send className="size-3" />
          </Button>
        </form>
      ) : null}
    </div>
  );
}
