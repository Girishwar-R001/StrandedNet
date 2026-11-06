import { Component, type ReactNode } from 'react'

/** A failure in one page must not blank a whole dashboard during live use. */
export default class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="p-8 text-center">
        <p className="font-medium">This page hit a problem.</p>
        <button className="mt-2 cursor-pointer underline" onClick={() => location.reload()}>Reload</button>
      </div>
    )
  }
}
