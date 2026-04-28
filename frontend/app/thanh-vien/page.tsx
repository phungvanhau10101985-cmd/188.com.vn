'use client';

import { useAuth } from '@/features/auth/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import Link from 'next/link';

interface LoyaltyTier {
  id: number;
  name: string;
  min_spend: number;
  discount_percent: number;
  description: string;
}

interface LoyaltyStatus {
  current_tier: LoyaltyTier | null;
  total_spent_6_months: number;
  next_tier: LoyaltyTier | null;
  remaining_spend_for_next_tier: number | null;
  message: string;
}

export default function LoyaltyPage() {
  const { user, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<LoyaltyStatus | null>(null);
  const [tiers, setTiers] = useState<LoyaltyTier[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/auth/login?redirect=/thanh-vien');
    }
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (isAuthenticated) {
      Promise.all([
        apiClient.getMyLoyaltyStatus(),
        apiClient.getLoyaltyTiers()
      ])
        .then(([statusData, tiersData]) => {
          setStatus(statusData);
          setTiers(tiersData);
        })
        .catch((err) => console.error(err))
        .finally(() => setLoadingData(false));
    }
  }, [isAuthenticated]);

  if (isLoading || loadingData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin w-10 h-10 border-4 border-[#ea580c] border-t-transparent rounded-full"></div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
  };

  const nextTier = status?.next_tier;
  const progressPercent = nextTier 
    ? Math.min(100, Math.max(0, ((status?.total_spent_6_months || 0) / nextTier.min_spend) * 100))
    : 100;

  return (
    <div className="min-h-screen bg-gray-50 pb-12">
      {/* Header Section */}
      <div className="bg-gradient-to-r from-[#ea580c] to-[#c2410c] text-white pt-12 pb-24 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="flex flex-col md:flex-row items-center gap-6">
            <div className="relative">
              <div className="w-24 h-24 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center border-4 border-white/30 shadow-xl">
                <span className="text-4xl font-bold text-white">{status?.current_tier?.name || 'L0'}</span>
              </div>
              <div className="absolute -bottom-2 -right-2 bg-white text-[#ea580c] text-xs font-bold px-2 py-1 rounded-full shadow-md border border-gray-100">
                {status?.current_tier ? 'Thành viên' : 'Mới'}
              </div>
            </div>
            <div className="text-center md:text-left">
              <h1 className="text-3xl font-bold mb-2">Xin chào, {user?.full_name || 'Bạn'}!</h1>
              <p className="text-orange-100 text-lg opacity-90">
                {status?.message}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 -mt-16">
        {/* Stats Card */}
        <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-6 md:p-8 mb-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-gray-500 text-sm font-medium uppercase tracking-wide mb-1">Tổng chi tiêu (6 tháng)</h3>
              <div className="text-3xl font-bold text-gray-900 mb-2">
                {formatCurrency(status?.total_spent_6_months || 0)}
              </div>
              <p className="text-sm text-gray-500">
                Cập nhật lần cuối: {new Date().toLocaleDateString('vi-VN')}
              </p>
            </div>
            
            <div className="bg-gray-50 rounded-xl p-5 border border-gray-100">
              {nextTier ? (
                <>
                  <div className="flex justify-between items-end mb-2">
                    <span className="text-sm font-medium text-gray-700">Tiến độ lên hạng <span className="font-bold text-[#ea580c]">{nextTier.name}</span></span>
                    <span className="text-xs text-gray-500">{progressPercent.toFixed(1)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3 mb-3 overflow-hidden">
                    <div 
                      className="bg-gradient-to-r from-[#ea580c] to-[#fb923c] h-3 rounded-full transition-all duration-1000 ease-out" 
                      style={{ width: `${progressPercent}%` }}
                    ></div>
                  </div>
                  <p className="text-sm text-gray-600">
                    Mua thêm <span className="font-bold text-gray-900">{formatCurrency(status?.remaining_spend_for_next_tier || 0)}</span> để nhận ưu đãi giảm <span className="font-bold text-[#ea580c]">{nextTier.discount_percent}%</span>
                  </p>
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-[#ea580c] font-medium">
                  🎉 Bạn đã đạt hạng cao nhất!
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Tiers Timeline/Table */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-6 py-5 border-b border-gray-100 bg-gray-50/50 flex justify-between items-center">
            <h2 className="text-lg font-bold text-gray-900">Quyền lợi thành viên</h2>
            <Link href="/" className="text-sm text-[#ea580c] hover:underline font-medium">
              Mua sắm ngay →
            </Link>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  <th className="px-6 py-4">Hạng thành viên</th>
                  <th className="px-6 py-4">Mức chi tiêu (6 tháng)</th>
                  <th className="px-6 py-4">Ưu đãi giảm giá</th>
                  <th className="px-6 py-4">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(() => {
                  const sortedTiers = [...tiers].sort((a, b) => a.min_spend - b.min_spend);
                  const currentTierIndex = sortedTiers.findIndex(t => t.id === status?.current_tier?.id);

                  return sortedTiers.map((tier, index) => {
                    const isCurrent = status?.current_tier?.id === tier.id;
                    
                    const isPassed = 
                      (currentTierIndex !== -1 && index < currentTierIndex) || 
                      (status?.total_spent_6_months || 0) >= tier.min_spend;
                    
                    return (
                      <tr 
                        key={tier.id} 
                        className={`transition-colors ${isCurrent ? 'bg-orange-50/60' : 'hover:bg-gray-50'}`}
                      >
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold ${
                              isCurrent 
                                ? 'bg-[#ea580c] text-white shadow-md' 
                                : isPassed 
                                  ? 'bg-gray-200 text-gray-600' 
                                  : 'bg-gray-100 text-gray-400'
                            }`}>
                              {tier.name}
                            </div>
                            <div>
                              <div className={`font-bold ${isCurrent ? 'text-[#ea580c]' : 'text-gray-900'}`}>
                                {tier.name}
                              </div>
                              <div className="text-xs text-gray-500 md:hidden">
                                {tier.min_spend === 0 ? '< 4 triệu' : `>= ${formatCurrency(tier.min_spend)}`}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 font-medium">
                          {tier.min_spend === 0 ? 'Dưới 4.000.000 ₫' : `Từ ${formatCurrency(tier.min_spend)}`}
                        </td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            tier.discount_percent > 0 
                              ? 'bg-orange-100 text-orange-800' 
                              : 'bg-gray-100 text-gray-800'
                          }`}>
                            Giảm {tier.discount_percent}%
                          </span>
                          <p className="text-xs text-gray-500 mt-1 max-w-xs">{tier.description}</p>
                        </td>
                        <td className="px-6 py-4">
                          {isCurrent ? (
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-orange-100 text-[#ea580c] border border-orange-200">
                              <span className="w-2 h-2 rounded-full bg-[#ea580c]"></span>
                              Hiện tại
                            </span>
                          ) : isPassed ? (
                            <span className="text-gray-500 text-sm font-medium flex items-center gap-1">
                              ✓ Đã đạt
                            </span>
                          ) : (
                            <span className="text-gray-400 text-sm">Chưa đạt</span>
                          )}
                        </td>
                      </tr>
                    );
                  });
                })()}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer Note */}
        <div className="mt-8 bg-gray-50 rounded-xl p-6 border border-gray-200 flex items-start gap-4">
          <div className="text-gray-400 text-xl mt-0.5">ℹ️</div>
          <div>
            <h4 className="font-bold text-gray-900 mb-2">Thông tin chương trình</h4>
            <ul className="text-sm text-gray-600 space-y-1.5 list-disc list-inside">
              <li>
                Doanh số được tính dựa trên tổng giá trị các đơn hàng có trạng thái <strong>{'"'}Đã nhận hàng{'"'}</strong> hoặc{' '}
                <strong>{'"'}Đã hoàn thành{'"'}</strong>.
              </li>
              <li>Chu kỳ xét hạng là <strong>6 tháng liên tiếp</strong> gần nhất tính từ thời điểm hiện tại.</li>
              <li>Mức giảm giá thành viên được áp dụng tự động khi quý khách đặt hàng.</li>
              <li>Hạng thành viên sẽ được cập nhật tự động ngay khi đơn hàng đủ điều kiện.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
