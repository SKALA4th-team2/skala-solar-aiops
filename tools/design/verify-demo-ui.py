"""Solar demo UI regression. Requires Playwright and Chrome; all batch writes are intercepted.
Run from project/: python ../tools/design/verify-demo-ui.py [http://127.0.0.1:8767]
Read-only energy/health APIs must be available. Does not trigger training or promotion.
"""
import copy
import os
import sys
from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8767'
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=os.getenv('CHROME_PATH', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        headless=True,
    )
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base + '/index.html#energy')
    page.wait_for_selector('.chart-y-tick')
    page.evaluate('document.fonts.ready')
    page.locator('[data-view="service"]').click()
    page.wait_for_timeout(200)
    with page.expect_response(lambda response: '/ui/energy?' in response.url):
        page.locator('#plant-filter').select_option(index=1)
    page.wait_for_timeout(200)
    page.locator('[data-view="energy"]').click()
    page.wait_for_function("document.querySelector('#overview-chart svg')?.viewBox.baseVal.width === document.querySelector('#overview-chart').clientWidth")
    print('PASS: hidden-view plant change restores full chart width')
    for width in [1440, 1280, 1024, 768, 390, 320]:
        page.set_viewport_size({'width': width, 'height': 900})
        for period in [24, 72, 168]:
            page.locator(f'[data-period="{period}"]').click()
            page.eval_on_selector('#daily-records', 'e=>e.open=false')
            before = [button.bounding_box() for button in page.locator('[data-period]').all()]
            for opened in [True, False, True]:
                page.eval_on_selector('#daily-records', '(e,opened)=>e.open=opened', opened)
                assert before == [button.bounding_box() for button in page.locator('[data-period]').all()], (width, period)
            assert page.locator('#forecast-hours tr').count() == 24
        assert page.locator('.incentive-panel').evaluate('e=>e.parentElement.id') == 'view-energy'
        assert page.locator('#main').evaluate('e=>e.scrollWidth<=e.clientWidth')
    print('PASS: all 3 period buttons fixed across 6 widths and repeated disclosure toggles')
    axes = []
    for period in [24, 72, 168]:
        page.locator(f'[data-period="{period}"]').click()
        axes.append(page.locator('.chart-y-tick').all_text_contents())
    assert axes[0] == axes[1] == axes[2]
    chart = page.locator('#overview-chart svg')
    chart.focus()
    chart.press('Home')
    first_time = page.locator('.chart-readout time').inner_text()
    chart.press('End')
    assert first_time != page.locator('.chart-readout time').inner_text()
    assert page.locator('.chart-y-tick').evaluate_all('es=>es.every(e=>e.getBBox().x>=0)')
    print('PASS: shared Y scale, keyboard time selection, unclipped axis labels')

    page.set_viewport_size({'width': 1440, 'height': 900})
    snapshot = page.request.get(base + '/preview-api/operations?plant_id=hadong-sewage').json()
    snapshot['plant']['monitor'] = None
    page.route('**/preview-api/operations?*', lambda route: route.fulfill(json=snapshot))
    page.locator('[data-view="service"]').click()
    page.wait_for_selector('.model-summary dl')
    pending = []
    page.route('**/predict/batch-test', lambda route: pending.append(route))
    page.locator('#simulation-button').click()
    page.locator('#normal-batch').click()
    page.wait_for_function('document.querySelector("[data-inspection=check]").dataset.state==="pending"')
    page.wait_for_timeout(200)
    assert len(pending) == 1
    assert len(pending[0].request.post_data_json['rows']) == 696
    assert page.locator('#simulation-close').is_disabled()
    page.keyboard.press('Escape')
    assert page.locator('#simulation-dialog').is_visible()
    monitor = {'state': 'normal', 'reason': 'normal', 'rmse_kwh': 1.2, 'end_timestamp': '2026-02-27T23:00:00+09:00'}
    pending.pop().fulfill(json={'predictions': [1] * 24, 'monitor': monitor})
    page.wait_for_function('!document.querySelector("#normal-batch").disabled')
    assert '정상 유지' in page.locator('#simulation-status').inner_text()
    assert page.locator('.inspection-progress [data-state="complete"]').count() == 3
    page.locator('#normal-batch').click()
    page.wait_for_timeout(400)
    pending.pop().fulfill(status=422, json={'detail': '검증용 입력 오류'})
    page.wait_for_function('!document.querySelector("#normal-batch").disabled')
    assert '검증용 입력 오류' in page.locator('#simulation-status').inner_text()
    assert page.locator('#simulation-count').inner_text() == '—'
    assert page.locator('[data-inspection="check"]').get_attribute('data-state') == 'attention'
    page.locator('#simulation-close').click()
    print('PASS: intercepted batch payload, pending/Escape guard, success/error, stale metric reset')
    for status, expected in [('queued', '학습 대기'), ('running', '학습 중'), ('succeeded', '반영 완료'), ('rejected', '반영 보류'), ('failed', '작업 실패')]:
        report = copy.deepcopy(monitor)
        report.update(state='queued', reason='forecast_conditioned_drop_and_error', job={'id': 'ui-test', 'status': 'queued'})
        snapshot['plant']['monitor'] = report
        snapshot['plant']['jobs'] = [{'id': 'ui-test', 'status': status, 'result': {'reason': 'training_period_overlap'} if status == 'rejected' else None}]
        page.locator('#refresh-ops').click()
        page.wait_for_function('(expected)=>document.querySelector("#pipeline-status").textContent.includes(expected)', arg=expected)
    for status, expected in [('normal', '정상 유지'), ('held', '확인 필요'), ('skipped', '자료 부족')]:
        snapshot['plant']['monitor'] = {**monitor, 'state': status}
        snapshot['plant']['jobs'] = []
        page.locator('#refresh-ops').click()
        page.wait_for_function('(expected)=>document.querySelector("#pipeline-status").textContent.includes(expected)', arg=expected)
    snapshot['plant']['monitor'] = {**monitor, 'state': 'succeeded', 'reason': 'existing_job_terminal', 'job': {'id': 'ui-test', 'status': 'succeeded'}}
    snapshot['plant']['jobs'] = [{'id': 'ui-test', 'status': 'succeeded'}]
    page.locator('#refresh-ops').click()
    page.wait_for_function('document.querySelector(".pipeline li:last-child .step-state").textContent.includes("이전 반영")')
    assert page.locator('#pipeline-summary').count() == 0
    for width in [1440, 768, 390, 320]:
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.locator('#main').evaluate('e=>e.scrollWidth<=e.clientWidth'), width
        page.locator('#simulation-button').click()
        assert page.locator('#simulation-dialog').evaluate('e=>e.scrollWidth<=e.clientWidth'), width
        page.keyboard.press('Escape')
    page.set_viewport_size({'width': 1440, 'height': 900})
    current = {'version': '2'}
    history = [{'version': '1', 'created_at': '2026-10-08T00:00:00Z', 'gate': {'passed': True, 'rmse_kwh': 4.45}}, {'version': '2', 'created_at': '2026-10-08T01:00:00Z', 'parent_version': '1', 'gate': {'passed': True, 'rmse_kwh': 3.41}}]
    page.route('**/preview-api/dashboard/current?*', lambda route: route.fulfill(json=current))
    page.route('**/preview-api/dashboard/history?*', lambda route: route.fulfill(json=history))
    switches = []
    page.route('**/plants/*/rollback', lambda route: switches.append(route))
    page.locator('[data-view="history"]').click()
    page.wait_for_selector('button[data-version="1"]')
    page.locator('button[data-version="1"]').click()
    page.wait_for_timeout(150)
    assert switches[0].request.post_data_json == {'version': 1}
    assert page.locator('#plant-filter').is_disabled()
    current['version'] = '1'
    switches.pop().fulfill(json={'version': '1'})
    page.wait_for_function('document.querySelector("#history-status").textContent.includes("v1 운영 적용 완료")')
    assert page.locator('button[data-version="1"]').count() == 0
    page.locator('button[data-version="2"]').click()
    page.wait_for_timeout(150)
    switches.pop().fulfill(status=409, json={'detail': '검증용 반영 거부'})
    page.wait_for_function('document.querySelector("#history-status").textContent.includes("검증용 반영 거부")')
    assert not page.locator('#plant-filter').is_disabled()
    print('PASS: intercepted model switch, current version, failure recovery; no real promotion')
    assert not errors, errors
    print('PASS: 9 monitor/job outcomes, narrow screens, keyboard close, no JS errors')
    browser.close()
