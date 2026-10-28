// Inspect UI using saved responses obtained from the real FastAPI/Trino tests.
// API integration itself is verified separately by verify_gold_serving.py.
const { chromium } = await import(process.argv[2] || process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
import fs from 'node:fs/promises'
const live=process.argv.includes('--live')
const suffix=live?'-live':''
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  const errors = []
  const apiRequests=[]
  page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/'))apiRequests.push(request.url())})
  page.on('pageerror',error=>errors.push(String(error)))
  let data = JSON.parse(await fs.readFile('reports/gold/gold_pilot-dashboard.json','utf8'))
  let admin = JSON.parse(await fs.readFile('reports/gold/gold_pilot-admin-dashboard.json','utf8'))
  if(live) {
    data=await (await page.request.get('http://127.0.0.1:5178/api/dashboard?resolution=hourly')).json()
    admin=await (await page.request.get('http://127.0.0.1:5178/api/admin/dashboard?resolution=hourly')).json()
    if(data.provinceSnapshots?.length!==34 || admin.provinceSnapshots?.length!==34)throw new Error('Invalid live Gold response')
  }
  await page.route('**/*', async route => {
    const url=new URL(route.request().url())
    if(!live && url.pathname.startsWith('/api/')) return route.fulfill({json:url.pathname.includes('/admin/')?admin:data})
    if(!['127.0.0.1','localhost'].includes(url.hostname)) return route.abort()
    return route.continue()
  })
  await page.goto('http://127.0.0.1:5178/user',{waitUntil:'networkidle'})
  await page.getByText('CAMS EAC4 · mô hình',{exact:true}).first().waitFor()
  await page.screenshot({path:`reports/gold/user-pilot${suffix}.png`,fullPage:true})
  await page.getByRole('button',{name:'Chọn khoảng thời gian',exact:true}).first().click()
  await page.getByRole('button',{name:'Chọn giờ bắt đầu UTC',exact:true}).click()
  const hourCount=await page.getByRole('group',{name:'Giờ bắt đầu UTC',exact:true}).getByRole('button').count()
  if(hourCount!==24)throw new Error('Expected 24 hourly slots, found '+hourCount)
  await page.screenshot({path:`reports/gold/hourly-picker${suffix}.png`,fullPage:true})
  await page.goto('http://127.0.0.1:5178/admin',{waitUntil:'networkidle'})
  await page.getByText('CAMS EAC4 · mô hình',{exact:true}).first().waitFor()
  await page.screenshot({path:`reports/gold/admin-pilot${suffix}.png`,fullPage:true})
  if(apiRequests.some(url=>new URL(url).searchParams.get('resolution')==='3h'))throw new Error('Gold UI default must request hourly, not 3h')
  const result={api_requests:apiRequests,source:live?'live Vite -> FastAPI -> Trino -> Iceberg':'saved real-stack API responses',published_release_id:data.metadata?.publishedReleaseId,page_errors:errors,province_count:data.provinceSnapshots.length,
    hour_picker_count:hourCount,hourly_mode:await page.getByRole('button',{name:'1 giờ',exact:true}).count(),screenshots:[`user-pilot${suffix}.png`,`hourly-picker${suffix}.png`,`admin-pilot${suffix}.png`]}
  await fs.writeFile(`reports/gold/ui-checks${suffix}.json`,JSON.stringify(result,null,2))
  if(errors.length)throw new Error(errors.join('\n'))
  console.log(JSON.stringify(result))
} finally {await browser.close()}
