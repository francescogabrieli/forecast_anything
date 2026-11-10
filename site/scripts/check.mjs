// Run against the built site with the console's installed Playwright.
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [playwrightPath, output, axePath] = process.argv.slice(2);
const { chromium } = await import(pathToFileURL(resolve(playwrightPath)));
const record = JSON.parse(await readFile(new URL('../demo-data.json', import.meta.url))).journey;
const base = process.env.SITE_URL ?? 'http://127.0.0.1:4176/';
const browser = await chromium.launch();

try {
  await mkdir(output, { recursive: true });
  for (const [width, height] of [[1440,900], [1024,768], [768,1024], [390,844], [320,700]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    assert.equal((await page.goto(base)).status(), 200);
    await page.evaluate(() => document.fonts.ready);
    assert.equal((await page.locator('h1').innerText()).replace(/\s+/g, ' '), 'Forecast with your assistant.');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
    const chart = page.locator('#demo svg[data-forecast-chart]:visible');
    assert.equal(await chart.count(), 1);
    assert.equal(await chart.locator('[data-series="timestral"]').count(), 1);
    assert.equal(await chart.locator('[data-series="seasonal"]').count(), 1);
    assert.equal(await chart.locator('[data-series="observed"] circle').count(), 8);
    const hero = page.locator('.hero');
    for (const point of [record.forecast.forecast[0], record.forecast.baseline_forecast[0]]) {
      assert.ok((await hero.locator('.preview-values').innerText()).includes(point.value.toFixed(3)));
    }
    const next = record.worker_update.change_summary.added_targets[0].timestamp.slice(0, 10);
    assert.equal(await hero.locator(`.figure-update time[datetime="${next}"]`).count(), 1);
    assert.equal((await hero.locator('.figure-status').innerText()).toLowerCase(), record.worker_update.quality);
    const image = await hero.locator('.warehouse-photo').evaluate(el => getComputedStyle(el).backgroundImage);
    const photoUrl = image.match(/url\("(.*?)"\)/)?.[1];
    assert.ok(photoUrl, 'warehouse photo URL');
    assert.equal((await page.request.get(photoUrl)).status(), 200);
    if (width === 1440) {
      for (const selector of ['#hero-cutoff', '.figure-forecast', '.hero-actions']) {
        const box = await page.locator(selector).boundingBox();
        assert.ok(box.y + box.height <= height, selector);
      }
    }
    if (width === 390 || width === 1440) {
      await page.screenshot({ animations: 'disabled', path: resolve(output, `first-${width}.png`) });
      await hero.screenshot({ animations: 'disabled', path: resolve(output, `hero-${width}.png`) });
      await page.screenshot({ animations: 'disabled', path: resolve(output, `full-${width}.png`), fullPage: true });
      if (axePath) {
        await page.addScriptTag({ path: axePath });
        const violations = await page.evaluate(async () => (await window.axe.run()).violations);
        assert.deepEqual(violations.map(({ id, nodes }) => ({ id, nodes: nodes.map(n => n.target) })), []);
      }
    }
    assert.deepEqual(errors, []);
    await page.close();
    console.log(`OK ${width}×${height}`);
  }

  const motionPage = await browser.newPage({ reducedMotion: 'no-preference' });
  await motionPage.goto(base);
  const hero = motionPage.locator('.chart-preview');
  await motionPage.waitForFunction(() =>
    document.querySelector('.chart-preview [data-reveal="history"]').getAnimations().length === 1
  );
  assert.equal(await hero.locator('.forecast-extension').count(), 2);

  const replay = motionPage.getByRole('button', { name: 'Replay forecast' });
  await replay.press('Enter');
  const chart = motionPage.locator('#demo svg[data-forecast-chart]:visible');
  const frames = await chart.evaluate(svg => {
    const history = svg.querySelector('[data-reveal="history"]');
    const forecast = svg.querySelector('[data-reveal="forecast"]');
    const animations = [history.getAnimations()[0], forecast.getAnimations()[0]];
    animations.forEach(animation => animation.pause());
    const widthsAt = time => {
      animations.forEach(animation => { animation.currentTime = time; });
      return [history, forecast].map(mask => parseFloat(getComputedStyle(mask).width));
    };
    return { history: widthsAt(310), forecast: widthsAt(780), end: widthsAt(1000) };
  });
  assert.ok(frames.history[0] > 0 && frames.history[0] < frames.end[0]);
  assert.equal(frames.history[1], 0);
  assert.equal(frames.forecast[0], frames.end[0]);
  assert.ok(frames.forecast[1] > 0 && frames.forecast[1] < frames.end[1]);
  await replay.press('Enter');
  const restarted = await chart.locator('[data-reveal="history"]').evaluate(mask =>
    mask.getAnimations().filter(animation => animation.playState === 'running').length
  );
  assert.equal(restarted, 1);
  await motionPage.emulateMedia({ reducedMotion: 'reduce' });
  await replay.waitFor({ state: 'hidden' });
  assert.equal(await motionPage.evaluate(() => document.getAnimations().length), 0);
  await motionPage.close();
  console.log('OK history reveal, forecast continuation, hero autoplay and reduced motion');

  const page = await browser.newPage({ javaScriptEnabled: false });
  const response = await page.goto(base);
  const html = await response.text();
  assert.match(html, /Forecast with your assistant/);
  assert.match(html, /--prepare-model/);
  assert.equal(await page.locator('.replay-button:visible').count(), 0);
  await page.keyboard.press('Tab');
  assert.equal(await page.locator(':focus').innerText(), 'Skip to content');
  assert.notEqual(await page.locator(':focus').evaluate(el => getComputedStyle(el).outlineStyle), 'none');
  await page.keyboard.press('Enter');
  assert.equal(new URL(page.url()).hash, '#main');
  const evidence = page.locator('#update details summary');
  await evidence.focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#update details').getAttribute('open'), '');
  const consolePreview = page.locator('.console-preview');
  const consoleImage = consolePreview.getByRole('img');
  assert.equal(await consoleImage.isVisible(), false);
  await consolePreview.locator('summary').focus();
  await page.keyboard.press('Enter');
  assert.equal(await consolePreview.getAttribute('open'), '');
  assert.equal(await consoleImage.isVisible(), true);
  const screenshot = await page.request.get(new URL(await consoleImage.getAttribute('src'), base).href);
  assert.equal(screenshot.status(), 200);
  assert.match(screenshot.headers()['content-type'], /^image\/webp/);
  for (const point of [record.forecast.forecast[0], record.forecast.baseline_forecast[0]]) {
    assert.ok((await page.locator('#demo').innerText()).includes(point.value.toFixed(3)));
  }
  for (const time of [record.forecast.as_of, record.forecast.forecast[0].time,
    record.worker_update.change_summary.added_targets[0].timestamp]) {
    assert.ok(await page.locator(`time[datetime="${time.slice(0,10)}"]`).count(), time);
  }
  const links = await page.locator('a[href]').evaluateAll(anchors => anchors.map(a => a.href));
  for (const href of new Set(links)) {
    const url = new URL(href);
    if (url.origin !== new URL(base).origin) continue;
    if (url.hash) assert.equal(await page.locator(url.hash).count(), 1, href);
    else assert.equal((await page.request.get(url.href)).status(), 200, href);
  }
  console.log('OK static HTML, recorded values/dates, keyboard, disclosure and local links');
} finally {
  await browser.close();
}
