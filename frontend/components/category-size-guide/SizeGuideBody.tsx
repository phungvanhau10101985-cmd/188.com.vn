'use client';

// Bảng số căn theo thang cỡ ôm thường gặp và cách quy đổi ra tem trên shop; phần hiển thị cho khách không cần nhắc xuất xứ nguồn.
import Link from 'next/link';
import {
  hrefChonSizeSegments,
  resolveSizeGuideSegments,
  titleForSizeGuideSlug,
} from '@/lib/category-size-guide-meta';

/** Bảng 2 cột: chiều dài chân (cm) ↔ cỡ in trên tem (chuẩn thường dùng ở shop Việt Nam). */
function ShoeTableMale() {
  const rows = [
    ['23,0', '36'],
    ['23,5', '37'],
    ['24,0', '38'],
    ['24,5', '39'],
    ['25,0', '40'],
    ['25,5', '41'],
    ['26,0', '41–42'],
    ['26,5', '42'],
    ['27,0', '43'],
    ['27,5', '43–44'],
    ['28,0', '44'],
    ['28,5', '45'],
    ['29,0', '45–46'],
  ];
  return (
    <table className="w-full text-sm border border-gray-200 border-collapse text-left mt-3">
      <thead>
        <tr className="bg-amber-100">
          <th className="p-2 border border-gray-200">Chiều dài chân (cm)</th>
          <th className="p-2 border border-gray-200">Cỡ giày (thường in trên tem / shop Việt Nam)</th>
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
    ['22,0', '35'],
    ['22,5', '36'],
    ['23,0', '36–37'],
    ['23,5', '37'],
    ['24,0', '38'],
    ['24,5', '39'],
    ['25,0', '39–40'],
    ['25,5', '40'],
    ['26,0', '41'],
    ['26,5', '41–42'],
    ['27,0', '42'],
    ['27,5', '43'],
  ];
  return (
    <table className="w-full text-sm border border-gray-200 border-collapse text-left mt-3">
      <thead>
        <tr className="bg-amber-100">
          <th className="p-2 border border-gray-200">Chiều dài chân (cm)</th>
          <th className="p-2 border border-gray-200">Cỡ giày (tem / shop Việt Nam)</th>
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
    ['S', '92–96', '44–46', '74–79', '90–94'],
    ['M', '97–101', '47–48', '79–82', '95–99'],
    ['L', '102–107', '49–51', '82–86', '100–106'],
    ['XL', '108–114', '52–54', '86–90', '107–112'],
    ['XXL', '115–120', '55–56', '90–95', '113–118'],
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

function ApparelFemaleTable() {
  const rows = [
    ['S', '84–88', '64–69', '90–93'],
    ['M', '88–92', '69–74', '93–96'],
    ['L', '92–96', '74–78', '96–100'],
    ['XL', '96–101', '78–84', '100–106'],
    ['XXL', '101–106', '84–92', '106–114'],
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
    ['12–18 tháng', '78–83', '9–11', '92–98'],
    ['2–3 tuổi', '88–93', '12–13', '100–106'],
    ['4–5 tuổi', '98–109', '16–17', '110–118'],
    ['6–7 tuổi', '110–122', '19–21', '120–132'],
    ['8–9 tuổi', '123–134', '22–26', '135–146'],
    ['10–11 tuổi', '135–144', '28–34', '147–154'],
    ['12–13 tuổi', '145–158', '36–45', '155–166'],
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

function Heading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-base font-bold text-gray-900 mt-4 first:mt-0">{children}</h2>;
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
        Bảng trên là quy đổi tham khảo theo cỡ tem phổ biến ở shop Việt Nam; từng hãng (đặc biệt sneakers) có thể lệch 1 cỡ — luôn đọc
        bảng kích cỡ trên trang sản phẩm của từng mã và hỏi shop khi không chắc.
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
        <li>{'<'} 10 cm: có thể AA hoặc A nhỏ tùy nhãn</li>
        <li>≈10–13 cm: thường A–B</li>
        <li>≈13–15 cm: thường C</li>
        <li>{'>'} 15 cm và form nặng: D trở lên — ưu tiên bảng nhãn từng mặt hàng và thử được thì hay nhất.</li>
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
        Vẫn căn vào chiều dài chân (cm) như giày bệt. Gót và mũi nhọn thường khiến cảm giác ôm cổ chân và ngón —
        có thể cần tăng nửa hoặc một cỡ so với sneaker của bạn, đặc biệt nếu bàn ngang và gót hẹp.
      </p>
      {wedding ? (
        <p className="text-sm text-gray-700 mt-2">
          Giày tiệc thường đi trong thời gian dài: ưu tiên form ổn gót và test đứng/ngồi; nếu mua online, căn chừng vào cỡ đang mang giày
          bệt cùng hãng (nếu có) và chiều ngang họng giày.
        </p>
      ) : null}
      <ShoeTableFemale />
      <Note>
        Độ cao gót (cm trong mô tả) ảnh hưởng lực bàn chân trước — thường chọn thoáng hơn một chút khi đế nghiêng và mũi nhọn. Luôn ưu
        tiên bảng kích cỡ và mô tả trên từng sản phẩm tại 188.com.vn.
      </Note>
    </>
  );
}

const CAT2_PAIR = {
  KIDS_SHOES: 'thoi-trang-tre-em/giay-dep-tre-em',
  BRA: 'do-lot-nu/bra-ao-nguc-nu',
  HEELS: 'giay-dep-nu/giay-cao-got-nu',
  WEDDING: 'giay-dep-nu/giay-cuoi-du-tiec-nu',
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
          Giữa hai cỡ: căn vào chiều dài cm. Form ôm có thể cần lớn hơn ~0,5 cỡ; mũi hẹp cũng dễ chật ngón — luôn ưu tiên mô tả và bảng trên trang sản phẩm.
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
        <Note>Giày cao gót / mũi nhọn có thể cần cỡ thoáng hơn một chút. Tham khảo thêm các trang nhóm con tương ứng trong mục Chọn size nếu sản phẩm thuộc danh mục đó.</Note>
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
        <Note>Bụng lớn hơn bảng tham khảo: có thể chọn lớn hơn một cỡ hoặc dòng co giãn.</Note>
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
        <Note>Đầm ôm vai–ngực trước; quần rộng ưu tiên eo và mông.</Note>
      </>
    );
  }

  if (key === 'do-lot-nam' || key === 'do-lot-nu') {
    return (
      <>
        <Heading>Đồ lót — căn vào cm vòng</Heading>
        <p className="text-sm text-gray-700 mt-2">
          Đo vòng eo thường mặc (cm) và vòng hông chỗ lớn nhất; so với bảng trên từng sản phẩm. Giữa hai cỡ chọn vừa, tránh siết quá eo.
        </p>
        <Note>Áo bra: xem thêm cỡ vành + cup trong trang «Bra áo ngực Nữ» trong danh sách nhóm con bên info.</Note>
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
          Riêng <strong>giày dép trẻ em</strong> nên căn chiều dài chân (cm): mở trang riêng cho nhóm con «Giày dép trẻ em» từ index chọn size.
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
      <p className="text-xs text-gray-500 mt-6 border-t pt-4">
        188.com.vn — thông tin chỉ mang tính tham khảo, không thay cho mô tả và chính sách đổi trả của từng sản phẩm.&nbsp;
        <Link href="/info/chon-size" className="text-[#ea580c] hover:underline">
          Danh sách hướng dẫn theo nhóm hàng
        </Link>
      </p>
    </article>
  );
}
