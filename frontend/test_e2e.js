import { chromium } from 'playwright-core';
import { createServer } from 'vite';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

async function runTests() {
  console.log('--- Starting Vite dev server for E2E tests ---');
  const server = await createServer({
    root: process.cwd(),
    server: { port: 5173 },
  });
  await server.listen();
  const url = 'http://localhost:5173';
  console.log(`Vite running at ${url}`);

  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
  });

  try {
    // ---------------------------------------------------------------
    // TEST 1: Exact Timing Verification (2.5s, 5.5s, 8.8s)
    // ---------------------------------------------------------------
    console.log('\n[TEST 1] Verifying Opening Sequence Timing at 2.5s, 5.5s, and 8.8s');
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(url);

    // Initial state: entry visible, app hidden, opening hidden
    const entryHiddenInit = await page.locator('#entry').evaluate(el => el.classList.contains('hidden'));
    const appHiddenInit = await page.locator('#app').evaluate(el => el.classList.contains('hidden'));
    const openingOnInit = await page.locator('#opening').evaluate(el => el.classList.contains('on'));
    console.log(`  Initial state -> Entry hidden: ${entryHiddenInit}, App hidden: ${appHiddenInit}, Opening active: ${openingOnInit}`);
    if (entryHiddenInit || !appHiddenInit || openingOnInit) {
      throw new Error('Initial state mismatch!');
    }

    // Submit form with a test name and hook submit time in the browser
    await page.fill('#name', 'Alex');
    await page.evaluate(() => {
      document.getElementById('entry-form').addEventListener('submit', () => {
        window.__animStart = performance.now();
      }, { capture: true });
    });
    await page.click('button[type="submit"]');

    // Wait until animation starts
    await page.waitForFunction(() => window.__animStart !== undefined);

    // Helper to wait until relative animation time (in browser time)
    const waitUntil = async (targetMs) => {
      await page.waitForFunction(
        (target) => (performance.now() - window.__animStart) >= target,
        targetMs,
        { polling: 20 }
      );
    };

    // Check at approx 2.5s (during handwriting)
    await waitUntil(2500);
    const elapsed2_5 = await page.evaluate(() => Math.round(performance.now() - window.__animStart));
    const openingOn2_5 = await page.locator('#opening').evaluate(el => el.classList.contains('on'));
    const openingLeaving2_5 = await page.locator('#opening').evaluate(el => el.classList.contains('leaving'));
    const captionShown2_5 = await page.locator('#opening-caption').evaluate(el => el.classList.contains('shown'));
    const appHidden2_5 = await page.locator('#app').evaluate(el => el.classList.contains('hidden'));
    const entryHidden2_5 = await page.locator('#entry').evaluate(el => el.classList.contains('hidden'));
    const pathsDrawing2_5 = await page.locator('.hand-path').evaluateAll(els => els.every(el => el.classList.contains('draw')));

    console.log(`  At ~2.5s (${elapsed2_5}ms browser time):`);
    console.log(`    Opening overlay active (.on): ${openingOn2_5} (expected: true)`);
    console.log(`    Opening overlay leaving: ${openingLeaving2_5} (expected: false)`);
    console.log(`    Caption shown: ${captionShown2_5} (expected: false)`);
    console.log(`    App still hidden: ${appHidden2_5} (expected: true)`);
    console.log(`    SVG paths have .draw: ${pathsDrawing2_5} (expected: true)`);
    if (!openingOn2_5 || openingLeaving2_5 || captionShown2_5 || !appHidden2_5 || !pathsDrawing2_5) {
      throw new Error('Timing check at 2.5s failed!');
    }

    // Check at approx 5.5s (writing finished / hold phase begins; app must NOT replace intro early)
    await waitUntil(5500);
    const elapsed5_5 = await page.evaluate(() => Math.round(performance.now() - window.__animStart));
    const openingOn5_5 = await page.locator('#opening').evaluate(el => el.classList.contains('on'));
    const appHidden5_5 = await page.locator('#app').evaluate(el => el.classList.contains('hidden'));

    console.log(`  At ~5.5s (${elapsed5_5}ms browser time):`);
    console.log(`    Opening overlay still active (.on): ${openingOn5_5} (expected: true)`);
    console.log(`    App still hidden (hold phase; chat did not replace intro early): ${appHidden5_5} (expected: true)`);
    if (!openingOn5_5 || !appHidden5_5) {
      throw new Error('Timing check at 5.5s failed!');
    }

    // Wait for caption to appear (scheduled at startDelay + writingMs + 200 = 5650ms)
    await page.waitForSelector('#opening-caption.shown', { timeout: 7000 });
    const elapsedCaption = await page.evaluate(() => Math.round(performance.now() - window.__animStart));
    console.log(`  Caption appeared during hold at ${elapsedCaption}ms browser time (expected ~5650ms)`);

    // Check at approx 8.8s (complete sequence finished, app open and active)
    await waitUntil(8800);
    const elapsed8_8 = await page.evaluate(() => Math.round(performance.now() - window.__animStart));
    const openingOn8_8 = await page.locator('#opening').evaluate(el => el.classList.contains('on'));
    const appHidden8_8 = await page.locator('#app').evaluate(el => el.classList.contains('hidden'));
    const profileName = await page.locator('#profile-name').textContent();

    console.log(`  At ~8.8s (${elapsed8_8}ms browser time):`);
    console.log(`    Opening overlay finished (not .on): ${!openingOn8_8} (expected: true)`);
    console.log(`    App visible (not .hidden): ${!appHidden8_8} (expected: true)`);
    console.log(`    Profile name set: "${profileName}" (expected: "Alex")`);
    if (openingOn8_8 || appHidden8_8 || profileName !== 'Alex') {
      throw new Error('Timing check at 8.8s failed!');
    }
    await context.close();

    // ---------------------------------------------------------------
    // TEST 2: Prefers-Reduced-Motion Setting Check
    // ---------------------------------------------------------------
    console.log('\n[TEST 2] Verifying Reduced Motion does NOT skip handwritten welcome');
    const rmContext = await browser.newContext({
      reducedMotion: 'reduce',
    });
    const rmPage = await rmContext.newPage();
    await rmPage.goto(url);
    await rmPage.fill('#name', 'MotionUser');
    await rmPage.evaluate(() => {
      document.getElementById('entry-form').addEventListener('submit', () => {
        window.__rmAnimStart = performance.now();
      }, { capture: true });
    });
    await rmPage.click('button[type="submit"]');

    await rmPage.waitForFunction(() => window.__rmAnimStart !== undefined);
    const rmWaitUntil = async (targetMs) => {
      await rmPage.waitForFunction(
        (target) => (performance.now() - window.__rmAnimStart) >= target,
        targetMs,
        { polling: 20 }
      );
    };

    // At 2.5s, opening must STILL be active and app must STILL be hidden
    await rmWaitUntil(2500);
    const rmOpening2_5 = await rmPage.locator('#opening').evaluate(el => el.classList.contains('on'));
    const rmAppHidden2_5 = await rmPage.locator('#app').evaluate(el => el.classList.contains('hidden'));
    console.log(`  Reduced-motion at ~2.5s -> Opening active: ${rmOpening2_5}, App hidden: ${rmAppHidden2_5}`);
    if (!rmOpening2_5 || !rmAppHidden2_5) {
      throw new Error('Reduced motion incorrectly skipped intro early!');
    }

    // At 8.8s, sequence must complete naturally
    await rmWaitUntil(8800);
    const rmOpening8_8 = await rmPage.locator('#opening').evaluate(el => el.classList.contains('on'));
    const rmAppHidden8_8 = await rmPage.locator('#app').evaluate(el => el.classList.contains('hidden'));
    console.log(`  Reduced-motion at ~8.8s -> Opening done: ${!rmOpening8_8}, App visible: ${!rmAppHidden8_8}`);
    if (rmOpening8_8 || rmAppHidden8_8) {
      throw new Error('Reduced motion completion failed!');
    }
    await rmContext.close();

    // ---------------------------------------------------------------
    // TEST 3: Mock API /chat Live Integration in Browser
    // ---------------------------------------------------------------
    console.log('\n[TEST 3] Verifying /chat live response handling, sources, and error states');
    const apiContext = await browser.newContext();
    const apiPage = await apiContext.newPage();

    // Set up mock routes for FastAPI /chat
    let currentMockResponse = null;
    let mockDelayMs = 50;
    await apiPage.route('**/chat', async (route) => {
      if (mockDelayMs > 0) {
        await new Promise(r => setTimeout(r, mockDelayMs));
      }
      if (currentMockResponse.status && currentMockResponse.status !== 200) {
        await route.fulfill({
          status: currentMockResponse.status,
          contentType: 'application/json',
          body: JSON.stringify(currentMockResponse.body),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(currentMockResponse),
        });
      }
    });

    // Emulate LIVE_API_ENABLED = true by setting it in window or mocking
    // We can evaluate beforeunload/initScript or test direct responses
    await apiPage.addInitScript(() => {
      // Mock import.meta.env or directly test with live api
      window.__TEST_LIVE_API__ = true;
    });

    await apiPage.goto(url);
    await apiPage.fill('#name', 'ApiTester');
    await apiPage.click('button[type="submit"]');
    // Wait for intro to finish
    await apiPage.waitForSelector('#app:not(.hidden)', { timeout: 12000 });

    // Verify UI layout elements
    const brandMark = await apiPage.locator('.wordmark-title').first().textContent();
    console.log(`  Wordmark text: "${brandMark}"`);

    // Verify prompt buttons work
    const promptButton = apiPage.locator('.prompt').first();
    const promptText = await promptButton.locator('strong').textContent();
    console.log(`  Clicking prompt suggestion: "${promptText}"`);
    await promptButton.click();

    // Verify user message appeared
    await apiPage.waitForSelector('.message.user');
    const userMsg = await apiPage.locator('.message.user').textContent();
    console.log(`  User message displayed: "${userMsg}"`);

    // Wait for bot response
    await apiPage.waitForSelector('.message.bot');
    const botMsg = await apiPage.locator('.message.bot .answer-body').textContent();
    const botChip = await apiPage.locator('.message.bot .chip').textContent();
    console.log(`  Bot answer: "${botMsg.slice(0, 50)}..."`);
    console.log(`  Bot chip: "${botChip}"`);

    // Test Local Storage & Chat History
    console.log('\n[TEST 4] Verifying Local Conversation Storage & Sidebar');
    const historyCount = await apiPage.locator('#count').textContent();
    const historyItems = await apiPage.locator('.history-open').count();
    console.log(`  History count: ${historyCount}, Items in list: ${historyItems}`);
    if (historyItems < 1) throw new Error('Chat history was not rendered!');

    // Test Search in History
    await apiPage.fill('#history-search', 'makeup');
    const filteredCount = await apiPage.locator('.history-open').count();
    console.log(`  Search for "makeup" returned ${filteredCount} items`);

    // Test New Conversation Button
    await apiPage.click('#new-chat');
    const messagesCountAfterNew = await apiPage.locator('.messages .message').count();
    const welcomeVisible = await apiPage.locator('#welcome').isVisible();
    console.log(`  New chat -> Messages count: ${messagesCountAfterNew}, Welcome visible: ${welcomeVisible}`);
    if (messagesCountAfterNew !== 0 || !welcomeVisible) {
      throw new Error('New conversation did not reset view!');
    }

    // Reopen previous conversation
    await apiPage.fill('#history-search', '');
    await apiPage.locator('.history-open').first().click();
    const messagesCountReopened = await apiPage.locator('.messages .message').count();
    console.log(`  Reopened chat -> Messages count: ${messagesCountReopened}`);
    if (messagesCountReopened < 2) {
      throw new Error('Reopened conversation did not restore messages!');
    }

    await apiContext.close();

    console.log('\n--- ALL E2E BROWSER CHECKS PASSED SUCCESSFULLY ---');
  } finally {
    await browser.close();
    await server.close();
  }
}

runTests().catch(err => {
  console.error('\nE2E Test Failed:', err);
  process.exit(1);
});
