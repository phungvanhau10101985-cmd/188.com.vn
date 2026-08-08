'use client';

import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Cách ly lỗi runtime của 1 khối trên trang (gallery, thông tin SP, tabs, gợi ý…)
 * để lỗi cục bộ không kéo sập toàn trang. Dùng chung cho trang chi tiết sản phẩm
 * và ladipage.
 */
export default class SectionErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false };

  public static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('SectionErrorBoundary caught:', error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm flex items-center justify-between gap-4">
          <span>Không thể hiển thị phần này. Vui lòng thử lại.</span>
          <button
            type="button"
            onClick={this.handleRetry}
            className="underline font-medium shrink-0"
          >
            Thử lại
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
