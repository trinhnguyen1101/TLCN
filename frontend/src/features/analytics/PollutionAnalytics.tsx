import { usePagination } from '../../hooks/usePagination'
import { Pagination } from '../../components/ui/Pagination'
import { useId, useMemo } from 'react'
import { Button } from '../../components/ui/Button'
import { DataState } from '../../components/dashboard/DataState'
import { DashboardSkeleton } from '../../components/dashboard/DashboardSkeleton'
import { METRIC_META } from '../../services/metricMetadata'
import type { DashboardAnalytics, DashboardFiltersValue, ProvinceRank } from '../../types/dashboard'
import './PollutionAnalytics.css'

interface Props {
  data: DashboardAnalytics | null
  loading: boolean
  error: string | null
  filters: DashboardFiltersValue
  onChange: (filters: DashboardFiltersValue) => void
  onRetry: () => void
}
const EMPTY_ROWS: ProvinceRank[] = []
const number = (value: number | null | undefined) =>
  value == null ? '—' : value.toLocaleString('vi-VN', { maximumFractionDigits: 3 })
const average = (values: number[]) =>
  values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
const coverage = (row: ProvinceRank) => `${row.validCount}/${row.expectedCount} tháng`

function buildHeatmap(data: DashboardAnalytics | null, provinceCode: string, metric: string) {
  const ranking = data?.rankings.find((item) => item.metric === metric)
  if (!data || !ranking)
    return {
      periods: [] as string[],
      rows: [] as Array<{ province: ProvinceRank; values: Array<number | null> }>,
      annual: false,
    }
  const annual = data.months.length > 24
  const periods = [...new Set(data.months.map((month) => (annual ? month.slice(0, 4) : month)))]
  const leaders = ranking.rows.slice(0, 8)
  const chosen = ranking.rows.find((row) => row.provinceCode === provinceCode)
  const visible = chosen && !leaders.includes(chosen) ? [...leaders, chosen] : leaders
  return {
    annual,
    periods,
    rows: visible.map((province) => ({
      province,
      values: periods.map((period) =>
        average(
          data.timeline
            .filter((point) => point.date.startsWith(period))
            .map((point) => point.values[province.provinceCode])
            .filter((value): value is number => value != null),
        ),
      ),
    })),
  }
}

function buildHistogram(rows: ProvinceRank[]) {
  const values = rows.map((row) => row.mean!).filter((value) => value != null)
  if (!values.length) return []
  const min = Math.min(...values),
    max = Math.max(...values)
  if (min === max) return [{ min, max, count: values.length }]
  const step = (max - min) / 5
  return Array.from({ length: 5 }, (_, index) => ({
    min: min + index * step,
    max: min + (index + 1) * step,
    count: values.filter((value) => Math.min(4, Math.floor((value - min) / step)) === index).length,
  }))
}

export function PollutionAnalytics({ data, loading, error, filters, onChange, onRetry }: Props) {
  const id = useId()
  const ranking = data?.rankings.find((item) => item.metric === filters.pollutant)
  const rows = ranking?.rows ?? EMPTY_ROWS
  const pagination = usePagination(rows.length, JSON.stringify(filters))
  const metric = METRIC_META[filters.pollutant]
  const unit = ranking?.unit ?? metric.unit
  const selected = rows.find((row) => row.provinceCode === filters.provinceCode)
  const scopeName =
    filters.provinceCode === 'all'
      ? 'Toàn quốc'
      : (selected?.provinceName ??
        data?.provinceSnapshots.find((p) => p.provinceCode === filters.provinceCode)?.provinceName ??
        'Tỉnh đang chọn')
  const selectProvince = (code: string) => onChange({ ...filters, provinceCode: code })
  const heatmap = useMemo(
    () => buildHeatmap(data, filters.provinceCode, filters.pollutant),
    [data, filters.provinceCode, filters.pollutant],
  )
  const histogram = buildHistogram(rows)
  const heatValues = heatmap.rows
    .flatMap((row) => row.values)
    .filter((value): value is number => value !== null)
  const heatMin = Math.min(...heatValues),
    heatMax = Math.max(...heatValues)
  const minimum = Math.min(0, ...rows.map((row) => row.mean ?? 0))
  const maximum = Math.max(0, ...rows.map((row) => row.mean ?? 0))
  const magnitude = Math.max(maximum - minimum, Number.EPSILON)
  const download = () => {
    const cells = [
      [
        'Hạng',
        'Tỉnh',
        'Chỉ số',
        'Trung bình',
        'Thấp nhất',
        'Cao nhất',
        'Đơn vị',
        'Tháng hợp lệ',
        'Tháng trong kỳ',
        'Kỳ',
      ],
      ...rows.map((row) => [
        row.rank,
        row.provinceName,
        metric.label,
        row.mean,
        row.minimum,
        row.maximum,
        unit,
        row.validCount,
        row.expectedCount,
        data?.months.join('; '),
      ]),
    ]
    const csv = cells
      .map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(','))
      .join('\n')
    const url = URL.createObjectURL(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `xep-hang-${filters.pollutant}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }
  return (
    <section className="pollution-analytics" aria-labelledby={`${id}-title`} aria-busy={loading || Boolean(error)}>
      <div className="analytics-heading">
        <div>
          <h2 id={`${id}-title`}>Thống kê & xếp hạng theo chất</h2>
          <p>{metric.label} · {scopeName} · {loading ? 'Đang cập nhật kỳ dữ liệu' : `${data?.months.length ?? 0} tháng trong kỳ`}</p>
        </div>
        {filters.provinceCode !== 'all' && (
          <Button onClick={() => selectProvince('all')}>← Về toàn quốc</Button>
        )}
      </div>
      <p className="analytics-note">
        Thống kê từ các giá trị trung bình tháng hợp lệ; mỗi tỉnh–tháng có trọng số bằng nhau. Xếp hạng toàn
        quốc giữ nguyên phạm vi thời gian để đối chiếu tỉnh đang chọn. Giá trị thiếu không được tính là 0.
      </p>
      {error && (
        <div role="alert" className="analytics-error">
          {error} <Button onClick={onRetry}>Thử lại phân tích</Button>
        </div>
      )}
      {loading && !data && <DashboardSkeleton variant="chart" loading />}
      {!loading && !error && !data && <p role="status">Chưa có dữ liệu phân tích.</p>}
      {data && (
        <div className="analytics-results" aria-hidden={loading || Boolean(error)}>
          <div className="analytics-stats">
            {[
              ['Trung vị', number(data.summary.median), unit],
              [
                'Thấp nhất / Cao nhất',
                `${number(data.summary.minimum)} / ${number(data.summary.maximum)}`,
                unit,
              ],
              [
                'Độ phủ dữ liệu',
                `${data.summary.validCount}/${data.summary.expectedCount}`,
                'số tỉnh–tháng hợp lệ / số có thể có trong kỳ nguồn',
              ],
              [
                'Vị trí toàn quốc',
                filters.provinceCode === 'all'
                  ? `${data.provinceCount} tỉnh`
                  : selected
                    ? `#${selected.rank} / ${rows.length}`
                    : 'Chưa xếp hạng',
                filters.provinceCode === 'all'
                  ? 'có dữ liệu chỉ số đang chọn'
                  : `${number(selected?.mean)} ${unit} trung bình`,
              ],
            ].map(([label, value, detail]) => (
              <article className="analytics-stat" key={label}>
                <p>{label}</p>
                <strong>{value}</strong>
                <span>{detail}</span>
              </article>
            ))}
          </div>
          <div className="analytics-grid">
            <section className="analytics-panel" aria-labelledby={`${id}-rank`}>
              <header>
                <div>
                  <h3 id={`${id}-rank`}>Tỉnh có {metric.label} cao nhất</h3>
                  <p>Trung bình kỳ · {unit} · chọn tỉnh để xem chi tiết</p>
                </div>
                <Button onClick={download} disabled={!rows.length}>
                  Xuất CSV
                </Button>
              </header>
              <DataState
                isEmpty={!rows.length}
                emptyMessage="Không có tỉnh đủ dữ liệu cho chỉ số và thời gian này."
              >
                <ol className="analytics-ranking">
                  {rows.slice(pagination.offset, pagination.offset + pagination.pageSize).map((row) => (
                    <li key={row.provinceCode}>
                      <button
                        type="button"
                        aria-pressed={filters.provinceCode === row.provinceCode}
                        onClick={() => selectProvince(row.provinceCode)}
                        title={`${row.provinceName}: ${number(row.mean)} ${unit}; ${coverage(row)}`}
                      >
                        <span className="rank-position">{row.rank}</span>
                        <span className="rank-main">
                          <span>{row.provinceName}</span>
                          <span className="rank-track">
                            <i
                              style={{
                                marginLeft: `${(((row.mean ?? 0) < 0 ? (row.mean ?? 0) - minimum : -minimum) / magnitude) * 100}%`,
                                width: `${(Math.abs(row.mean ?? 0) / magnitude) * 100}%`,
                              }}
                            />
                          </span>
                        </span>
                        <span className="rank-value">
                          <strong>{number(row.mean)}</strong>
                          <small>{coverage(row)}</small>
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
                <Pagination {...pagination} label="Phân trang xếp hạng tỉnh" />
              </DataState>
              <p className="analytics-note">
                Thứ hạng giảm dần theo trung bình các tháng có dữ liệu; giá trị bằng nhau cùng hạng. Độ phủ
                khác nhau có thể ảnh hưởng so sánh.
              </p>
            </section>
            <section className="analytics-panel" aria-labelledby={`${id}-distribution`}>
              <header>
                <div>
                  <h3 id={`${id}-distribution`}>Phân bố giữa các tỉnh</h3>
                  <p>
                    Số tỉnh theo khoảng {metric.label} trung bình ({unit})
                  </p>
                </div>
              </header>
              <DataState isEmpty={!histogram.length} emptyMessage="Không có dữ liệu phân bố.">
                <div
                  className="analytics-histogram"
                  role="img"
                  aria-label={`Phân bố ${rows.length} tỉnh theo ${metric.label}`}
                >
                  {histogram.map((bin, index) => (
                    <div key={index} className="histogram-bin">
                      <strong>{bin.count}</strong>
                      <div>
                        <i
                          style={{
                            height: `${(bin.count / Math.max(...histogram.map((item) => item.count), 1)) * 100}%`,
                          }}
                        />
                      </div>
                      <span>
                        {number(bin.min)}
                        <br />– {number(bin.max)}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="analytics-note">
                  {rows.length} tỉnh có dữ liệu. Các khoảng liền nhau không trùng biên; khoảng cuối gồm cả giá
                  trị cao nhất.
                </p>
              </DataState>
              <h3 className="mt-6">Chi tiết tỉnh đang chọn</h3>
              {selected ? (
                <dl className="analytics-detail">
                  <div>
                    <dt>Tỉnh / thành</dt>
                    <dd>{selected.provinceName}</dd>
                  </div>
                  <div>
                    <dt>Trung bình</dt>
                    <dd>
                      {number(selected.mean)} {unit}
                    </dd>
                  </div>
                  <div>
                    <dt>Trung vị</dt>
                    <dd>
                      {number(selected.median)} {unit}
                    </dd>
                  </div>
                  <div>
                    <dt>Thấp nhất – cao nhất</dt>
                    <dd>
                      {number(selected.minimum)} – {number(selected.maximum)} {unit}
                    </dd>
                  </div>
                  <div>
                    <dt>Độ phủ</dt>
                    <dd>{coverage(selected)}</dd>
                  </div>
                </dl>
              ) : (
                <p className="analytics-note">
                  {filters.provinceCode === 'all'
                    ? 'Chọn một tỉnh trên biểu đồ xếp hạng hoặc bản đồ.'
                    : 'Tỉnh đang chọn chưa có dữ liệu trong kỳ.'}
                </p>
              )}
            </section>
          </div>
          <section className="analytics-panel" aria-labelledby={`${id}-heat`}>
            <header>
              <div>
                <h3 id={`${id}-heat`}>Diễn biến theo tỉnh và {heatmap.annual ? 'năm' : 'tháng'}</h3>
                <p>
                  8 tỉnh đứng đầu và tỉnh đang chọn · {metric.label} ({unit}). Chọn ô để đi sâu theo tỉnh và
                  thời gian.
                </p>
              </div>
              {filters.month !== 'all' && (
                <Button onClick={() => onChange({ ...filters, month: 'all' })}>Xem các tháng</Button>
              )}
            </header>
            <DataState isEmpty={!heatmap.rows.length} emptyMessage="Chưa có dữ liệu theo tỉnh và thời gian.">
              <div
                className="analytics-heatmap-scroll"
                tabIndex={0}
                role="region"
                aria-label="Ma trận tỉnh và thời gian, cuộn ngang để xem thêm"
              >
                <table className="analytics-heatmap">
                  <thead>
                    <tr>
                      <th scope="col">Tỉnh / thành</th>
                      {heatmap.periods.map((period) => (
                        <th scope="col" key={period}>
                          {heatmap.annual ? period : `${period.slice(5)}/${period.slice(2, 4)}`}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {heatmap.rows.map((row) => (
                      <tr key={row.province.provinceCode}>
                        <th scope="row">
                          <button onClick={() => selectProvince(row.province.provinceCode)}>
                            {row.province.provinceName}
                          </button>
                        </th>
                        {row.values.map((value, index) => (
                          <td key={heatmap.periods[index]}>
                            <button
                              disabled={value === null}
                              style={
                                value === null
                                  ? undefined
                                  : {
                                      background: `hsl(174 52% ${18 + ((value - heatMin) / (heatMax - heatMin || 1)) * 28}%)`,
                                      color:
                                        value !== null && (value - heatMin) / (heatMax - heatMin || 1) > 0.6
                                          ? '#061c1b'
                                          : '#ecfdf5',
                                    }
                              }
                              aria-label={`${row.province.provinceName}, ${heatmap.periods[index]}: ${number(value)} ${unit}. Xem chi tiết`}
                              onClick={() =>
                                onChange({
                                  ...filters,
                                  provinceCode: row.province.provinceCode,
                                  year: Number(heatmap.periods[index].slice(0, 4)),
                                  month: heatmap.annual ? 'all' : Number(heatmap.periods[index].slice(5)),
                                })
                              }
                            >
                              {number(value)}
                            </button>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="analytics-note">
                Màu từ đậm đến sáng: {number(heatMin)} → {number(heatMax)} {unit}. Dấu — là thiếu dữ liệu.{' '}
                {heatmap.annual && 'Gộp trung bình các tháng hợp lệ theo năm khi kỳ dài hơn 24 tháng.'}
              </p>
            </DataState>
          </section>
          <section aria-labelledby={`${id}-all`}>
            <h3 id={`${id}-all`} className="analytics-section-title">
              Dẫn đầu theo từng chất và chỉ số aerosol
            </h3>
            <p className="analytics-note">
              Mỗi bảng dùng đơn vị riêng. Các chỉ số tổng cột và AOD không phải nồng độ sát mặt đất hoặc AQI.
            </p>
            <div className="analytics-leaders">
              {data.rankings
                .filter((item) => !['t2m', 'd2m', 'sp', 'mslp', 'u10', 'v10'].includes(item.metric))
                .map((item) => (
                  <article className="analytics-panel" key={item.metric}>
                    <h4>
                      {METRIC_META[item.metric].label} <span>{item.unit}</span>
                    </h4>
                    {item.rows.length ? (
                      <ol>
                        {item.rows.slice(0, 3).map((row) => (
                          <li key={row.provinceCode}>
                            <button
                              onClick={() =>
                                onChange({
                                  ...filters,
                                  pollutant: item.metric,
                                  provinceCode: row.provinceCode,
                                })
                              }
                            >
                              <span>
                                #{row.rank} {row.provinceName}
                              </span>
                              <strong>{number(row.mean)}</strong>
                            </button>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="analytics-note">Chưa có dữ liệu trong kỳ.</p>
                    )}
                    <Button onClick={() => onChange({ ...filters, pollutant: item.metric })}>
                      Xem xếp hạng {METRIC_META[item.metric].label}
                    </Button>
                  </article>
                ))}
            </div>
          </section>
        </div>
      )}
      {(loading || error) && data && <div className="analytics-refresh-overlay" role="status"><DashboardSkeleton variant="chart" loading={loading} /></div>}
    </section>
  )
}
