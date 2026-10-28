import { useEffect, useState } from 'react'
import type { DashboardMetadata, Pollutant } from '../types'

interface QualityRow { pollutant:string;valid_measurements:number;expected_hours:number;missing_hours:number;absent_slots?:number;missing_value_slots?:number;invalid_measurements:number;latest_observation_time:string|null }
interface Distribution { counts:Record<string,number>;series_days:number }
const labels:Record<string,string>={good:'Tốt',moderate:'Trung bình',poor:'Kém',unhealthy:'Xấu',very_unhealthy:'Rất xấu',hazardous:'Nguy hại',unavailable:'Chưa đủ điều kiện'}
const day=86400000,offset=7*3600000
function localMidnight(instant:string,end=false) {
  const value=Date.parse(instant)
  return new Date(Math.floor((value+offset)/day)*day-offset+(end?day:0)).toISOString()
}

export function GoldAnalyticsPanel({metadata,pollutant,provinceCode}:{metadata?:DashboardMetadata|null;pollutant:Pollutant;provinceCode:string}) {
  const [state,setState]=useState<{key:string;quality:QualityRow[];distribution:Distribution|null;error:string|null}>({key:'',quality:[],distribution:null,error:null})
  const timeline=metadata?.publishedTimelineId
  const compatibility=metadata?.compatibilityId
  const start=metadata?.queryStart ? localMidnight(metadata.queryStart) : undefined
  const end=metadata?.queryEnd ? localMidnight(metadata.queryEnd,true) : undefined
  const key=JSON.stringify([timeline,compatibility,start,end,provinceCode])
  useEffect(()=>{
    if(!timeline)return
    const controller=new AbortController()
    const params=new URLSearchParams({timeline_id:timeline})
    if(compatibility)params.set('compatibility_id',compatibility)
    if(start)params.set('start',start)
    if(end)params.set('end',end)
    const distribution=new URLSearchParams(params)
    if(provinceCode!=='all')distribution.set('admin_code',provinceCode)
    async function read(path:string) {
      const response=await fetch(path,{signal:controller.signal})
      if(!response.ok)throw new Error(`Gold analytics HTTP ${response.status}`)
      return response.json()
    }
    Promise.all([read(`/api/gold/history/quality?${params}`),read(`/api/gold/history/aqi-distribution?${distribution}`)])
      .then(([quality,distribution])=>{if(!controller.signal.aborted)setState({key,quality:quality.rows,distribution,error:null})})
      .catch((error:unknown)=>{if(!controller.signal.aborted)setState({key,quality:[],distribution:null,error:error instanceof Error?error.message:'Không thể đọc Gold analytics'})})
    return ()=>controller.abort()
  },[timeline,compatibility,start,end,provinceCode,key])
  if(!timeline)return null
  const ready=state.key===key
  const rows=ready?state.quality.filter(row=>row.pollutant===(pollutant==='aqi'?'pm25':pollutant)):[]
  const valid=rows.reduce((sum,row)=>sum+row.valid_measurements,0),expected=rows.reduce((sum,row)=>sum+row.expected_hours,0)
  return <section className="my-4 rounded-card border border-border bg-surface p-4" aria-label="Chất lượng nguồn và phân bố AQI ngày">
    <h2 className="text-sm font-semibold text-heading">Chất lượng nguồn và phân bố AQI ngày</h2>
    <p className="mt-1 text-xs text-muted">Ngày Việt Nam bao phủ khoảng đang đọc: {start && new Date(start).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})} → {end && new Date(end).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})} (Asia/Ho_Chi_Minh, end exclusive). Coverage tính trên tất cả chuỗi đã công bố; không đồng nghĩa độ chính xác quan trắc.</p>
    <p className="mt-1 text-xs text-muted">Coverage so với lịch phân tích 24 giờ/ngày. Nguồn native 3 giờ chỉ có 8 thời điểm/ngày; các slot còn lại không có observation, không tự chứng minh lỗi thu thập. QC invalid và thiếu giá trị được đếm riêng.</p>
    {!ready?<p role="status">Đang đọc Gold analytics…</p>:state.error?<p role="alert">{state.error}</p>:<>
      <p className="mt-2 text-sm">Mẫu hợp lệ {valid.toLocaleString('vi-VN')} / {expected.toLocaleString('vi-VN')} giờ kỳ vọng{expected?` · ${(100*valid/expected).toFixed(1)}%`:''} · Không dùng được {rows.reduce((sum,row)=>sum+row.missing_hours,0)} · Không có observation {rows.every(row=>typeof row.absent_slots==='number') ? rows.reduce((sum,row)=>sum+(row.absent_slots??0),0) : 'chưa xác minh'} · Thiếu giá trị {rows.every(row=>typeof row.missing_value_slots==='number') ? rows.reduce((sum,row)=>sum+(row.missing_value_slots??0),0) : 'chưa xác minh'} · QC invalid {rows.reduce((sum,row)=>sum+row.invalid_measurements,0)}</p>
      <p className="mt-1 text-xs text-muted">AQI theo tỉnh đang chọn: {state.distribution?.series_days ?? 0} series-days; mỗi series/ngày/method chỉ đếm một lần.</p>
      <ul className="mt-2 flex flex-wrap gap-3 text-xs">{Object.entries(state.distribution?.counts ?? {}).map(([category,count])=><li key={category}>{labels[category]??category}: <strong>{count}</strong></li>)}</ul>
      {metadata?.missingScopes?.length ? <p className="mt-2 text-xs text-muted">Có {metadata.missingScopes.length} khoảng chưa công bố hoặc đã rút lại; không đưa vào coverage của series-days đã công bố.</p>:null}
    </>}
  </section>
}
