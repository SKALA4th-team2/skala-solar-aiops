"""Browser regression for CSV selection/drop; upload requests are intercepted."""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=b.new_page(viewport={'width':390,'height':844})
 page.goto('http://127.0.0.1:8767/index.html#service')
 page.locator('#upload-button').click()
 page.locator('#upload-file').set_input_files({'name':'test.csv','mimeType':'text/csv','buffer':b'timestamp,generation_kwh\n'})
 assert page.locator('#upload-filename').inner_text()=='test.csv'
 assert page.locator('#upload-submit').is_enabled()
 page.locator('#upload-remove').click()
 assert page.locator('#upload-submit').is_disabled()
 def drop(name):
  page.locator('#upload-dropzone').evaluate('''(e,name)=>{const d=new DataTransfer();d.items.add(new File(['test'],name,{type:'text/csv'}));e.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:d}));}''',name)
 drop('bad.txt');assert page.locator('#upload-submit').is_disabled()
 drop('dropped.csv');assert page.locator('#upload-filename').inner_text()=='dropped.csv'
 requests=[]
 page.route('**/data/upload',lambda route:requests.append(route))
 page.locator('#upload-submit').click();page.wait_for_timeout(150)
 assert len(requests)==1 and 'dropped.csv' in requests[0].request.post_data
 assert page.locator('#upload-pick').is_disabled()
 page.keyboard.press('Escape');assert page.locator('#upload-dialog').is_visible()
 requests[0].fulfill(status=422,json={'detail':'CSV 검증 실패'})
 page.wait_for_function('!document.querySelector("#upload-pick").disabled')
 assert 'CSV 검증 실패' in page.locator('#upload-status').inner_text()
 assert page.locator('#upload-dialog').evaluate('e=>e.scrollWidth<=e.clientWidth')
 print('PASS: selection, removal, invalid extension, drop, intercepted upload, pending guard, error recovery, mobile width')
 b.close()
