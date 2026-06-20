import React from 'react'

interface ErrorBoundaryState {
  errorMessage: string
}

export default class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { errorMessage: '' }

  static getDerivedStateFromError(error: Error) {
    return { errorMessage: error.message || '화면 처리 중 오류가 발생했습니다.' }
  }

  componentDidCatch(error: Error) {
    sessionStorage.setItem('sorimemo_last_ui_error', error.message || String(error))
  }

  render() {
    if (!this.state.errorMessage) return this.props.children

    return (
      <div className="min-h-screen bg-[#eef8f6] px-5 py-10 text-[#183f40]">
        <div className="mx-auto max-w-sm rounded-3xl border border-red-100 bg-white p-5 shadow-lg">
          <p className="text-[18px] font-black text-red-600">화면 오류</p>
          <p className="mt-3 text-[13px] leading-5 text-[#426160]">
            파일 선택 직후 화면 처리 중 오류가 발생했습니다. 새로고침 후 다시 시도해 주세요.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-5 h-12 w-full rounded-full bg-[#0f7d82] text-[14px] font-black text-white"
          >
            새로고침
          </button>
        </div>
      </div>
    )
  }
}
