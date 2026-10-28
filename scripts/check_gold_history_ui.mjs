import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
const {chromium}=await import(process.argv[2] || process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const base=process.env.GOLD_UI_BASE_URL || 'http://127.0.0.1:5178'
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']})
try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}})
  const errors=[],requests=[],responses=[]
  page.on('pageerror',error=>errors.push(String(error)))
  page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/'))requests.push(request.url())})
  page.on('response',response=>{if(new URL(response.url()).pathname.startsWith('/api/'))responses.push({url:response.url(),status:response.status()})})
  await page.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort())
  const params='start=2025-12-29T17:00:00Z&end=2026-01-01T17:00:00Z'
  const result={}
  for(const [resolution,count] of [['hourly',72],['daily',3],['monthly',2]]) {
    const response=await page.request.get(`${base}/api/gold/history?${params}&resolution=${resolution}`)
    assert.equal(response.status(),200,await response.text())
    const data=await response.json();assert.equal(data.rows.length,count)
    assert.equal(data.missing_scopes.length,0)
    result[resolution]={rows:data.rows.length,timeline:data.published_timeline_id,releases:data.published_release_ids.length}
  }
  const dashboard=await (await page.request.get(`${base}/api/dashboard?resolution=hourly`)).json()
  assert.equal(dashboard.provinceSnapshots.length,34)
  assert.equal(dashboard.dashboardTrendRecords.length,72)
  assert.equal(dashboard.metadata.metrics.co.mapScale.version,'analytical-concentration-colors-v1')
  await page.goto(`${base}/user`,{waitUntil:'networkidle'})
  await page.getByText(/analytical-concentration-colors-v1/).first().waitFor()
  await page.screenshot({path:'reports/gold/readiness/history-user.png',fullPage:true})
  await page.getByRole('button',{name:'Chọn khoảng thời gian',exact:true}).first().click()
  await page.getByRole('button',{name:'Chọn giờ bắt đầu UTC',exact:true}).click()
  assert.equal(await page.getByRole('group',{name:'Giờ bắt đầu UTC',exact:true}).getByRole('button').count(),24)
  await page.goto(`${base}/admin`,{waitUntil:'networkidle'})
  await page.getByText(/analytical-concentration-colors-v1/).first().waitFor()
  await page.getByRole('button',{name:'Ngày',exact:true}).click()
  await page.waitForResponse(r=>r.url().includes('/api/admin/dashboard?') && r.url().includes('resolution=daily'))
  await page.getByText(/Trung bình mẫu thực trong ngày/).first().waitFor()
  await page.getByRole('button',{name:'Tháng',exact:true}).click()
  await page.getByText(/Trung bình mẫu thực trong tháng/).first().waitFor()
  await page.getByRole('region',{name:'Chất lượng nguồn và phân bố AQI ngày'}).getByText(/3 series-days/).waitFor()
  const qualityPanel=await page.getByRole('region',{name:'Chất lượng nguồn và phân bố AQI ngày'}).innerText()
  assert.match(qualityPanel,/71 \/ 72/ )
  await page.getByRole('columnheader',{name:'Thời gian (UTC+7)',exact:true}).waitFor()
  const downloadPromise=page.waitForEvent('download')
  await page.getByRole('region',{name:'Bảng dữ liệu theo thời gian',exact:true}).getByRole('button',{name:'Xuất CSV',exact:true}).click()
  const download=await downloadPromise
  const csv=await fs.readFile(await download.path(),'utf8')
  assert.match(csv,/Mui_gio/)
  assert.match(csv,/Asia\/Ho_Chi_Minh/)
  assert.equal(csv.includes('Thoi_gian_UTC'),false)
  await fs.writeFile('reports/gold/readiness/history-monthly.csv',csv)
  result.admin_analytics={calendar_timezone:'Asia/Ho_Chi_Minh',series_days:3,valid_hours:71,expected_hours:72,rendered_text:qualityPanel}
  await page.screenshot({path:'reports/gold/readiness/history-admin-monthly.png',fullPage:true})
  assert.deepEqual(errors,[])
  assert.equal(responses.filter(r=>r.status>=500).length,0,JSON.stringify(responses))
  assert.equal(requests.some(url=>new URL(url).searchParams.get('resolution')==='3h'),false)
  result.browser={province_count:34,hour_picker_count:24,page_errors:errors,requests,responses,source:'live Vite → FastAPI → Trino → Iceberg'}
  await fs.writeFile('reports/gold/readiness/history-ui.json',JSON.stringify(result,null,2))
  console.log(JSON.stringify(result))
}finally{await browser.close()}
