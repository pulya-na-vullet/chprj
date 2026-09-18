import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback: ReactNode;
  // When this value changes, the boundary clears its error state and retries
  // rendering. During streaming we pass the growing answer text, so a transient
  // throw on partial markdown recovers on the next token instead of sticking.
  resetKey?: unknown;
}

interface State {
  hasError: boolean;
}

// A render throw anywhere below (e.g. react-markdown choking on partial markdown
// mid-stream) is caught here and shown as `fallback`, instead of unmounting the
// whole React tree and leaving a blank white page.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidUpdate(prev: Props): void {
    if (this.state.hasError && prev.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  render(): ReactNode {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
