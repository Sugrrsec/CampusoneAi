import { chromium } from 'playwright-core';
import { createServer } from 'vite';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

async function runLiveApiTests() {
  console.log('--- Starting Vite with LIVE_API_ENABLED=true for Live Contract Tests ---');
  // Pass env so import.meta.env.VITE_USE_LIVE_API === 'true'
  process.env.VITE_USE_LIVE_API = 'true';
  process.env.VITE_API_BASE_URL = 'http://127.0.0.1:8000';

  const server = await createServer({
    root: process.cwd(),
    server: { port: 5174 },
  });
  await server.listen();
  const url = 'http://localhost:5174';
  console.log(`Vite running at ${url}`);

  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
  });

  try {
    const context = await browser.newContext();
    const page = await context.newPage();

    let currentResponse = null;
    let requestDelay = 0;
    let lastReceivedPayload = null;

    await page.route('http://127.0.0.1:8000/chat', async (route) => {
      lastReceivedPayload = JSON.parse(route.request().postData());
      if (requestDelay > 0) {
        await new Promise(r => setTimeout(r, requestDelay));
      }
      if (currentResponse.status && currentResponse.status !== 200) {
        await route.fulfill({
          status: currentResponse.status,
          contentType: 'application/json',
          body: JSON.stringify(currentResponse.body || { detail: 'Server Error' }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(currentResponse),
        });
      }
    });

    await page.goto(url);
    await page.fill('#name', 'LiveTester');
    await page.click('button[type="submit"]');

    // Wait until app is visible
    await page.waitForSelector('#app:not(.hidden)', { timeout: 12000 });

    // Verify header mode pill displays Live API
    const modePillText = await page.locator('.topmeta span:last-child').textContent();
    console.log(`  Top bar mode pill: "${modePillText}" (expected: "● Live API")`);
    if (!modePillText.includes('Live API')) {
      throw new Error(`Mode pill mismatch: ${modePillText}`);
    }

    // -------------------------------------------------------------
    // SCENARIO 1: Standard Answer with Sources & Citations
    // -------------------------------------------------------------
    console.log('\n[SCENARIO 1] Standard Answer with Citations & External Links');
    currentResponse = {
      answer: 'Semester exams for B.Tech are conducted twice an academic year: Fall (Odd) and Spring (Even) semesters.',
      domains: ['HR_ADMIN'],
      confidence: 0.95,
      needs_clarification: false,
      clarification_question: null,
      is_out_of_scope: false,
      sources: [
        {
          chunk_id: 'scset_ug_0002',
          domain: 'HR_ADMIN',
          source_title: 'Academic Rules for SCSET UG',
          page: 1,
          score: 0.7076,
          source_url: 'https://www.bennett.edu.in/wp-content/uploads/2022/03/Academic-Rules-for-SCSET_UG.pdf',
        },
        {
          chunk_id: 'scset_ug_0001',
          domain: 'HR_ADMIN',
          source_title: 'SCSET Ordinance',
          page: null,
          score: 0.65,
          source_url: null,
        }
      ],
      session_id: 'test-session-1',
      metadata: { status: 'answered', routing_method: 'keyword_fallback' },
    };

    await page.fill('#message-input', 'What semester system is used?');
    await page.press('#message-input', 'Enter');

    await page.waitForSelector('.message.bot');
    const answer1 = await page.locator('.message.bot:last-child .answer-body').textContent();
    const chip1 = await page.locator('.message.bot:last-child .chip').first().textContent();
    const sourceLink = await page.locator('.message.bot:last-child .source-link').textContent();
    const sourceHref = await page.locator('.message.bot:last-child .source-link').getAttribute('href');
    const sourceChip = await page.locator('.message.bot:last-child .answer-detail .chip').nth(1).textContent();

    console.log(`  Sent payload: ${JSON.stringify(lastReceivedPayload)}`);
    console.log(`  Answer rendered: "${answer1.slice(0, 60)}..."`);
    console.log(`  Domain chip: "${chip1}" (expected: "HR_ADMIN")`);
    console.log(`  Source link: "${sourceLink}" -> href: "${sourceHref}"`);
    console.log(`  Source non-link chip: "${sourceChip}"`);

    if (chip1 !== 'HR_ADMIN' || !sourceHref.startsWith('https://www.bennett.edu.in') || !sourceChip.includes('SCSET Ordinance')) {
      throw new Error('Scenario 1 source rendering failed!');
    }

    // -------------------------------------------------------------
    // SCENARIO 2: Out of Scope Response
    // -------------------------------------------------------------
    console.log('\n[SCENARIO 2] Out of Scope Response');
    currentResponse = {
      answer: 'I can only help with IT support, HR and administrative queries, university fees, and campus facilities. Please ask a question related to these university domains.',
      domains: [],
      confidence: 0.0,
      needs_clarification: false,
      clarification_question: null,
      is_out_of_scope: true,
      sources: [],
      session_id: 'test-session-1',
      metadata: { status: 'out_of_scope' },
    };

    await page.fill('#message-input', 'Write a quicksort in C++');
    await page.press('#message-input', 'Enter');

    await page.waitForTimeout(300);
    const chip2 = await page.locator('.message.bot:last-child .chip').first().textContent();
    const statusText2 = await page.locator('.message.bot:last-child small').textContent();
    console.log(`  Out of scope chip: "${chip2}" (expected: "Out of scope")`);
    console.log(`  Out of scope status detail: "${statusText2}" (expected: "Out of scope query")`);
    if (chip2 !== 'Out of scope' || statusText2 !== 'Out of scope query') {
      throw new Error('Scenario 2 out-of-scope failed!');
    }

    // -------------------------------------------------------------
    // SCENARIO 3: Clarification Needed
    // -------------------------------------------------------------
    console.log('\n[SCENARIO 3] Clarification Needed Response');
    currentResponse = {
      answer: 'Could you please specify whether you need help with hostel fee payment or tuition fee refund?',
      domains: ['FEES'],
      confidence: 0.6,
      needs_clarification: true,
      clarification_question: 'Could you please specify...',
      is_out_of_scope: false,
      sources: [],
      session_id: 'test-session-1',
      metadata: { status: 'needs_clarification' },
    };

    await page.fill('#message-input', 'fee query');
    await page.press('#message-input', 'Enter');

    await page.waitForTimeout(300);
    const chip3 = await page.locator('.message.bot:last-child .chip').first().textContent();
    const statusText3 = await page.locator('.message.bot:last-child small').textContent();
    console.log(`  Clarification chip: "${chip3}" (expected: "FEES")`);
    console.log(`  Clarification detail: "${statusText3}" (expected: "Clarification requested")`);
    if (chip3 !== 'FEES' || statusText3 !== 'Clarification requested') {
      throw new Error('Scenario 3 clarification failed!');
    }

    // -------------------------------------------------------------
    // SCENARIO 4: Provider Rate Limited (Groq)
    // -------------------------------------------------------------
    console.log('\n[SCENARIO 4] Provider Rate Limited Response');
    currentResponse = {
      answer: 'The AI service is temporarily busy. Please try again shortly.',
      domains: [],
      confidence: 0.0,
      needs_clarification: false,
      clarification_question: null,
      is_out_of_scope: false,
      sources: [],
      session_id: 'test-session-1',
      metadata: { status: 'provider_rate_limited', provider: 'groq' },
    };

    await page.fill('#message-input', 'Tell me about hostel wifi');
    await page.press('#message-input', 'Enter');

    await page.waitForTimeout(300);
    const chip4 = await page.locator('.message.bot:last-child .chip').first().textContent();
    const statusText4 = await page.locator('.message.bot:last-child small').textContent();
    console.log(`  Rate limit chip: "${chip4}" (expected: "Rate limit")`);
    console.log(`  Rate limit detail: "${statusText4}" (expected: "AI service temporarily busy")`);
    if (chip4 !== 'Rate limit' || statusText4 !== 'AI service temporarily busy') {
      throw new Error('Scenario 4 rate-limited failed!');
    }

    // -------------------------------------------------------------
    // SCENARIO 5: Server / Network Connection Error (No fallback to demo)
    // -------------------------------------------------------------
    console.log('\n[SCENARIO 5] Server Error Handling (No Demo Fallback)');
    currentResponse = {
      status: 500,
      body: { detail: 'CampusOne AI backend connection failed: GROQ_API_KEY missing' },
    };

    await page.fill('#message-input', 'Are libraries open on Sunday?');
    await page.press('#message-input', 'Enter');

    await page.waitForTimeout(300);
    const errorBotAnswer = await page.locator('.message.bot:last-child .answer-body').textContent();
    const errorChip = await page.locator('.message.bot:last-child .chip').first().textContent();
    const errorStatus = await page.locator('.message.bot:last-child small').textContent();

    console.log(`  Error answer: "${errorBotAnswer}"`);
    console.log(`  Error chip: "${errorChip}" (expected: "Error")`);
    console.log(`  Error status: "${errorStatus}" (expected: "Connection error")`);

    if (errorChip !== 'Error' || !errorBotAnswer.includes('GROQ_API_KEY missing')) {
      throw new Error('Scenario 5 error handling failed!');
    }

    // -------------------------------------------------------------
    // SCENARIO 6: Switching Chats Mid-flight (No Leakage)
    // -------------------------------------------------------------
    console.log('\n[SCENARIO 6] Mid-flight Chat Switch Leak Prevention');
    // Set a 1000ms delay on API response
    requestDelay = 1000;
    currentResponse = {
      answer: 'This answer belongs to chat 1 only!',
      domains: ['IT'],
      confidence: 0.9,
      needs_clarification: false,
      clarification_question: null,
      is_out_of_scope: false,
      sources: [],
      session_id: 'chat-1',
      metadata: { status: 'answered' },
    };

    // Send question in chat 1
    await page.fill('#message-input', 'Inflight question in Chat 1');
    await page.press('#message-input', 'Enter');

    // Immediately start a new chat
    await page.click('#new-chat');
    console.log('  Switched to new chat while request was in-flight');

    // Wait for the in-flight request to resolve
    await page.waitForTimeout(1500);

    // Verify new chat remains empty and did NOT receive Chat 1 response
    const newChatMessages = await page.locator('.messages .message').count();
    console.log(`  New chat message count after delay: ${newChatMessages} (expected: 0)`);
    if (newChatMessages !== 0) {
      throw new Error('Response leaked to the wrong active chat!');
    }

    // Reopen Chat 1 from history
    await page.locator('.history-open').first().click();
    const chat1Messages = await page.locator('.messages .message').count();
    console.log(`  Reopened Chat 1 message count: ${chat1Messages} (expected: >= 2)`);
    if (chat1Messages < 2) {
      throw new Error('Chat 1 did not retain its history!');
    }

    await context.close();
    console.log('\n--- ALL LIVE API CONTRACT & ROBUSTNESS TESTS PASSED ---');
  } finally {
    await browser.close();
    await server.close();
  }
}

runLiveApiTests().catch(err => {
  console.error('\nLive API Test Failed:', err);
  process.exit(1);
});
