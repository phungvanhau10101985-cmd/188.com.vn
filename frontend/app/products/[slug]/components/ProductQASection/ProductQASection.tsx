'use client';

import { useState, useEffect, useCallback } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { Product, type ProductQuestionItem } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { formatPrice } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import { buildAuthLoginHrefFromParts } from '@/lib/auth-redirect';
import { useToast } from '@/components/ToastProvider';
import VerifiedPurchaserBadge from '../VerifiedPurchaserBadge';

interface ProductQASectionProps {
  product: Product;
  /** Khi true: nhúng trong tab, bỏ border/padding thừa */
  embedded?: boolean;
  /** Chỉ render modal, dùng modalOpen/onModalClose điều khiển từ ngoài */
  modalOnly?: boolean;
  modalOpen?: boolean;
  onModalClose?: () => void;
  onModalOpen?: () => void;
}


function formatDate(s: string | null | undefined) {
  if (!s) return '';
  try {
    return new Date(s).toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return s;
  }
}

export default function ProductQASection({ product, embedded, modalOnly, modalOpen: modalOpenProp, onModalClose, onModalOpen }: ProductQASectionProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [questions, setQuestions] = useState<ProductQuestionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [askContent, setAskContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [replyingId, setReplyingId] = useState<number | null>(null);
  const [replyContent, setReplyContent] = useState('');
  const [togglingUsefulId, setTogglingUsefulId] = useState<number | null>(null);
  const [modalOpenLocal, setModalOpenLocal] = useState(false);
  const modalOpen = modalOnly ? (modalOpenProp ?? false) : modalOpenLocal;
  const setModalOpen = useCallback((open: boolean) => {
    if (modalOnly) {
      if (open) onModalOpen?.();
      else onModalClose?.();
      return;
    }
    setModalOpenLocal(open);
  }, [modalOnly, onModalClose, onModalOpen]);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getProductQuestions(product.id)
      .then((list) => {
        if (!cancelled) setQuestions(Array.isArray(list) ? list : []);
      })
      .catch(() => {
        if (!cancelled) setQuestions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [product.id]);

  // Khi URL có #question-123 (từ nút "Xem câu hỏi" ở admin): mở popup và cuộn tới câu hỏi
  useEffect(() => {
    if (loading || questions.length === 0) return;
    const hash = typeof window !== 'undefined' ? window.location.hash : '';
    const match = hash.match(/^#question-(\d+)$/);
    if (!match) return;
    setModalOpen(true);
    const questionId = match[1];
    const scrollToQuestion = () => {
      const el = document.getElementById(`question-${questionId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ring-2', 'ring-[#ea580c]', 'ring-offset-2');
        setTimeout(() => el.classList.remove('ring-2', 'ring-[#ea580c]', 'ring-offset-2'), 2000);
      }
    };
    const t = setTimeout(scrollToQuestion, 200);
    return () => clearTimeout(t);
  }, [loading, questions.length, setModalOpen]);

  // Đóng popup khi bấm Escape
  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [modalOpen, setModalOpen]);

  const handleSubmitQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = askContent.trim();
    if (!content) return;
    if (!isAuthenticated) {
      pushToast({ title: 'Vui lòng đăng nhập để đặt câu hỏi', variant: 'info', durationMs: 2500 });
      return;
    }
    setSubmitting(true);
    try {
      const newQ = await apiClient.askProductQuestion(product.id, content);
      setQuestions((prev) => [newQ, ...prev]);
      setAskContent('');
    } catch (err) {
      pushToast({ title: 'Gửi câu hỏi thất bại', description: (err as Error)?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleUseful = useCallback(async (questionId: number) => {
    if (!isAuthenticated) {
      pushToast({ title: 'Vui lòng đăng nhập để bình chọn', variant: 'info', durationMs: 2500 });
      return;
    }
    setTogglingUsefulId(questionId);
    try {
      const res = await apiClient.toggleQuestionUseful(questionId);
      setQuestions((prev) =>
        prev.map((q) =>
          q.id === questionId
            ? { ...q, useful: res.useful, user_has_voted: res.user_has_voted }
            : q
        )
      );
    } catch {
      // ignore
    } finally {
      setTogglingUsefulId(null);
    }
  }, [isAuthenticated, pushToast]);

  const handleSubmitReply = useCallback(async (questionId: number) => {
    const content = replyContent.trim();
    if (!content) return;
    if (!isAuthenticated) {
      pushToast({ title: 'Vui lòng đăng nhập để trả lời', variant: 'info', durationMs: 2500 });
      return;
    }
    setReplyingId(questionId);
    try {
      const updated = await apiClient.replyToQuestion(questionId, content);
      setQuestions((prev) =>
        prev.map((q) => (q.id === questionId ? updated : q))
      );
      setReplyContent('');
      setReplyingId(null);
    } catch (err) {
      pushToast({
        title: 'Trả lời thất bại',
        description: (err as Error)?.message || 'Chỉ người đã mua sản phẩm mới được trả lời.',
        variant: 'error',
        durationMs: 3500,
      });
    } finally {
      setReplyingId(null);
    }
  }, [isAuthenticated, replyContent, pushToast]);

  const renderQuestionList = useCallback(
    (list: ProductQuestionItem[]) => (
      <div className="space-y-4">
        {list.map((q) => (
          <div key={q.id} id={`question-${q.id}`} className="bg-gray-50 rounded-lg p-4 space-y-2 scroll-mt-24">
            <div>
              <p className="text-sm font-medium text-gray-900">
                {q.user_name || 'Khách'} hỏi: {q.content}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">{formatDate(q.display_created_at ?? q.created_at)}</p>
            </div>
            {q.reply_admin_content && (
              <div className="pl-4 border-l-2 border-orange-200 text-sm text-gray-600">
                <p className="font-medium text-gray-800">
                  {q.reply_admin_name || '188.COM.VN'} trả lời: {formatDate(q.display_reply_admin_at ?? q.reply_admin_at)}
                </p>
                <p>{q.reply_admin_content}</p>
              </div>
            )}
            {q.reply_user_one_content && (
              <div className="pl-4 border-l-2 border-gray-200 text-sm text-gray-600">
                <p className="font-medium text-gray-800 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                  <span className="inline-flex items-center gap-1">
                    {q.reply_user_one_name}
                    {q.reply_user_one_id != null && <VerifiedPurchaserBadge compact />}
                  </span>
                  <span>
                    trả lời: {formatDate(q.display_reply_user_one_at ?? q.reply_user_one_at)}
                  </span>
                </p>
                <p>{q.reply_user_one_content}</p>
              </div>
            )}
            {q.reply_user_two_content && (
              <div className="pl-4 border-l-2 border-gray-200 text-sm text-gray-600">
                <p className="font-medium text-gray-800 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                  <span className="inline-flex items-center gap-1">
                    {q.reply_user_two_name}
                    {q.reply_user_two_id != null && <VerifiedPurchaserBadge compact />}
                  </span>
                  <span>
                    trả lời: {formatDate(q.display_reply_user_two_at ?? q.reply_user_two_at)}
                  </span>
                </p>
                <p>{q.reply_user_two_content}</p>
              </div>
            )}
            {isAuthenticated && (q.reply_count ?? 0) < 2 && (
              <div className="mt-2">
                {replyingId === q.id ? (
                  <div className="flex flex-col gap-2">
                    <textarea
                      value={replyContent}
                      onChange={(e) => setReplyContent(e.target.value)}
                      placeholder="Nhập câu trả lời của bạn (chỉ người đã mua sản phẩm mới được trả lời)"
                      rows={2}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm resize-none w-full"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => handleSubmitReply(q.id)}
                        disabled={!replyContent.trim()}
                        className="px-3 py-1.5 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] text-sm font-medium disabled:opacity-50"
                      >
                        Gửi trả lời
                      </button>
                      <button
                        type="button"
                        onClick={() => { setReplyingId(null); setReplyContent(''); }}
                        className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
                      >
                        Hủy
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setReplyingId(q.id)}
                    className="text-sm text-[#ea580c] hover:underline"
                  >
                    Trả lời (chỉ người đã mua hàng)
                  </button>
                )}
              </div>
            )}
            <div className="flex items-center gap-2 flex-wrap mt-1">
              {q.useful > 0 && (
                <span className="text-xs text-gray-500">
                  {q.useful} người thấy câu hỏi này hữu ích
                </span>
              )}
              <button
                type="button"
                onClick={() => handleToggleUseful(q.id)}
                disabled={togglingUsefulId === q.id}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-sm font-medium transition ${
                  q.user_has_voted
                    ? 'bg-[#dc2626] text-white hover:bg-[#b91c1c]'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                } disabled:opacity-50`}
                title="Hữu ích"
              >
                <span className="w-4 h-4 inline-flex items-center justify-center shrink-0" aria-hidden>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 11H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h3z" />
                  </svg>
                </span>
                Hữu ích
              </button>
            </div>
          </div>
        ))}
      </div>
    ),
    [handleSubmitReply, handleToggleUseful, isAuthenticated, replyingId, replyContent, togglingUsefulId]
  );

  const askLoginHref = buildAuthLoginHrefFromParts(pathname, searchParams, '#qa');

  const askForm = (
    <div className="mt-6">
      <p className="text-sm font-medium text-gray-700 mb-2">Đặt câu hỏi của bạn</p>
      {isAuthenticated ? (
        <form onSubmit={handleSubmitQuestion} className="flex flex-col sm:flex-row gap-2">
          <textarea
            value={askContent}
            onChange={(e) => setAskContent(e.target.value)}
            placeholder="Nhập câu hỏi..."
            rows={2}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm resize-none"
          />
          <button
            type="submit"
            disabled={!askContent.trim() || submitting}
            className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            {submitting ? 'Đang gửi...' : 'Gửi câu hỏi'}
          </button>
        </form>
      ) : (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <p className="mb-3">
            Đặt câu hỏi cho sản phẩm chỉ dành cho tài khoản đã đăng nhập.
          </p>
          <Link
            href={askLoginHref}
            className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-[#ea580c] text-white font-medium hover:bg-[#c2410c] transition-colors"
          >
            Đăng nhập để đặt câu hỏi
          </Link>
        </div>
      )}
    </div>
  );

  const productInfoBlock = (
    <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg mb-4">
      <div className="shrink-0 w-14 h-14 rounded-lg overflow-hidden bg-white border border-gray-200 relative">
        <Image
          src={getOptimizedImage(product.main_image || product.images?.[0], { fallbackStrategy: 'local' })}
          alt={product.name}
          fill
          sizes="56px"
          className="object-cover"
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-gray-900 truncate">{product.name}</p>
        <p className="text-[#ea580c] font-semibold">{formatPrice(product.price)}</p>
      </div>
    </div>
  );

  return (
    <>
      {!modalOnly && (
        <div id="qa" className={`scroll-mt-4 ${embedded ? 'py-0' : 'border-t border-gray-100 p-6'}`}>
          <h3 className="font-semibold text-gray-900 mb-4">
            Hỏi người bán và hỏi người đã mua: Có {loading ? '...' : questions.length} câu hỏi và trả lời
          </h3>
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="px-4 py-2 bg-[#ea580c] text-white rounded-lg hover:bg-[#c2410c] text-sm font-medium"
          >
            Xem thêm câu hỏi, trả lời và đặt câu hỏi
          </button>
        </div>
      )}

      {/* Popup trang câu hỏi của sản phẩm */}
      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          onClick={() => setModalOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="qa-modal-title"
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between shrink-0 px-4 py-3 border-b border-gray-200">
              <h2 id="qa-modal-title" className="font-semibold text-lg text-gray-900">
                Trang tổng hợp câu hỏi
              </h2>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition"
                aria-label="Đóng"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="overflow-y-auto flex-1 p-4">
              {productInfoBlock}
              {loading ? (
                <div className="py-8 text-center text-gray-500">Đang tải câu hỏi...</div>
              ) : questions.length === 0 ? (
                <div className="bg-gray-50 rounded-lg p-4 text-gray-600 text-sm">
                  Chưa có câu hỏi nào. Bạn hãy đặt câu hỏi đầu tiên (cần đăng nhập).
                </div>
              ) : (
                renderQuestionList(questions)
              )}
              {!loading && askForm}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
