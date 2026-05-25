import Link from 'next/link';
import { getProductBySkuForSSR } from '@/lib/product-seo';
import { parseCartAddCloseMode } from '@/lib/cart-add-return';
import CartAddClient from './CartAddClient';

type Props = {
  params: Promise<{ sku: string }>;
  searchParams: Promise<{ action?: string; return?: string; from?: string }>;
};

function parseAction(raw?: string): 'add' | 'buy' | 'both' {
  const v = (raw || '').trim().toLowerCase();
  if (v === 'add' || v === 'buy') return v;
  return 'both';
}

export default async function CartAddBySkuPage({ params, searchParams }: Props) {
  const { sku: rawSku } = await params;
  const { action: rawAction, return: rawReturn, from: rawFrom } = await searchParams;
  const sku = decodeURIComponent(rawSku || '').trim();
  const action = parseAction(rawAction);
  const fromNanoAi = (rawFrom || '').trim().toLowerCase() === 'nanoai';
  const close = parseCartAddCloseMode(rawReturn, fromNanoAi);

  if (!sku) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
        <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
          <h1 className="text-xl font-bold text-gray-900 mb-2">Thiếu mã sản phẩm</h1>
          <p className="text-sm text-gray-600 mb-6">URL cần có dạng /cart/add/{'{sku}'}.</p>
          <Link
            href="/"
            className="inline-flex px-5 py-2.5 bg-[#ea580c] text-white rounded-lg font-medium hover:bg-[#c2410c]"
          >
            Về trang chủ
          </Link>
        </div>
      </div>
    );
  }

  const product = await getProductBySkuForSSR(sku);

  if (!product) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
        <div className="bg-white border border-gray-200 rounded-2xl p-8 max-w-lg w-full text-center">
          <h1 className="text-xl font-bold text-gray-900 mb-2">Không tìm thấy sản phẩm</h1>
          <p className="text-sm text-gray-600 mb-2">
            Mã <span className="font-mono text-gray-800">{sku}</span> không khớp sản phẩm nào trên shop.
          </p>
          <p className="text-xs text-gray-500 mb-6">Kiểm tra lại SKU từ chat hoặc thử tìm trên trang chủ.</p>
          <Link
            href="/"
            className="inline-flex px-5 py-2.5 bg-[#ea580c] text-white rounded-lg font-medium hover:bg-[#c2410c]"
          >
            Về trang chủ
          </Link>
        </div>
      </div>
    );
  }

  return (
    <CartAddClient
      product={product}
      sku={sku}
      action={action}
      closeMode={close.mode}
      closePath={close.path}
    />
  );
}
