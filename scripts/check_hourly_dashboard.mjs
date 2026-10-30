import { readFile, writeFile } from 'node:fs/promises'
const { chromium } = await import(process.argv[2] || process.env.PLAYWRIGHT_MODULE || 'playwright')
const generation=(await readFile('backend/data/samples/cams/eac4_provinces/CURRENT','utf8')).trim()
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||'/usr/bin/google-chrome',args:['--no-sandbox']})
const results=[]
try {
for(const width of [1440,768,390]) for(const route of ['/user','/admin']) {
 const page=await browser.newPage({viewport:{width,height:1000}})
 const errors=[],responses=[]
 page.on('pageerror',error=>errors.push(error.message))
 page.on('console',message=>{if(message.type()==='error') errors.push(message.text())})
 page.on('response',response=>{if(/\/api\/(?:admin\/)?dashboard\?/.test(response.url())) responses.push({url:response.url(),status:response.status()})})
 const top=async()=>{await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(120)}
 const choose=async(label)=>{await top();await page.getByRole('button',{name:'Chỉ số',exact:true}).click();await page.getByRole('listbox',{name:'Chỉ số',exact:true}).getByRole('option',{name:label,exact:true}).click()}
 await page.goto(`http://127.0.0.1:5181${route}`)
 const input=page.getByLabel('Mốc giờ Việt Nam')
 await input.waitFor()
 await page.waitForFunction(()=>Boolean(document.querySelector('input[type="datetime-local"]')?.value),null,{timeout:60000})
 await page.locator('.leaflet-container').waitFor()
 await page.waitForTimeout(400)
 const info=page.getByLabel('Thông tin nguồn và phương pháp')
 await info.click()
 const infoOverflow=await page.evaluate(()=>document.body.scrollWidth>innerWidth)
 await info.click()
 await page.screenshot({path:`reports/dashboard/science/${route.slice(1)}-${width}.png`,fullPage:true})
 const overflow=await page.evaluate(()=>({body:document.body.scrollWidth,viewport:innerWidth}))
 let mapGap=null,mapHeight=null
 if(route==='/admin') {
  const card=await page.locator('[data-map-variant="admin"]').boundingBox()
  const legend=await page.getByLabel('Chú giải màu').boundingBox()
  mapHeight=(await page.locator('.leaflet-container').boundingBox()).height
  mapGap=card.y+card.height-legend.y-legend.height
  if(mapGap>3||mapHeight<300) throw new Error(`Empty admin map space: ${mapGap}, viewport ${mapHeight}`)
 }
 const target=`/api/${route==='/admin'?'admin/':''}dashboard?`
 const selected=page.waitForResponse(r=>r.url().includes(target)&&r.url().includes('2025-12-30T01'))
 await input.fill('2025-12-30T08:00')
 const response=await selected,payload=await response.json()
 if(payload.provinceSnapshots.length!==34 || payload.provinceSnapshots.some(p=>['20333','22736'].includes(p.provinceCode))) throw new Error('Archipelagos counted as provinces')
 await top()
 await page.getByRole('button',{name:'Khu vực',exact:true}).click()
 const provinceOptions=await page.getByRole('listbox',{name:'Khu vực',exact:true}).getByRole('option').count()
 if(provinceOptions!==35) throw new Error('Expected all-country option plus 34 provinces: '+provinceOptions)
 await page.getByRole('button',{name:'Đóng lựa chọn',exact:true}).click()
 if(payload.metadata.generation!==generation||payload.dashboardTrendRecords.some(r=>r.date!=='2025-12-30T01:00:00Z')) throw new Error('Wrong generation/UTC hour')
 await page.getByRole('button',{name:'Giờ trước',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('input[type="datetime-local"]')?.value==='2025-12-30T07:00')
 await page.getByRole('button',{name:'Giờ sau',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('input[type="datetime-local"]')?.value==='2025-12-30T08:00')
 await page.getByRole('button',{name:'Khu vực',exact:true}).click()
 await page.getByRole('listbox',{name:'Khu vực',exact:true}).getByRole('option',{name:'Hà Nội',exact:true}).click()
 await page.getByRole('button',{name:'Chỉ số',exact:true}).click()
 const names=(await page.getByRole('listbox',{name:'Chỉ số',exact:true}).getByRole('option').allTextContents()).map(x=>x.replace('✓','').trim())
 if(JSON.stringify(names)!==JSON.stringify(['PM2.5','PM10','PM1','NO₂','SO₂','CO','O₃'])) throw new Error('Primary selector contains unsupported/non-surface quantities: '+names)
 await page.getByRole('listbox',{name:'Chỉ số',exact:true}).getByRole('option',{name:'CO',exact:true}).click()
 if(route==='/user') await page.getByText('Chi tiết quan sát và xuất CSV',{exact:true}).click()
 const table=page.locator('.observation-panel')
 const sourceRow=payload.dashboardTrendRecords.find(r=>r.provinceCode==='01')
 const verified=[]
 const metrics=width===1440?['pm25','pm10','pm1','no2','so2','co','o3']:['co']
 const labels={pm25:'PM2.5',pm10:'PM10',pm1:'PM1',no2:'NO₂',so2:'SO₂',co:'CO',o3:'O₃'}
 for(const metric of metrics) {
  await choose(labels[metric]);await page.waitForTimeout(100)
  const text=await table.innerText()
  const value=sourceRow[metric]?.toLocaleString('vi-VN',{maximumFractionDigits:3})
  const unit=metric==='co'?'mg/m³':'µg/m³'
  if(!text.includes(value)||!text.includes(unit)) throw new Error(`Value/unit mismatch: ${metric}`)
  verified.push(metric)
 }
 await choose('CO')
 if(route==='/admin') {
  await page.getByRole('tab',{name:'Chất lượng dữ liệu',exact:true}).click()
  await page.getByText('Nguồn, chuyển đổi & phiên bản ⓘ',{exact:true}).click()
  await page.getByText(`Generation: ${generation}`,{exact:false}).waitFor()
  if(width===1440) {
   await top();await page.getByLabel('Nhóm dữ liệu').selectOption('weather')
   await page.waitForTimeout(150)
   if(!(await table.innerText()).includes('°C')) throw new Error('Weather unit/category mismatch')
   await page.getByLabel('Nhóm dữ liệu').selectOption('columns')
   await page.getByRole('button',{name:'Chỉ số',exact:true}).click()
   const advanced=await page.getByRole('listbox',{name:'Chỉ số',exact:true}).innerText()
   if(!advanced.includes('tổng cột')||advanced.includes('PM2.5')) throw new Error('Column category not isolated')
   await page.getByRole('button',{name:'Đóng lựa chọn',exact:true}).click()
   await page.getByLabel('Nhóm dữ liệu').selectOption('pollutants');await choose('CO')
  }
 }
 const cells=await table.locator('tbody tr').allTextContents()
 if(cells.length!==1||!cells[0].includes('Hà Nội')) throw new Error('Province/table scope mismatch')
 const download=page.waitForEvent('download')
 await table.getByRole('button',{name:'Xuất CSV',exact:true}).click()
 const file=await download,csvPath=`reports/dashboard/science/${route.slice(1)}-${width}.csv`
 await file.saveAs(csvPath)
 const csv=await readFile(csvPath,'utf8')
 if(!csv.includes('2025-12-30T01:00:00Z')||!csv.includes('"CO"')||!csv.includes('mg/m³')||!csv.includes('Hà Nội')) throw new Error('CSV scope/units mismatch')
 for(const [island,parent] of [['Hoàng Sa','Đà Nẵng'],['Trường Sa','Khánh Ho']]) {
  await page.locator(`path[aria-label^="Quần đảo ${island}"]`).evaluate(element=>element.dispatchEvent(new MouseEvent('click',{bubbles:true})))
  await page.waitForTimeout(100)
  // On mobile, the sticky toolbar can be collapsed while the map is in view.
  if(!(await page.locator('button[aria-label="Khu vực"]').getAttribute('title')).includes(parent)) throw new Error('Island did not select parent province: '+island)
  if(await page.locator('.leaflet-province-selection-pane path').count()!==2) throw new Error('Parent and island must both be highlighted')
 }
 await top();await page.getByRole('button',{name:'24 giờ',exact:true}).click();await page.waitForTimeout(200)
 if(width===1440) for(const label of ['Ngày','Tháng','1 giờ']) {
  const button=page.getByRole('button',{name:label,exact:true});await button.click();await page.waitForTimeout(300)
  if(await button.getAttribute('aria-pressed')!=='true') throw new Error('Resolution switch failed: '+label)
 }
 results.push({route,width,generation,overflow,infoOverflow,errors,mapGap,mapHeight,verified,tableRows:cells.length,responses})
 await page.close()
}
} finally {await browser.close()}
await writeFile('reports/dashboard/science/browser-results.json',JSON.stringify(results,null,2))
if(results.some(r=>r.errors.length||r.infoOverflow||r.overflow.body>r.overflow.viewport||r.responses.some(x=>x.status!==200))) throw new Error('Browser error/overflow')
console.log(JSON.stringify(results,null,2))
