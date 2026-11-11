import { fmt } from "./format";
import type { ReportPeriod, ReportRow } from "./report-data";

type PdfReport = {
  title: string; period: ReportPeriod; rows: ReportRow[]; daily: boolean; sample: boolean;
  averages: (number | null)[];
  extremes: { min: number | null; max: number | null }[];
};
const encode = (s: string) => new TextEncoder().encode(s);
const join = (parts: Uint8Array[]) => {
  const result = new Uint8Array(parts.reduce((n, part) => n + part.length, 0));
  let at = 0;
  for (const part of parts) { result.set(part, at); at += part.length; }
  return result;
};

// Embed high-resolution page images: Korean uses the browser's local fonts,
// so export needs no external font request and works in embedded browsers too.
function imagePdf(images: Uint8Array[], width: number, height: number) {
  const objects: Uint8Array[] = [];
  const pages = images.map((_, i) => `${3 + i * 3} 0 R`).join(" ");
  objects.push(encode("<< /Type /Catalog /Pages 2 0 R >>"));
  objects.push(encode(`<< /Type /Pages /Kids [${pages}] /Count ${images.length} >>`));
  images.forEach((jpeg, i) => {
    const page = 3 + i * 3;
    const content = "q 595.28 0 0 841.89 0 0 cm /Im0 Do Q";
    objects.push(encode(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources << /XObject << /Im0 ${page + 1} 0 R >> >> /Contents ${page + 2} 0 R >>`));
    objects.push(join([encode(`<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`), jpeg, encode("\nendstream")]));
    objects.push(encode(`<< /Length ${encode(content).length} >>\nstream\n${content}\nendstream`));
  });
  const parts = [encode("%PDF-1.4\n")];
  const offsets = [0];
  let size = parts[0].length;
  objects.forEach((object, i) => {
    offsets.push(size);
    const part = join([encode(`${i + 1} 0 obj\n`), object, encode("\nendobj\n")]);
    parts.push(part); size += part.length;
  });
  parts.push(encode(`xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${size}\n%%EOF`));
  return join(parts);
}

export async function downloadReportPdf(report: PdfReport) {
  await document.fonts.ready;
  const width = 1488, height = 2105;
  const canvas = document.createElement("canvas");
  canvas.width = width; canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("PDF 화면을 만들지 못했어요. 브라우저를 다시 열어 주세요.");
  const images: Uint8Array[] = [];
  const perPage = 20, pages = Math.ceil(report.rows.length / perPage);
  if (!pages) throw new Error("저장할 측정 기록이 없어요.");
  const write = (text: string, x: number, y: number, size = 24, color = "#243653", bold = false, maxWidth = 1200) => {
    ctx.font = `${bold ? 600 : 400} ${size}px "Malgun Gothic", "Noto Sans KR", sans-serif`;
    ctx.fillStyle = color;
    let shown = text;
    while (shown.length > 1 && ctx.measureText(shown).width > maxWidth) shown = shown.slice(0, -2) + "…";
    ctx.fillText(shown, x, y);
  };
  for (let page = 0; page < pages; page++) {
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, width, height);
    write("벽면 곰팡이 예보  /  환경 측정 리포트", 90, 92, 22, "#526686");
    write(report.title, 90, 163, 40, "#203353", true, 1300);
    write(`${report.period.from} — ${report.period.to}  ·  한국 시간  ·  ${report.daily ? "일별 평균" : "시간별 평균"}`, 90, 211, 23);
    if (report.sample) write("샘플 데이터 · 실제 측정 결과가 아닙니다.", 90, 254, 22, "#8a5264");
    ["평균 실내 온도", "평균 실내 습도", "평균 벽면 온도"].forEach((label, i) => {
      const x = 90 + i * 442;
      ctx.fillStyle = "#f2f5fb"; ctx.fillRect(x, 290, 424, 174);
      write(label, x + 24, 333, 23, "#536684");
      const unit = i === 1 ? "%" : "°C";
      write(`${fmt(report.averages[i])}${unit}`, x + 24, 385, 38, "#304b83", true);
      write(`최저 ${fmt(report.extremes[i]?.min)}${unit} · 최고 ${fmt(report.extremes[i]?.max)}${unit}`, x + 24, 421, 19, "#425777", false, 376);
      write("평균·최고·최저: 수신된 시간별 평균 기준", x + 24, 447, 17, "#596b86", false, 376);
    });
    ctx.fillStyle = "#e9eef8"; ctx.fillRect(90, 478, 1308, 62);
    ["측정 일시 / 센서", "실내 온도 (°C)", "실내 습도 (%)", "벽면 온도 (°C)"].forEach((label, i) => write(label, [108, 578, 861, 1142][i], 518, 22, "#344d75", true));
    report.rows.slice(page * perPage, (page + 1) * perPage).forEach((row, i) => {
      const y = 540 + i * 66;
      if (i % 2 === 1) { ctx.fillStyle = "#f7f9fc"; ctx.fillRect(90, y, 1308, 66); }
      const date = row.date.length === 10 ? row.date : new Date(row.date).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
      write(date, 108, y + 28, 23, "#334867", false, 440);
      write(row.probe, 108, y + 53, 18, "#5f6e85", false, 440);
      [row.air, row.humidity, row.wall].forEach((value, j) => write(fmt(value), [624, 910, 1190][j], y + 42, 27, ["#355b9b", "#675095", "#286d72"][j], true));
      ctx.strokeStyle = "#e1e6ef"; ctx.beginPath(); ctx.moveTo(90, y + 66); ctx.lineTo(1398, y + 66); ctx.stroke();
    });
    write("일별 값은 수신된 시간별 집계의 평균이며, 기록이 없는 날은 ‘—’로 표시합니다.", 90, 1930, 20, "#52647f");
    write("오늘은 현재까지의 기록입니다. 측정 환경을 이해하기 위한 참고자료입니다.", 90, 1965, 20, "#52647f");
    write(`벽면 곰팡이 예보  ·  ${report.sample ? "샘플 리포트" : "측정 리포트"}`, 90, 2030, 19, "#62728b");
    write(`${page + 1} / ${pages}`, 1290, 2030, 20, "#62728b");
    const binary = atob(canvas.toDataURL("image/jpeg", .94).split(",")[1]);
    images.push(Uint8Array.from(binary, char => char.charCodeAt(0)));
    // Let the browser update the progress indicator between pages.
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
  }
  const bytes = imagePdf(images, width, height);
  const url = URL.createObjectURL(new Blob([bytes.buffer as ArrayBuffer], { type: "application/pdf" }));
  const link = document.createElement("a");
  link.href = url; link.download = `환경측정_${report.period.from}_${report.period.to}${report.sample ? "_샘플" : ""}.pdf`;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
