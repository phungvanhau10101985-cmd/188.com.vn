'use client';

// Bảng số căn theo thang cỡ ôm thường gặp và cách quy đổi ra tem trên shop; phần hiển thị cho khách không cần nhắc xuất xứ nguồn.
import Link from 'next/link';
import {
  hrefChonSizeSegments,
  resolveSizeGuideSegments,
  titleForSizeGuideSlug,
} from '@/lib/category-size-guide-meta';

/** Bảng chiều dài chân ↔ cỡ EU/VN thường gặp ở shop Việt Nam. */
function ShoeTableMale() {
  const rows = [
    ['23,6–24,0', '38'],
    ['24,1–24,5', '39'],
    ['24,6–25,0', '40'],
    ['25,1–25,5', '41'],
    ['25,6–26,0', '42'],
    ['26,1–26,5', '43'],
    ['26,6–27,0', '44'],
    ['27,1–27,5', '45'],
    ['27,6–28,0', '46'],
    ['28,1–28,5', '47'],
  ];
  return (
    <table className="w-full text-sm border border-gray-200 border-collapse text-left mt-3">
      <thead>
        <tr className="bg-amber-100">
          <th className="p-2 border border-gray-200">Chiều dài chân (cm)</th>
          <th className="p-2 border border-gray-200">Cỡ giày dép nam (EU/VN)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([cm, sz], idx) => (
          <tr key={`${cm}-${idx}`}>
            <td className="p-2 border border-gray-100">{cm}</td>
            <td className="p-2 border border-gray-100">{sz}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ShoeTableFemale() {
  const rows = [
    ['21,6–22,0', '34'],
    ['22,1–22,5', '35'],
    ['22,6–23,0', '36'],
    ['23,1–23,5', '37'],
    ['23,6–24,0', '38'],
    ['24,1–24,5', '39'],
    ['24,6–25,0', '40'],
    ['25,1–25,5', '41'],
    ['25,6–26,0', '42'],
    ['26,1–26,5', '43'],
  ];
  return (
    <table className="w-full text-sm border border-gray-200 border-collapse text-left mt-3">
      <thead>
        <tr className="bg-amber-100">
          <th className="p-2 border border-gray-200">Chiều dài chân (cm)</th>
          <th className="p-2 border border-gray-200">Cỡ giày dép nữ (EU/VN)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([cm, sz], idx) => (
          <tr key={`${cm}-${idx}`}>
            <td className="p-2 border border-gray-100">{cm}</td>
            <td className="p-2 border border-gray-100">{sz}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Bảng chiều dài chân trẻ em (nhị / học sinh nhỏ). */
function ShoeTableKid() {
  const rows = [
    ['15,5', '24'],
    ['16,0', '24–25'],
    ['16,5', '25–26'],
    ['17,0', '26–27'],
    ['17,5', '27–28'],
    ['18,0', '28–29'],
    ['18,5', '29–30'],
    ['19,0', '30'],
    ['19,5', '31'],
    ['20,0', '31–32'],
    ['20,5', '32–33'],
    ['21,0', '33–34'],
    ['21,5', '34–35'],
    ['22,0', '35–36'],
    ['22,5', '36'],
    ['23,0', '36–37'],
    ['23,5', '37'],
    ['24,0', '37–38'],
  ];
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse text-left mt-3">
      <thead>
        <tr className="bg-amber-100">
          <th className="p-2 border border-gray-200">Chiều dài chân (cm)</th>
          <th className="p-2 border border-gray-200">Cỡ tem (tham khảo nhị / học sinh nhỏ)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([cm, sz], idx) => (
          <tr key={`${cm}-${idx}`}>
            <td className="p-2 border border-gray-100">{cm}</td>
            <td className="p-2 border border-gray-100">{sz}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BraBandTable() {
  const rows = [
    ['63–67', '65'],
    ['68–72', '70'],
    ['73–77', '75'],
    ['78–82', '80'],
    ['83–87', '85'],
    ['88–92', '90'],
  ];
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse mt-3">
      <thead>
        <tr className="bg-pink-50">
          <th className="p-2 border">Vòng ngực dưới (ôm sát ngang xương, cm)</th>
          <th className="p-2 border">Cỡ vành hay gặp (band)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([cm, sz], idx) => (
          <tr key={`${sz}-${idx}`}>
            <td className="p-2 border border-gray-100">{cm}</td>
            <td className="p-2 border border-gray-100">{sz}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ApparelMaleTable() {
  const rows = [
    ['S', '86–90', '41–43', '70–76', '88–94'],
    ['M', '90–96', '43–45', '76–82', '94–100'],
    ['L', '96–102', '45–47', '82–88', '100–106'],
    ['XL', '102–108', '47–49', '88–94', '106–112'],
    ['XXL', '108–114', '49–51', '94–100', '112–118'],
    ['3XL', '114–122', '51–53', '100–108', '118–126'],
    ['4XL', '122–130', '53–55', '108–116', '126–134'],
    ['5XL', '130–138', '55–58', '116–126', '134–144'],
  ];
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse mt-3">
      <thead>
        <tr className="bg-gray-50">
          <th className="p-2 border">Cỡ</th>
          <th className="p-2 border">Ngực (cm)</th>
          <th className="p-2 border">Vai (cm)</th>
          <th className="p-2 border">Eo (cm)</th>
          <th className="p-2 border">Mông (cm)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r[0]}>
            {r.map((c, i) => (
              <td key={`${r[0]}-${i}`} className="p-2 border border-gray-100">
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Gợi ý cỡ theo chiều cao & cân nặng (form ôm chuẩn Á — tham khảo; luôn ưu tiên số đo cm). */
function ApparelMaleHeightWeightTable() {
  const rows = [
    ['S', '155–165', '45–55'],
    ['M', '160–170', '55–63'],
    ['L', '165–175', '63–72'],
    ['XL', '170–180', '72–82'],
    ['XXL', '175–185', '82–92'],
    ['3XL', '178–188', '92–105'],
    ['4XL', '180–192', '105–118'],
    ['5XL', '185–196', '118–130'],
  ];
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse mt-3">
      <thead>
        <tr className="bg-slate-50">
          <th className="p-2 border">Cỡ</th>
          <th className="p-2 border">Chiều cao (cm)</th>
          <th className="p-2 border">Cân nặng (kg)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r[0]}>
            {r.map((c, i) => (
              <td key={`${r[0]}-${i}`} className="p-2 border border-gray-100">
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ApparelFemaleHeightWeightTable() {
  const rows = [
    ['XS', '145–155', '38–45'],
    ['S', '150–160', '43–50'],
    ['M', '155–165', '50–56'],
    ['L', '158–168', '56–63'],
    ['XL', '160–170', '63–72'],
    ['XXL', '162–172', '72–82'],
    ['3XL', '165–175', '82–92'],
  ];
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse mt-3">
      <thead>
        <tr className="bg-slate-50">
          <th className="p-2 border">Cỡ</th>
          <th className="p-2 border">Chiều cao (cm)</th>
          <th className="p-2 border">Cân nặng (kg)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r[0]}>
            {r.map((c, i) => (
              <td key={`${r[0]}-${i}`} className="p-2 border border-gray-100">
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ApparelFemaleTable() {
  const rows = [
    ['XS', '78–82', '60–66', '84–90'],
    ['S', '82–86', '66–70', '88–94'],
    ['M', '86–90', '70–74', '92–98'],
    ['L', '90–95', '74–80', '96–104'],
    ['XL', '95–101', '80–86', '102–110'],
    ['XXL', '101–108', '86–94', '108–116'],
    ['3XL', '108–116', '94–104', '116–126'],
  ];
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse mt-3">
      <thead>
        <tr className="bg-gray-50">
          <th className="p-2 border">Cỡ</th>
          <th className="p-2 border">Ngực (cm)</th>
          <th className="p-2 border">Eo (cm)</th>
          <th className="p-2 border">Mông (cm)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r[0]}>
            {r.map((c, i) => (
              <td key={`${r[0]}-${i}`} className="p-2 border border-gray-100">
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function KidsTable() {
  const rows = [
    ['12–18 tháng', '78–83', '9–12', '92–98'],
    ['2–3 tuổi', '88–96', '12–15', '100–106'],
    ['4–5 tuổi', '98–110', '16–20', '110–118'],
    ['6–7 tuổi', '110–122', '19–24', '120–132'],
    ['8–9 tuổi', '123–134', '22–28', '135–146'],
    ['10–11 tuổi', '135–145', '28–38', '147–154'],
    ['12–13 tuổi', '145–158', '36–50', '155–166'],
  ];
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse mt-3">
      <thead>
        <tr className="bg-gray-50">
          <th className="p-2 border">Tuổi (tham khảo)</th>
          <th className="p-2 border">Chiều cao (cm)</th>
          <th className="p-2 border">Cân nặng (kg)</th>
          <th className="p-2 border">Cỡ Á (hay gặp)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r[0]}>
            {r.map((c, i) => (
              <td key={`${r[0]}-${i}`} className="p-2 border border-gray-100">
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-gray-600 mt-3 leading-relaxed">{children}</p>;
}

function Heading({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <h2 className={['text-base font-bold text-gray-900 mt-4 first:mt-0', className].filter(Boolean).join(' ')}>{children}</h2>
  );
}

function GuideTable({
  headers,
  rows,
  headClass = 'bg-gray-50',
}: {
  headers: string[];
  rows: string[][];
  headClass?: string;
}) {
  return (
    <table className="w-full text-xs sm:text-sm border border-gray-200 border-collapse text-left mt-3">
      <thead>
        <tr className={headClass}>
          {headers.map((h) => (
            <th key={h} className="p-2 border border-gray-200">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, idx) => (
          <tr key={`${r[0]}-${idx}`}>
            {r.map((c, i) => (
              <td key={`${r[0]}-${i}`} className="p-2 border border-gray-100">
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Cat2Link({ path, children }: { path: string; children: React.ReactNode }) {
  return (
    <Link href={`/info/chon-size/${path}`} className="text-[#ea580c] hover:underline">
      {children}
    </Link>
  );
}

const SOURCE_FIT_CAT1 = new Set([
  'giay-dep-nam',
  'giay-dep-nu',
  'thoi-trang-nam',
  'thoi-trang-nu',
  'do-lot-nam',
  'do-lot-nu',
  'trang-phuc-bau-hau-san',
  'thoi-trang-tre-em',
  'the-thao-da-ngoai',
]);

function SourceFitNote() {
  return (
    <Note>
      Nhiều lô trên 188.com.vn là form Á / tem nhập: cùng số đo cm thường ôm hơn hàng may sẵn Việt. Giữa hai cỡ hoặc khi bảng shop trống, nên
      nghiêng lớn hơn 0,5–1 size.
    </Note>
  );
}

function GuideKidsShoes() {
  return (
    <>
      <Heading>Giày dép trẻ em — đo chiều dài chân (cm)</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Trẻ mỗi năm tăng nhanh: nên đo lại chiều dài chân (gót → ngón dài nhất) khi mua giày mới; đặt hai bàn chân đứng; đo buổi chiều tối
        và chừng 0,3–0,5 cm không chạm vách đầu mũi nếu mô tả không nói rõ ôm chặt.
      </p>
      <ShoeTableKid />
      <Note>
        Một chiều dài chân có thể ra hai cỡ tem (24–25, 31–32…) vì hãng không cùng thang. Ưu tiên cm chân + chừa khoảng 0,5 cm mũi; đừng chọn
        theo số tuổi trên nhãn.
      </Note>
      <Note>Bé lớn dần hết bảng trên có thể đo chiều dài chân và so với bảng giày nữ cỡ nhỏ (thường từ 35+) trên từng sản phẩm.</Note>
    </>
  );
}

function GuideBraFemale() {
  return (
    <>
      <Heading>Bra áo ngực Nữ — vòng vành (band) và cup</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Bước 1 — đo vòng ngực dưới: ôm sát nhưng không siết ngang đường chân núm sau lưng; thở nhẹ và giữ chỉ của thước ngang. Bước 2 —
        đo ngang ngực trọn chỗ nhô nhất (thường qua núm) nhưng vẫn giữ chỉ không siết.
      </p>
      <p className="text-sm text-gray-700 mt-2">
        Cỡ vành hay gặp (70, 75, 80…) tương ứng vòng dưới khoảng như sau (mỗi hãng có thể lệch 1 size):
      </p>
      <BraBandTable />
      <p className="text-sm text-gray-700 mt-2 mt-4">
        Cup (A/B/C…): là hiệu giữa số đo ngực trọn và ngực dưới (cm), quy chiếu sơ bộ:
      </p>
      <ul className="list-disc list-inside text-sm text-gray-700 mt-2 space-y-1">
        <li>{'<'} 10 cm: AA hoặc A nhỏ tùy nhãn</li>
        <li>≈10–12 cm: A</li>
        <li>≈12–14 cm: B</li>
        <li>≈14–16 cm: C</li>
        <li>≈16–18 cm: D</li>
        <li>{'>'} 18 cm: E trở lên — đối chiếu bảng nhãn từng mặt hàng</li>
      </ul>
      <Note>
        Một nhãn dùng một mã («75B»); khi chỉ có S/M/L hãy ưu tiên bảng cm trên tin bán của shop trên trang sản phẩm.
      </Note>
    </>
  );
}

function GuideHeelsFemale({ variant }: { variant: 'cao-got' | 'cuoi-tiec' }) {
  const wedding = variant === 'cuoi-tiec';
  return (
    <>
      <Heading>{wedding ? 'Giày cưới & dự tiệc Nữ' : 'Giày cao gót Nữ'} — cỡ và độ ôm</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Vẫn căn vào chiều dài chân (cm) như giày bệt. Gót và mũi nhọn thường khiến cổ chân và ngón bị ôm hơn:
        nếu bàn chân bè, mu chân cao hoặc ít đi cao gót, nên nghiêng lớn hơn 1 size.
      </p>
      {wedding ? (
        <p className="text-sm text-gray-700 mt-2">
          Giày tiệc thường đi trong thời gian dài: ưu tiên form ổn gót và test đứng/ngồi; nếu mua online, căn chừng vào cỡ đang mang giày
          bệt cùng hãng (nếu có) và chiều ngang họng giày.
        </p>
      ) : null}
      <ShoeTableFemale />
      <Note>
        Độ cao gót (cm trong mô tả) ảnh hưởng lực bàn chân trước. Giày mũi nhọn nên chọn vừa thoáng; sandal quai mảnh
        nếu chân gầy có thể giữ đúng size, chân bè nên tăng 1 size. Luôn ưu tiên bảng kích cỡ trên từng sản phẩm tại 188.com.vn.
      </Note>
    </>
  );
}

function PantsMaleTable() {
  return (
    <GuideTable
      headClass="bg-amber-50"
      headers={[
        'Cỡ số (hay gặp)',
        'Cỡ chữ',
        'Eo (cm)',
        'Hông (cm)',
        'Dài ngoài cạp–gấu (cm)',
        'Inseam mặt trong (cm)',
      ]}
      rows={[
        ['28', 'S', '70–74', '88–94', '98–102', '72–76'],
        ['29', 'S–M', '74–76', '90–96', '99–103', '73–77'],
        ['30', 'M', '76–79', '94–100', '100–104', '74–78'],
        ['31', 'M–L', '79–81', '96–102', '101–105', '75–79'],
        ['32', 'L', '81–84', '100–106', '102–106', '76–80'],
        ['33', 'L–XL', '84–86', '102–108', '103–107', '77–81'],
        ['34', 'XL', '86–90', '106–112', '104–108', '78–82'],
        ['36', 'XXL', '90–96', '110–118', '105–109', '79–83'],
        ['38', '3XL', '96–102', '116–126', '106–110', '80–84'],
      ]}
    />
  );
}

function ShirtMaleTable() {
  return (
    <GuideTable
      headClass="bg-amber-50"
      headers={['Cỡ', 'Cổ áo (cm)', 'Ngực (cm)', 'Vai (cm)', 'Dài tay (cm)']}
      rows={[
        ['S', '37–38', '86–92', '41–43', '57–59'],
        ['M', '39–40', '92–98', '43–45', '59–61'],
        ['L', '41–42', '98–104', '45–47', '61–63'],
        ['XL', '43–44', '104–110', '47–49', '63–65'],
        ['XXL', '45–46', '110–116', '49–51', '64–66'],
        ['3XL', '47–48', '116–124', '51–54', '65–67'],
      ]}
    />
  );
}

function SkirtFemaleTable() {
  return (
    <GuideTable
      headClass="bg-pink-50"
      headers={['Cỡ', 'Eo (cm)', 'Hông (cm)', 'Dài ngang gối (cm)', 'Dài midi (cm)']}
      rows={[
        ['XS', '60–66', '84–90', '42–50', '68–76'],
        ['S', '66–70', '88–94', '44–52', '70–78'],
        ['M', '70–74', '92–98', '46–54', '72–80'],
        ['L', '74–80', '96–104', '48–56', '74–82'],
        ['XL', '80–86', '102–110', '50–58', '76–84'],
        ['XXL', '86–94', '108–116', '52–60', '78–86'],
      ]}
    />
  );
}

function PantsFemaleTable() {
  return (
    <GuideTable
      headClass="bg-pink-50"
      headers={['Cỡ', 'Eo (cm)', 'Hông (cm)', 'Dài ngoài cạp–gấu (cm)', 'Inseam mặt trong (cm)']}
      rows={[
        ['XS', '60–66', '84–90', '90–96', '68–72'],
        ['S', '66–70', '88–94', '92–98', '70–74'],
        ['M', '70–74', '92–98', '94–100', '72–76'],
        ['L', '74–80', '96–104', '96–102', '74–78'],
        ['XL', '80–86', '102–110', '98–104', '75–79'],
        ['XXL', '86–94', '108–116', '99–105', '76–80'],
      ]}
    />
  );
}

function BoxerMaleTable() {
  return (
    <GuideTable
      headClass="bg-slate-50"
      headers={['Cỡ', 'Eo (cm)', 'Hông (cm)']}
      rows={[
        ['S', '70–76', '88–94'],
        ['M', '76–82', '94–100'],
        ['L', '82–88', '100–106'],
        ['XL', '88–94', '106–112'],
        ['XXL', '94–100', '112–118'],
        ['3XL', '100–108', '118–126'],
      ]}
    />
  );
}

function PantyFemaleTable() {
  return (
    <GuideTable
      headClass="bg-pink-50"
      headers={['Cỡ', 'Eo (cm)', 'Hông (cm)']}
      rows={[
        ['XS', '60–66', '84–90'],
        ['S', '66–70', '88–94'],
        ['M', '70–74', '92–98'],
        ['L', '74–80', '96–104'],
        ['XL', '80–86', '102–110'],
        ['XXL', '86–94', '108–116'],
      ]}
    />
  );
}

function MaternityBellyTable() {
  return (
    <GuideTable
      headClass="bg-rose-50"
      headers={['Giai đoạn', 'Vòng bụng (cm, tham khảo)', 'Gợi ý cỡ so với trước bầu']}
      rows={[
        ['Trước bầu / tam cá nguyệt 1', 'Giữ số đo đang mặc', 'Giữ size, ưu tiên vải co giãn'],
        ['Tuần 13–27', 'Tăng khoảng 8–15 cm', '+1 cỡ hoặc dáng bầu'],
        ['Tuần 28 trở đi', 'Tăng khoảng 15–25+ cm', '+1 đến +2 cỡ; ưu tiên ô bụng'],
        ['Sau sinh 0–6 tuần', 'Bụng còn nở', 'Giữ size bầu hoặc −1 so với cuối thai kỳ'],
      ]}
    />
  );
}

function GuideMaleFootwear({ kind }: { kind: 'sneaker' | 'tay' | 'boot' | 'sandal' }) {
  const title =
    kind === 'sneaker'
      ? 'Sneaker & giày chạy Nam'
      : kind === 'tay'
        ? 'Giày tây & công sở Nam'
        : kind === 'boot'
          ? 'Boot Nam'
          : 'Sandal & dép quai Nam';
  return (
    <>
      <Heading>{title} — đo chiều dài chân (cm)</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo từ gót đến ngón dài nhất, hai chân đứng; đo buổi tối, mang đúng loại tất như khi đi. Nếu hai chân lệch, lấy chân dài hơn.
      </p>
      <ShoeTableMale />
      {kind === 'sneaker' ? (
        <Note>
          Giày chạy thường cần chừa 0,5–1 cm mũi (không sát ngón). Giữa hai cỡ nên chọn lớn hơn; bàn bè hoặc mu cao tăng 1 size.
          Sneaker thời trang ôm hơn giày chạy — nếu thích vừa khít có thể giữ đúng cỡ khi chân thon.
        </Note>
      ) : null}
      {kind === 'tay' ? (
        <Note>
          Form giày tây / mũi nhọn thường hẹp hơn sneaker. Da mới có thể nới nhẹ theo bề ngang, gần như không dài thêm — căn theo chiều
          dài chân, không mua chật chờ giãn. Giữa hai cỡ nên nghiêng lớn hơn; mang tất công sở khi đo.
        </Note>
      ) : null}
      {kind === 'boot' ? (
        <>
          <p className="text-sm text-gray-700 mt-3">
            Boot cổ cao: đo thêm bắp chân chỗ to nhất (cm) rồi so với số ống boot trên tin bán. Tất dày hoặc quần bó trong boot nên tăng 1 size
            chiều dài.
          </p>
          <Note>
            Chelsea / boot ôm cổ nên vừa, tránh quá rộng bị tuột gót. Combat hoặc ống rộng ưu tiên chiều dài chân; bắp to thì đọc kỹ chu vi ống.
          </Note>
        </>
      ) : null}
      {kind === 'sandal' ? (
        <Note>
          Quai chỉnh được: giữ đúng cỡ nếu chân thon. Quai cố định hoặc dép slide: chân bè / mu cao tăng 1 size; quá rộng dễ tuột gót khi bước.
          Không mang tất khi đo nếu bạn đi dép trần.
        </Note>
      ) : null}
    </>
  );
}

function GuideFemaleSneaker() {
  return (
    <>
      <Heading>Sneaker & giày bệt Nữ — đo chiều dài chân (cm)</Heading>
      <p className="text-sm text-gray-700 mt-2">Đo gót đến ngón dài nhất; đứng, đo buổi tối, mang tất như khi đi sneaker.</p>
      <ShoeTableFemale />
      <Note>
        Sneaker đế dày / chunky thường rộng hơn giày bệt mũi nhọn. Giữa hai cỡ: giày bệt hoặc mũi hẹp nghiêng lớn hơn; sneaker thể thao chừa
        khoảng 0,5 cm mũi. Chân bè, mu cao tăng 1 size.
      </Note>
    </>
  );
}

function GuideFemaleBoot() {
  return (
    <>
      <Heading>Boot Nữ — cỡ chân và ống boot</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Căn chiều dài chân như giày bệt. Boot cổ cao / over-knee: đo bắp chân chỗ to nhất và chiều cao ống (nếu mô tả có) để biết có kéo vừa
        không.
      </p>
      <ShoeTableFemale />
      <Note>
        Boot mũi nhọn hoặc khóa kéo ôm nên nghiêng lớn hơn 1 size nếu ở giữa hai cỡ. Tất dày, quần trong boot cũng nên tăng 1 size. Bắp to ưu
        tiên mẫu ống rộng hoặc chất co giãn.
      </Note>
    </>
  );
}

function GuideFemaleSandal({
  kind,
}: {
  kind: 'dep-sandal-nu' | 'sandal-quai-ngang-nu' | 'sandal-dinh-da-nu' | 'sandal-ho-mui-nu';
}) {
  const title =
    kind === 'sandal-quai-ngang-nu'
      ? 'Sandal quai ngang Nữ'
      : kind === 'sandal-dinh-da-nu'
        ? 'Sandal đính đá Nữ'
        : kind === 'sandal-ho-mui-nu'
          ? 'Sandal hở mũi Nữ'
          : 'Dép sandal Nữ';
  return (
    <>
      <Heading>{title} — cỡ và quai</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo chiều dài chân (cm) như giày bệt. Sandal hở nên vừa, không chật mũi và không quá rộng để gót bị tuột.
      </p>
      <ShoeTableFemale />
      {kind === 'sandal-quai-ngang-nu' ? (
        <Note>
          Quai ngang ôm mu chân: nếu mu cao hoặc quai không chỉnh được, tăng 1 size. Chân thon có thể giữ đúng cỡ; kiểm tra vị trí quai không
          cắt ngón.
        </Note>
      ) : null}
      {kind === 'sandal-dinh-da-nu' ? (
        <Note>
          Hạt / đá đính phía trong có thể làm lòng giày chật hơn 0,5 cỡ. Giữa hai cỡ nên chọn lớn hơn; thử cảm giác quai không cấn mu chân.
        </Note>
      ) : null}
      {kind === 'sandal-ho-mui-nu' ? (
        <Note>
          Mũi hở: ngón không được tràn khỏi đế. Giữa hai cỡ, chân thon giữ đúng; chân bè tăng 1 size để bề ngang thoáng, không chọn quá dài.
        </Note>
      ) : null}
      {kind === 'dep-sandal-nu' ? (
        <Note>
          Dép lê / sandal quai mảnh: chân thon giữ đúng size; chân bè hoặc mu cao tăng 1 size. Quai chỉnh được thì ưu tiên đúng chiều dài chân.
        </Note>
      ) : null}
    </>
  );
}

function GuideShirtMale() {
  return (
    <>
      <Heading>Áo sơ mi Nam — cổ, ngực và tay</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng cổ (ôm vừa, không siết), vòng ngực chỗ nở nhất, vai (xương vai này sang xương vai kia) và dài tay từ vai đến cổ tay khi hơi
        gập khuỷu.
      </p>
      <ShirtMaleTable />
      <Note>
        Sơ mi slim: nếu bụng / ngực dày hơn vai, tăng 1 cỡ hoặc ưu tiên dáng regular. Cổ áo phải cài được nút trên mà vẫn thở được. Form oversize
        có thể giảm 1 cỡ nếu muốn gọn.
      </Note>
    </>
  );
}

function GuidePantsMale() {
  return (
    <>
      <Heading>Quần dài Nam — eo, hông và dài ống</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng eo chỗ thường cài quần (không hóp bụng) và vòng hông chỗ lớn nhất. Dài ngoài: từ cạp xuống gấu. Inseam: từ đáy đũng (đường
        may giữa hai ống) xuống gấu — chỉ so với cột inseam khi tin bán ghi inseam.
      </p>
      <PantsMaleTable />
      <Note>
        Cỡ số 28–38 ≈ vòng eo tính theo inch. Nam Việt ~168–175 cm thường khớp dải dài ngoài 100–106 cm (cỡ 30–32). Cao trên 178 cm lấy dải
        dài hơn trong cùng cỡ eo. Quần âu/jeans ôm: giữa hai cỡ chọn vừa, tránh siết.
      </Note>
    </>
  );
}

function GuideDressFemale() {
  return (
    <>
      <Heading>Đầm Nữ — ngực, eo, hông và dài đầm</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng ngực (qua điểm nở nhất), eo nhỏ nhất, hông chỗ lớn nhất. Dài đầm: từ vai (hoặc từ eo với đầm hai dây) xuống gấu — so với số
        trong mô tả (mini / midi / maxi).
      </p>
      <ApparelFemaleTable />
      <Note>
        Đầm ôm ưu tiên ngực và eo; nếu hông to hơn cùng cỡ thì chọn cỡ theo hông hoặc dáng xòe. Đầm hai dây / cổ đổ: đo thêm vòng trên ngực.
        Form oversize có thể giảm 1 cỡ nếu muốn gọn.
      </Note>
    </>
  );
}

function GuideSkirtFemale() {
  return (
    <>
      <Heading>Váy &amp; chân váy Nữ — eo, hông và dài</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng eo chỗ cạp váy và vòng hông chỗ lớn nhất. Dài chân váy đo từ cạp xuống gấu: ngang gối khoảng giữa đùi–gối; midi tới giữa bắp
        chân (không phải váy ngắn).
      </p>
      <SkirtFemaleTable />
      <Note>
        Mini thường ngắn hơn cột ngang gối. Maxi gần mắt cá — đọc số cm trên từng sản phẩm, đừng lấy midi. Chân váy ôm căn hông; chân váy xòe
        căn eo. Eo nhỏ hơn hông nhiều thì chọn theo hông rồi chỉnh cạp (nếu có).
      </Note>
    </>
  );
}

function GuidePantsFemale() {
  return (
    <>
      <Heading>Quần dài &amp; legging Nữ — eo, hông và dài ống</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng eo thường mặc quần và vòng hông chỗ lớn nhất. Dài ngoài: cạp xuống gấu. Inseam: đáy đũng xuống gấu (thường 70–80 cm — không
        nhầm với dài ngoài ~90–105 cm). Legging co giãn có thể trùng hai cỡ — ưu tiên ôm vừa, không tụt cạp.
      </p>
      <PantsFemaleTable />
      <Note>
        Jeans / quần tây ôm: chọn theo hông nếu hông to hơn eo. Legging và quần cạp cao: bụng hơi dày nên tăng 1 cỡ. Cao dưới 155 cm lấy dải
        inseam ngắn hơn trong cùng cỡ; cao trên 165 cm lấy dải dài hơn.
      </Note>
    </>
  );
}

function GuideBoxerMale() {
  return (
    <>
      <Heading>Quần lót boxer brief Nam — eo và hông</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng eo chỗ cạp quần lót (ôm vừa) và vòng hông chỗ lớn nhất. Chọn cỡ vừa, không siết eo — vải co giãn sẽ ôm thêm khi mặc.
      </p>
      <BoxerMaleTable />
      <Note>
        Boxer brief ôm đùi: nếu đùi to, tăng 1 cỡ dù eo còn trong dải. Brief/sịp tam giác thường trùng bảng eo. Giữa hai cỡ chọn vừa, tránh căng
        cạp.
      </Note>
    </>
  );
}

function GuidePantyFemale() {
  return (
    <>
      <Heading>Quần lót &amp; bikini lót Nữ — eo và hông</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng eo nhỏ nhất và vòng hông chỗ lớn nhất. Bikini / quần lót ôm nên khớp hông; cạp không cắt da.
      </p>
      <PantyFemaleTable />
      <Note>
        Nếu hông to hơn eo một bậc, chọn theo hông. Quần lót cotton ít co hơn vải thun — giữa hai cỡ nên tăng 1. Không dùng bảng này cho áo
        bra (xem trang{' '}
        <Cat2Link path="do-lot-nu/bra-ao-nguc-nu">Bra áo ngực Nữ</Cat2Link>).
      </Note>
    </>
  );
}

function GuideMaternityDaily() {
  return (
    <>
      <Heading>Đồ mặc bầu hàng ngày — vòng bụng và cỡ</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Đo vòng ngực và vòng bụng chỗ nở nhất (đứng thẳng, thở bình thường). So với size đang mặc trước bầu, rồi đối chiếu giai đoạn:
      </p>
      <MaternityBellyTable />
      <p className="text-sm text-gray-700 mt-3">Bảng ngực–eo–hông nữ (tham khảo dáng trước bầu / đầu thai kỳ):</p>
      <ApparelFemaleTable />
      <Note>
        Ưu tiên chất co giãn và ô bụng. Bụng phát triển lệch bảng thì chọn cỡ lớn hơn, không siết bụng. Đồ công sở bầu hoặc sau sinh có thể
        cần dáng khác — luôn đọc mô tả từng sản phẩm.
      </Note>
    </>
  );
}

const CAT2_PAIR = {
  KIDS_SHOES: 'thoi-trang-tre-em/giay-dep-tre-em',
  BRA: 'do-lot-nu/bra-ao-nguc-nu',
  HEELS: 'giay-dep-nu/giay-cao-got-nu',
  WEDDING: 'giay-dep-nu/giay-cuoi-du-tiec-nu',
  MALE_SNEAKER: 'giay-dep-nam/sneaker-giay-chay-nam',
  MALE_DRESS: 'giay-dep-nam/giay-tay-cong-so-nam',
  MALE_BOOT: 'giay-dep-nam/boot-nam',
  MALE_SANDAL: 'giay-dep-nam/sandal-dep-quai-nam',
  FEMALE_SNEAKER: 'giay-dep-nu/sneaker-giay-bet-nu',
  FEMALE_BOOT: 'giay-dep-nu/boot-nu',
  FEMALE_SANDAL: 'giay-dep-nu/dep-sandal-nu',
  FEMALE_SANDAL_STRAP: 'giay-dep-nu/sandal-quai-ngang-nu',
  FEMALE_SANDAL_STONE: 'giay-dep-nu/sandal-dinh-da-nu',
  FEMALE_SANDAL_OPEN: 'giay-dep-nu/sandal-ho-mui-nu',
  MALE_SHIRT: 'thoi-trang-nam/ao-so-mi-nam',
  MALE_PANTS: 'thoi-trang-nam/quan-dai-nam',
  FEMALE_DRESS: 'thoi-trang-nu/dam-nu',
  FEMALE_SKIRT: 'thoi-trang-nu/vay-chan-vay-nu',
  FEMALE_PANTS: 'thoi-trang-nu/quan-dai-legging-nu',
  MALE_BOXER: 'do-lot-nam/quan-lot-boxer-brief-nam',
  FEMALE_PANTY: 'do-lot-nu/quan-lot-bikini-lot-nu',
  MATERNITY_DAILY: 'trang-phuc-bau-hau-san/do-mac-bau-hang-ngay',
} as const;

/** Nội dung chính: `segments` là [cat1] hoặc [cat1, cat2Override]. */
export function SizeGuideInner({ segments }: { segments: readonly string[] }) {
  if (segments.length === 2) {
    const k = `${segments[0]}/${segments[1]}`;
    switch (k) {
      case CAT2_PAIR.KIDS_SHOES:
        return <GuideKidsShoes />;
      case CAT2_PAIR.BRA:
        return <GuideBraFemale />;
      case CAT2_PAIR.HEELS:
        return <GuideHeelsFemale variant="cao-got" />;
      case CAT2_PAIR.WEDDING:
        return <GuideHeelsFemale variant="cuoi-tiec" />;
      case CAT2_PAIR.MALE_SNEAKER:
        return <GuideMaleFootwear kind="sneaker" />;
      case CAT2_PAIR.MALE_DRESS:
        return <GuideMaleFootwear kind="tay" />;
      case CAT2_PAIR.MALE_BOOT:
        return <GuideMaleFootwear kind="boot" />;
      case CAT2_PAIR.MALE_SANDAL:
        return <GuideMaleFootwear kind="sandal" />;
      case CAT2_PAIR.FEMALE_SNEAKER:
        return <GuideFemaleSneaker />;
      case CAT2_PAIR.FEMALE_BOOT:
        return <GuideFemaleBoot />;
      case CAT2_PAIR.FEMALE_SANDAL:
        return <GuideFemaleSandal kind="dep-sandal-nu" />;
      case CAT2_PAIR.FEMALE_SANDAL_STRAP:
        return <GuideFemaleSandal kind="sandal-quai-ngang-nu" />;
      case CAT2_PAIR.FEMALE_SANDAL_STONE:
        return <GuideFemaleSandal kind="sandal-dinh-da-nu" />;
      case CAT2_PAIR.FEMALE_SANDAL_OPEN:
        return <GuideFemaleSandal kind="sandal-ho-mui-nu" />;
      case CAT2_PAIR.MALE_SHIRT:
        return <GuideShirtMale />;
      case CAT2_PAIR.MALE_PANTS:
        return <GuidePantsMale />;
      case CAT2_PAIR.FEMALE_DRESS:
        return <GuideDressFemale />;
      case CAT2_PAIR.FEMALE_SKIRT:
        return <GuideSkirtFemale />;
      case CAT2_PAIR.FEMALE_PANTS:
        return <GuidePantsFemale />;
      case CAT2_PAIR.MALE_BOXER:
        return <GuideBoxerMale />;
      case CAT2_PAIR.FEMALE_PANTY:
        return <GuidePantyFemale />;
      case CAT2_PAIR.MATERNITY_DAILY:
        return <GuideMaternityDaily />;
      default:
        break;
    }
  }

  const key = segments[0];

  if (key === 'giay-dep-nam') {
    return (
      <>
        <Heading>Hướng dẫn đo và chọn size giày dép nam — 188.com.vn</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Đo chiều dài bàn chân (cm): từ gót đến ngón dài nhất, hai chân nên đứng; đo buổi tối, mang đúng loại tất như khi mang giày.
        </p>
        <ShoeTableMale />
        <Note>
          Giữa hai cỡ: giày thể thao hoặc giày bít mũi nên chọn cỡ lớn hơn; dép lê/dép quai ngang có thể giữ đúng cỡ nếu
          chân thon. Chân bè, mu chân cao hoặc thích mang tất dày nên tăng 1 size.
        </Note>
        <Note>
          Bảng theo form:{' '}
          <Cat2Link path={CAT2_PAIR.MALE_SNEAKER}>sneaker &amp; giày chạy</Cat2Link>
          {', '}
          <Cat2Link path={CAT2_PAIR.MALE_DRESS}>giày tây</Cat2Link>
          {', '}
          <Cat2Link path={CAT2_PAIR.MALE_BOOT}>boot</Cat2Link>
          {' và '}
          <Cat2Link path={CAT2_PAIR.MALE_SANDAL}>sandal &amp; dép quai</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'giay-dep-nu') {
    return (
      <>
        <Heading>Hướng dẫn chọn size giày dép nữ — 188.com.vn</Heading>
        <p className="text-sm text-gray-700 mt-2">Đo như nam: gót đến ngón dài nhất (cm).</p>
        <ShoeTableFemale />
        <Note>
          Giày cao gót, mũi nhọn hoặc boot ôm nên nghiêng lớn hơn 1 size nếu ở giữa hai cỡ. Sandal/dép quai mảnh giữ đúng
          size khi chân thon; chân bè hoặc mu cao nên tăng 1 size.
        </Note>
        <Note>
          Bảng theo form:{' '}
          <Cat2Link path={CAT2_PAIR.FEMALE_SNEAKER}>sneaker &amp; giày bệt</Cat2Link>
          {', '}
          <Cat2Link path={CAT2_PAIR.HEELS}>cao gót</Cat2Link>
          {', '}
          <Cat2Link path={CAT2_PAIR.WEDDING}>cưới &amp; tiệc</Cat2Link>
          {', '}
          <Cat2Link path={CAT2_PAIR.FEMALE_BOOT}>boot</Cat2Link>
          {' và '}
          <Cat2Link path={CAT2_PAIR.FEMALE_SANDAL}>dép sandal</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'thoi-trang-nam') {
    return (
      <>
        <Heading>Size quần áo nam (tham khảo)</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Ưu tiên đo thước dây: ngực, vai, eo, mông — so với dải (cm) của bạn rồi chọn cỡ gần nhất.
        </p>
        <ApparelMaleTable />
        <Heading className="!mt-6">Gợi ý cỡ theo chiều cao &amp; cân nặng (nam)</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Dùng khi chưa đo được thước: dải này hợp vóc dáng nam Việt hơn. Người vai rộng / bụng lớn nên nghiêng cỡ lớn hơn
          hoặc căn bảng cm phía trên.
        </p>
        <ApparelMaleHeightWeightTable />
        <Note>Form oversize có thể giảm 1 cỡ nếu thích vừa người; form slim/ôm hoặc bụng lớn nên tăng 1 cỡ.</Note>
        <Note>
          Chi tiết hơn:{' '}
          <Cat2Link path={CAT2_PAIR.MALE_SHIRT}>áo sơ mi (cổ–tay)</Cat2Link>
          {' và '}
          <Cat2Link path={CAT2_PAIR.MALE_PANTS}>quần dài (eo–dài ống)</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'thoi-trang-nu') {
    return (
      <>
        <Heading>Size quần áo nữ (tham khảo)</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Đo ngực, eo, hông (cm); chọn cỡ vừa khít nhất so với số đo của bạn.
        </p>
        <ApparelFemaleTable />
        <Heading className="!mt-6">Gợi ý cỡ theo chiều cao &amp; cân nặng (nữ)</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Tham khảo nhanh khi mua online theo vóc dáng nữ Việt; ngực / eo / hông khác biệt lớn so với cùng chiều cao nên
          luôn ưu tiên bảng đo cm phía trên.
        </p>
        <ApparelFemaleHeightWeightTable />
        <Note>Đầm ôm ưu tiên vai–ngực–eo; quần và chân váy ưu tiên eo và hông. Form oversize có thể giảm 1 cỡ nếu muốn gọn.</Note>
        <Note>
          Chi tiết hơn:{' '}
          <Cat2Link path={CAT2_PAIR.FEMALE_DRESS}>đầm</Cat2Link>
          {', '}
          <Cat2Link path={CAT2_PAIR.FEMALE_SKIRT}>váy &amp; chân váy</Cat2Link>
          {' và '}
          <Cat2Link path={CAT2_PAIR.FEMALE_PANTS}>quần dài &amp; legging</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'do-lot-nam') {
    return (
      <>
        <Heading>Đồ lót nam — căn vào cm vòng</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Đo vòng eo thường mặc (cm) và vòng hông chỗ lớn nhất; so với bảng trên từng sản phẩm. Giữa hai cỡ chọn vừa, tránh siết quá eo.
        </p>
        <Note>
          Quần lót boxer/brief: xem bảng eo–hông tại{' '}
          <Cat2Link path={CAT2_PAIR.MALE_BOXER}>Quần lót boxer brief Nam</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'do-lot-nu') {
    return (
      <>
        <Heading>Đồ lót nữ — căn vào cm vòng</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Đo vòng eo thường mặc (cm) và vòng hông chỗ lớn nhất; so với bảng trên từng sản phẩm. Giữa hai cỡ chọn vừa, tránh siết quá eo.
        </p>
        <Note>
          Áo bra: cỡ vành + cup tại{' '}
          <Cat2Link path={CAT2_PAIR.BRA}>Bra áo ngực Nữ</Cat2Link>. Quần lót / bikini lót:{' '}
          <Cat2Link path={CAT2_PAIR.FEMALE_PANTY}>Quần lót &amp; bikini lót Nữ</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'trang-phuc-bau-hau-san') {
    return (
      <>
        <Heading>Bầu & sau sinh</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Ưu tiên vòng ngực và bụng (cm), chiều cao, giai đoạn bầu hoặc sau sinh. Ưu tiên chất co giãn, dáng ôm vừa.
        </p>
        <Note>Bụng phát triển lệch bảng có thể chọn cỡ lớn hơn hoặc kiểu ô thoáng bụng của shop.</Note>
        <Note>
          Bảng theo giai đoạn thai kỳ: xem{' '}
          <Cat2Link path={CAT2_PAIR.MATERNITY_DAILY}>Đồ mặc bầu hàng ngày</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'thoi-trang-tre-em') {
    return (
      <>
        <Heading>Trẻ em — tuổi, cao và cỡ Á</Heading>
        <p className="text-sm text-gray-700 mt-2">Tham khảo thường dùng trong shop Việt Nam (mỗi hãng có thể khác):</p>
        <KidsTable />
        <Note>Trẻ lớn nhanh — ưu tiên khớp chiều cao và cân nặng hơn đúng số tuổi trên nhãn.</Note>
        <Note>
          Riêng <strong>giày dép trẻ em</strong> nên căn chiều dài chân (cm):{' '}
          <Cat2Link path={CAT2_PAIR.KIDS_SHOES}>Giày dép trẻ em</Cat2Link>.
        </Note>
      </>
    );
  }

  if (key === 'the-thao-da-ngoai') {
    return (
      <>
        <Heading>Đồ thể thao &amp; dã ngoại</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Quần áo: đo ngực — eo — hông (cm) rồi so bảng của từng sản phẩm. Găng, mũ, bó: xem cỡ tay, chu vi đầu hoặc chiều dài dây trong mô tả.
        </p>
        <ApparelMaleTable />
        <Heading className="!mt-6">Gợi ý cỡ theo chiều cao &amp; cân nặng (nam — tham khảo)</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Áp dụng tương tự thời trang nam; đồ thể thao co giãn có thể trùng nhiều cỡ — ưu tiên bảng shop từng mã.
        </p>
        <ApparelMaleHeightWeightTable />
        <Note>Hàng co giãn ôm người có thể cần cỡ lớn hơn nếu vai rộng hoặc tay dài — đọc chi tiết từng mẫu.</Note>
      </>
    );
  }

  const genericCats = [
    'tui-xach-nam',
    'tui-xach-nu',
    'phu-kien-nam',
    'phu-kien-nu',
    'vali-tui-du-lich',
    'dong-ho',
    'trang-suc-thoi-trang',
    'phu-kien-dien-thoai-cong-nghe',
    'my-pham-lam-dep',
    'do-gia-dung',
    'do-choi-me-be',
    'thuc-pham-do-uong',
    'thuc-pham-chuc-nang',
    'van-phong-pham-sach',
    'phu-kien-xe-may-o-to',
    'thu-cung',
    'noi-that-trang-tri-nha',
  ];

  if (genericCats.includes(key)) {
    const label = titleForSizeGuideSlug(key);
    return (
      <>
        <Heading>Hướng dẫn chọn kích cỡ — {label}</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Nhóm hàng này thường thể hiện kích thước bằng số trong mô tả: kích thước (cm, mm), khối lượng (g, kg), dung tích (ml, l),
          đường kính nhẫn hoặc chiều dài dây.
        </p>
        <p className="text-sm text-gray-700 mt-2">
          Trên trang sản phẩm của 188.com.vn, đọc đủ mục «Thông tin sản phẩm» và bảng biến thể; dùng thước dây đo tại nhà để so khớp.
        </p>
        <Note>Không có một bảng chung cho cả nhóm — mỗi mã hàng một thông số, nên căn vào tin bán của từng shop và NCC.</Note>
      </>
    );
  }

  return (
    <>
      <Heading>Chọn size trên 188.com.vn</Heading>
      <p className="text-sm text-gray-700 mt-2">
        Hãy ưu tiên phần mô tả và bảng kích cỡ của từng sản phẩm đã đăng. Nếu sản phẩm không ghi cỡ cụ thể, gửi câu hỏi trực tiếp cho cửa hàng trên trang sản phẩm.
      </p>
    </>
  );
}

export default function SizeGuideBody({
  categoryLevel1Slug,
  categoryLevel2Slug,
}: {
  categoryLevel1Slug: string;
  categoryLevel2Slug?: string | null;
}) {
  const segments = resolveSizeGuideSegments(categoryLevel1Slug, categoryLevel2Slug ?? null);
  return (
    <article className="px-1 pb-2">
      {segments.length === 2 ? (
        <p className="text-xs text-gray-500 mb-3">
          <Link href="/info/chon-size" className="hover:underline text-gray-600">
            Chọn size
          </Link>
          <span aria-hidden className="mx-1">
            /
          </span>
          <Link href={hrefChonSizeSegments([segments[0]])} className="hover:underline text-gray-700">
            {titleForSizeGuideSlug(segments[0])}
          </Link>
        </p>
      ) : null}
      <SizeGuideInner segments={segments} />
      {SOURCE_FIT_CAT1.has(segments[0]) ? <SourceFitNote /> : null}
      <p className="text-xs text-gray-500 mt-6 border-t pt-4">
        188.com.vn — thông tin chỉ mang tính tham khảo, không thay cho mô tả và chính sách đổi trả của từng sản phẩm.&nbsp;
        <Link href="/info/chon-size" className="text-[#ea580c] hover:underline">
          Danh sách hướng dẫn theo nhóm hàng
        </Link>
      </p>
    </article>
  );
}
