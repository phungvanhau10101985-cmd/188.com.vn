'use client';

import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Cách ly lỗi runtime của 1 khối trên trang chủ (VD: lưới gợi ý, lưới sản phẩm)
 * để lỗi cục bộ không kéo sập toàn trang. Reset khi children thay đổi identity
 * qua key ở nơi sử dụng nếu cần tải lại.
 */
export default class HomeSectionErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false };

  public static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('HomeSectionErrorBoundary caught:', error, errorInfo);
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
