import type { DashboardMetadata, Pollutant } from '../types'
import { formatDateTime } from '../../../utils/dates'

export function SourceDetails({metadata,metric}: {metadata?:DashboardMetadata|null;metric:Pollutant}) {
  const info=metadata?.metrics[metric]
  return <details className="relative shrink-0 text-xs">
    <summary className="cursor-pointer list-none rounded-full border border-accent-border bg-accent-soft px-3 py-1.5 text-accent" aria-label="Thông tin nguồn và phương pháp">CAMS EAC4 · {metadata?.temporalOrigin==='interpolated'?'Nội suy 1 giờ':'Mô hình'} ⓘ</summary>
    <div className="absolute right-0 top-full z-[1100] mt-2 max-h-[80vh] overflow-auto w-[min(24rem,calc(100vw-2rem))] max-sm:fixed max-sm:inset-x-4 max-sm:top-20 max-sm:w-auto rounded-xl border border-border bg-surface p-4 text-xs leading-relaxed text-secondary shadow-card">
      <h2 className="mb-3 font-semibold text-heading">Nguồn & phương pháp</h2>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2"><dt>Thời gian</dt><dd>{formatDateTime(metadata?.start)} → {formatDateTime(metadata?.end)} UTC+7</dd><dt>Độ phân giải</dt><dd>Phân tích gốc 3 giờ → hiển thị 1 giờ; các slot nội suy không độc lập.</dd><dt>Nội suy</dt><dd>PCHIP: chất ô nhiễm. Tuyến tính: khí tượng.</dd><dt>Chỉ số</dt><dd>{info?.displayName??metric} · {info?.quantity??'—'}</dd><dt>Đơn vị</dt><dd>{info?.sourceUnit??'—'} → {info?.unit??'—'}</dd><dt>Tầng nguồn</dt><dd>{info?.sourceLevelType??'—'} · {info?.sourceLevel??'—'}</dd><dt>Chuyển đổi</dt><dd>{info?.conversionMethod??'—'}{info?.mmrMassBasis&&` · ${info.mmrMassBasis}`}</dd></dl>
      {info?.densityAssumption&&<p className="mt-3">{info.densityAssumption}</p>}
      <p className="mt-3">Ước tính CAMS, không phải số đo trạm. Không suy AQI từ nội suy giờ; khí tổng cột tách riêng nồng độ bề mặt.</p>
      <p className="mt-3 break-all font-mono text-[.65rem] text-muted">{metadata?.generation??'—'}</p>
    </div>
  </details>
}
