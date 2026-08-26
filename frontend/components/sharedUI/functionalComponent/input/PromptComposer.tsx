// components/sharedUI/functionalComponent/input/PromptComposer.tsx — the multi-line question input.
//
// what  : An auto-growing textarea with a context slot, a voice button, and a send/stop control that swaps
//         according to whether the agent is currently answering. Exposes a focus() handle.
// where : Used by the Mission Command assistant panel, and reusable by the Investigation Workspace and
//         every other surface that talks to the agent.
// how   : Auto-resize resets the height to "auto" before reading scrollHeight, which is the only way to
//         let the box shrink again after text is deleted; the result is clamped so a long paste can never
//         swallow the transcript above it. Enter submits and Shift+Enter inserts a newline — the
//         convention operators expect from a command surface.
//
//         The textarea element stays private. Callers that need to focus it receive a narrow handle
//         through `ref` instead of passing their own element ref in: a component that owns a DOM node
//         should own every mutation of it, and handing the raw element outward invites callers to resize
//         or restyle it from a distance.
//
//         The microphone is present but disabled. Voice is a declared future capability, and showing the
//         affordance with an explicit "not yet" is more honest than hiding it and surprising people later.

"use client";

import { ArrowUp, Mic, Square } from "lucide-react";
import type { KeyboardEvent, ReactNode, Ref } from "react";
import { useCallback, useEffect, useImperativeHandle, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const MAX_COMPOSER_HEIGHT_PX = 168;

export interface PromptComposerHandle {
  focus: () => void;
}

interface PromptComposerProps {
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  isStreaming?: boolean;
  isDisabled?: boolean;
  placeholder: string;
  /** Slot above the input for selected-context chips. */
  contextSlot?: ReactNode;
  /** Slot below the input for hints. */
  hintSlot?: ReactNode;
  ref?: Ref<PromptComposerHandle>;
  className?: string;
}

export function PromptComposer({
  value,
  onValueChange,
  onSubmit,
  onStop,
  isStreaming = false,
  isDisabled = false,
  placeholder,
  contextSlot,
  hintSlot,
  ref,
  className,
}: PromptComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }), []);

  const resizeToContent = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_COMPOSER_HEIGHT_PX)}px`;
  }, []);

  useEffect(() => {
    resizeToContent();
  }, [value, resizeToContent]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!isStreaming && value.trim().length > 0) {
        onSubmit();
      }
    }
  };

  const canSubmit = !isDisabled && value.trim().length > 0;

  return (
    <div
      className={cn(
        "rounded-md border border-border bg-surface-2/80 transition-colors duration-base focus-within:border-aeris-teal/50 focus-within:shadow-glow-teal",
        className,
      )}
    >
      {contextSlot ? (
        <div className="flex flex-wrap items-center gap-1 border-b border-border-soft px-2.5 py-1.5">
          {contextSlot}
        </div>
      ) : null}

      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        disabled={isDisabled}
        placeholder={placeholder}
        onChange={(event) => onValueChange(event.target.value)}
        onKeyDown={handleKeyDown}
        className="block w-full resize-none bg-transparent px-3 pt-2.5 pb-1 text-xs leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/70 disabled:cursor-not-allowed"
        aria-label={placeholder}
      />

      <div className="flex items-center justify-between gap-2 px-2 pb-2">
        <div className="min-w-0 flex-1">{hintSlot}</div>

        <div className="flex shrink-0 items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              {/* The span keeps the tooltip working on a disabled control, which fires no pointer events. */}
              <span className="inline-flex">
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  disabled
                  aria-label="Voice command"
                >
                  <Mic />
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent side="top">Voice command arrives in a later phase</TooltipContent>
          </Tooltip>

          {isStreaming ? (
            <Button
              type="button"
              size="icon-sm"
              variant="outline"
              onClick={onStop}
              aria-label="Stop generating"
            >
              <Square className="fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              size="icon-sm"
              disabled={!canSubmit}
              onClick={onSubmit}
              aria-label="Send question"
            >
              <ArrowUp />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
