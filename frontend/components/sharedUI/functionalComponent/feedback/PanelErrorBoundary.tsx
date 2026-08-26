// components/sharedUI/functionalComponent/feedback/PanelErrorBoundary.tsx — isolates a panel crash.
//
// what  : A React error boundary that renders ErrorState in place of a panel that threw during render.
// where : Wraps each independent zone of the Mission Command Center — data panel, globe, assistant panel.
// how   : Without per-panel boundaries a single render error in, say, the marker layer unmounts the whole
//         route and the operator loses the entire interface. Scoping the boundary to a zone means a
//         failure costs one panel and the rest of the command centre keeps working. Error boundaries must
//         be class components; this is the only class component in the codebase.

"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "./ErrorState";

interface PanelErrorBoundaryProps {
  children: ReactNode;
  /** Named in the console so a crash report identifies the zone immediately. */
  panelName: string;
}

interface PanelErrorBoundaryState {
  error: Error | null;
}

export class PanelErrorBoundary extends Component<
  PanelErrorBoundaryProps,
  PanelErrorBoundaryState
> {
  state: PanelErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): PanelErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(`[AERIS] ${this.props.panelName} panel crashed`, error, errorInfo.componentStack);
  }

  private handleReset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="flex h-full items-center justify-center">
          <ErrorState error={this.state.error} onRetry={this.handleReset} />
        </div>
      );
    }

    return this.props.children;
  }
}
