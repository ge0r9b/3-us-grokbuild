# usage: python3 tests/sort-under-search.py URL
# Confirms the sort button (#laSort) is hidden whenever search / full-screen filter (foldfs) is open (t239).
import asyncio,sys
from playwright.async_api import async_playwright
base=sys.argv[1]; fails=0
def chk(name,ok,info=''):
  global fails
  fails+=0 if ok else 1; print('OK  ' if ok else 'FAIL',name,info,flush=True)
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for W,H,t in((390,780,'ph'),(1280,800,'dk')):
      pg=await b.new_page(viewport={"width":W,"height":H})
      await pg.goto(base,wait_until="networkidle"); await pg.wait_for_timeout(2000)
      # enter list-all so sort button is eligible to show
      await pg.evaluate("()=>window.__allPick()"); await pg.wait_for_timeout(1000)
      await pg.evaluate("()=>{ if(!document.body.classList.contains('foldfs')) document.getElementById('bGeo').click(); }"); await pg.wait_for_timeout(800)
      await pg.evaluate("()=>document.querySelector('li.la-row').click()"); await pg.wait_for_timeout(2500)
      # sort should be visible in list mode
      vis=await pg.evaluate("()=>{const s=document.getElementById('laSort'); return s && getComputedStyle(s).display!=='none' && s.offsetParent!==null}")
      chk(t+' sort visible in list-all',vis)
      # open search / foldfs
      await pg.evaluate("()=>{ if(!document.body.classList.contains('foldfs')) document.getElementById('bSearch').click(); }"); await pg.wait_for_timeout(800)
      hidden=await pg.evaluate("()=>{const s=document.getElementById('laSort'); return !s || getComputedStyle(s).display==='none' || s.offsetParent===null}")
      chk(t+' sort hidden under search/foldfs (t239)',hidden)
      # close search
      await pg.evaluate("()=>{ if(document.body.classList.contains('foldfs')) document.getElementById('bSearch').click(); }"); await pg.wait_for_timeout(600)
      vis2=await pg.evaluate("()=>{const s=document.getElementById('laSort'); return s && getComputedStyle(s).display!=='none' && s.offsetParent!==null}")
      chk(t+' sort returns after closing search',vis2)
    await b.close()
  print('FAILS',fails); sys.exit(1 if fails else 0)
asyncio.run(main())
