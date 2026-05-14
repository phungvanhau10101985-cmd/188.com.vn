/** Nhãn “tháng N/Y” đồng bộ SSR/client cho listing SEO + H1. */
export function getListingFreshnessMonthLabel(date = new Date()): string {
  let month = date.getMonth() + 1;
  let year = date.getFullYear();
  if (date.getDate() >= 20) {
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return `tháng ${month}/${year}`;
}
