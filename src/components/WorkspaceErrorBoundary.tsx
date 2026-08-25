import { Component, type ReactNode } from 'react'

type Props = {
  children: ReactNode
  workspaceName: string
  onReturnHome: () => void
}

type State = {
  failed: boolean
}

export default class WorkspaceErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  private returnHome = () => {
    this.props.onReturnHome()
    this.setState({ failed: false })
  }

  render() {
    if (!this.state.failed) return this.props.children

    return (
      <section className="desktop-coming-soon" role="alert">
        <div className="coming-soon-icon">!</div>
        <span className="workspace-label">WORKSPACE UNAVAILABLE</span>
        <h1>{this.props.workspaceName} could not be displayed.</h1>
        <p>
          ETOP stopped this workspace after a local display error. This
          display fallback does not perform an ERP write or financial action.
        </p>
        <div className="coming-soon-banner">
          Preserve the current test environment and its logs for review.
        </div>
        <button
          type="button"
          className="desktop-primary-button"
          onClick={this.returnHome}
        >
          Return to Dashboard
        </button>
      </section>
    )
  }
}
