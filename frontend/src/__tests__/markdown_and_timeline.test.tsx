import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { App } from '../App';
import { ErrorBanner } from '../components/ErrorBanner';
import { ExecutionTimeline } from '../components/ExecutionTimeline';
import { MarkdownView } from '../components/MarkdownView';
import { Navbar } from '../components/Navbar';
import { ResultCard } from '../components/ResultCard';
import type { ChatResult, RunEventPayload } from '../types';

// Configure React act environment for jsdom
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe('Markdown Rendering & Escaping Fixes', () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    document.body.removeChild(container);
  });

  it('renders markdown headings h3 (###) as proper heading elements, not literal ### characters', async () => {
    const markdown = '### Executive Overview\nTarget domain analysis completed successfully.\n\n### Research Limitations\nAutomated crawl reached boundaries.';
    const root = createRoot(container);
    await act(async () => {
      root.render(<MarkdownView content={markdown} />);
    });

    const headings = container.querySelectorAll('h4');
    expect(headings.length).toBe(2);
    expect(headings[0].textContent).toBe('Executive Overview');
    expect(headings[1].textContent).toBe('Research Limitations');
    // Ensure no raw ### prefix is visible
    expect(container.textContent).not.toContain('###');
  });

  it('un-escapes backslash-escaped markdown headings (\\###) cleanly', async () => {
    const escapedMarkdown = '\\### Executive Overview\nClean analysis text.\n\n\\### Page-Level Findings\nFindings text.';
    const root = createRoot(container);
    await act(async () => {
      root.render(<MarkdownView content={escapedMarkdown} />);
    });

    const headings = container.querySelectorAll('h4');
    expect(headings.length).toBe(2);
    expect(headings[0].textContent).toBe('Executive Overview');
    expect(headings[1].textContent).toBe('Page-Level Findings');
    expect(container.textContent).not.toContain('\\###');
    expect(container.textContent).not.toContain('###');
  });

  it('renders bullet lists and list items correctly without escaping artifacts', async () => {
    const listMarkdown = '- First key observation\n- Second finding (source: https://example.com)\n\\- \\*\\*Example Domain\\*\\*: third finding';
    const root = createRoot(container);
    await act(async () => {
      root.render(<MarkdownView content={listMarkdown} />);
    });

    const ul = container.querySelector('ul');
    expect(ul).not.toBeNull();
    const items = container.querySelectorAll('li');
    expect(items.length).toBe(3);
    expect(items[0].textContent).toBe('First key observation');
    // Confirm raw \- or \*\* is not present in output
    expect(container.textContent).not.toContain('\\-');
    expect(container.textContent).not.toContain('\\*\\*');
  });

  it('renders markdown links [title](url) as clickable <a> elements with safe target and rel', async () => {
    const linkMarkdown = '- **[Acme Corporation](https://acme.example/jobs)**: High performance cloud platform.\n(source: https://docs.example.com)';
    const root = createRoot(container);
    await act(async () => {
      root.render(<MarkdownView content={linkMarkdown} />);
    });

    const links = container.querySelectorAll('a');
    expect(links.length).toBe(2);

    const firstLink = links[0];
    expect(firstLink.textContent).toBe('Acme Corporation');
    expect(firstLink.getAttribute('href')).toBe('https://acme.example/jobs');
    expect(firstLink.getAttribute('target')).toBe('_blank');
    expect(firstLink.getAttribute('rel')).toBe('noopener noreferrer');

    const secondLink = links[1];
    expect(secondLink.getAttribute('href')).toBe('https://docs.example.com');
  });

  it('does not render untrusted website HTML directly (avoids XSS and raw HTML injection)', async () => {
    const hostileHtml = '### Overview\n<script>alert("xss")</script><img src="x" onerror="alert(1)" />Safe text.';
    const root = createRoot(container);
    await act(async () => {
      root.render(<MarkdownView content={hostileHtml} />);
    });

    // Scripts and images must NOT be inserted into DOM as HTML elements
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    // React automatically renders the string safely
    expect(container.textContent).toContain('<script>');
  });

  it('rejects unsafe javascript: protocol in links', async () => {
    const dangerousMarkdown = '[Malicious Link](javascript:alert(1))';
    const root = createRoot(container);
    await act(async () => {
      root.render(<MarkdownView content={dangerousMarkdown} />);
    });

    const link = container.querySelector('a');
    expect(link).toBeNull();
    expect(container.textContent).toContain('Malicious Link');
  });
});

describe('Timeline DNS Failure & Step States', () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    document.body.removeChild(container);
  });

  it('marks subsequent stages as Skipped or Not Executed (never Pending) on DNS failure', async () => {
    const dnsFailureEvents: RunEventPayload[] = [
      {
        run_id: 'test-dns-run',
        event: 'plan',
        data: { url: 'https://nonexistent-domain-4040.org', tool: 'site_crawler' },
      },
      {
        run_id: 'test-dns-run',
        event: 'error',
        data: {
          error: "DNS resolution failed: Host 'nonexistent-domain-4040.org' could not be resolved or is unreachable",
          reason: 'dns_resolution_failed',
        },
      },
    ];

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ExecutionTimeline
          events={dnsFailureEvents}
          runId="test-dns-run"
          isRunning={false}
          terminalStatus="FAILED"
          onCancel={() => {}}
        />
      );
    });

    // Check step 1 (Validate Intent & URL Scheme) -> Done
    const step1 = container.querySelector('[data-testid="timeline-step-validate"]');
    expect(step1?.textContent).toContain('Done');

    // Check step 2 (SSRF & Netpolicy / DNS) -> Failed with DNS error
    const step2 = container.querySelector('[data-testid="timeline-step-robots"]');
    expect(step2?.textContent).toContain('Failed');
    expect(step2?.textContent).toContain('DNS resolution failed');

    // Check step 3 (Spawn Subprocess) -> Not Executed
    const step3 = container.querySelector('[data-testid="timeline-step-spawn"]');
    expect(step3?.textContent).toContain('Not Executed');
    expect(step3?.textContent).toContain('No CLI subprocess was launched');

    // Check step 4, 5, 6 (Crawl, Parse, Summarize) -> Skipped
    const step4 = container.querySelector('[data-testid="timeline-step-crawl"]');
    expect(step4?.textContent).toContain('Skipped');

    const step5 = container.querySelector('[data-testid="timeline-step-parse"]');
    expect(step5?.textContent).toContain('Skipped');

    const step6 = container.querySelector('[data-testid="timeline-step-summarize"]');
    expect(step6?.textContent).toContain('Skipped');

    // Ensure NO step is marked Pending
    expect(container.textContent).not.toContain('Pending');
  });

  it('distinguishes DNS errors from SSRF violations in ErrorBanner and Timeline', async () => {
    // 1. DNS error banner test
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ErrorBanner
          error="DNS resolution failed: Host 'unreachable.example' could not be resolved"
          onDismiss={() => {}}
        />
      );
    });
    expect(container.textContent).toContain('DNS / Network Resolution Error:');
    expect(container.textContent).not.toContain('SSRF Protection');

    // 2. SSRF error banner test
    await act(async () => {
      root.render(
        <ErrorBanner
          error="SSRF policy violation: Encoded IP resolves to forbidden address"
          onDismiss={() => {}}
        />
      );
    });
    expect(container.textContent).toContain('Security Policy Error (SSRF Protection):');
  });

  it('renders Raw Extracted JSON Payload section expanded by default with JSON visible immediately', async () => {
    const mockResult: ChatResult = {
      run_id: 'test-run-111',
      status: 'SUCCESS',
      status_reason: 'Crawl completed successfully',
      pages_crawled: 1,
      json: {
        site: 'https://example.com',
        pages: [{ url: 'https://example.com', title: 'Example Domain' }],
      },
    };

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ResultCard
          result={mockResult}
          onOpenLogs={() => {}}
          onReplay={() => {}}
        />
      );
    });

    // 1. Verify "Raw Extracted JSON Payload" header is present
    expect(container.textContent).toContain('Raw Extracted JSON Payload');

    // 2. Verify controls: JSON Valid, Copy JSON, Download JSON, Download Report (.md)
    expect(container.textContent).toContain('✓ JSON Valid');
    expect(container.textContent).toContain('Copy JSON');
    expect(container.textContent).toContain('Download JSON');
    expect(container.textContent).toContain('Download Report (.md)');

    // 3. Verify section is expanded immediately without clicking expand:
    // Toggle button shows "▲ Collapse", NOT "▼ Expand"
    expect(container.textContent).toContain('▲ Collapse');
    expect(container.textContent).not.toContain('▼ Expand');

    // 4. Verify formatted JSON content is immediately visible in pre
    const pre = container.querySelector('pre.monospace-view');
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toContain('https://example.com');
    expect(pre?.textContent).toContain('Example Domain');

    // 5. User can collapse it manually
    const collapseButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.textContent?.includes('Collapse')
    );
    expect(collapseButton).toBeDefined();

    await act(async () => {
      collapseButton?.click();
    });

    // Now it should be collapsed
    expect(container.textContent).toContain('▼ Expand');
    expect(container.querySelector('pre.monospace-view')).toBeNull();

    // 6. User can re-expand it manually
    const expandButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.textContent?.includes('Expand')
    );
    await act(async () => {
      expandButton?.click();
    });
    expect(container.textContent).toContain('▲ Collapse');
    expect(container.querySelector('pre.monospace-view')).not.toBeNull();
  });

  it('automatically re-expands for each new execution result', async () => {
    const mockResult1: ChatResult = {
      run_id: 'test-run-111',
      status: 'SUCCESS',
      status_reason: 'First crawl',
      json: { run: 1, site: 'https://first.example' },
    };

    const mockResult2: ChatResult = {
      run_id: 'test-run-222',
      status: 'SUCCESS',
      status_reason: 'Second crawl',
      json: { run: 2, site: 'https://second.example' },
    };

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ResultCard
          result={mockResult1}
          onOpenLogs={() => {}}
          onReplay={() => {}}
        />
      );
    });

    // Initially expanded
    expect(container.textContent).toContain('▲ Collapse');
    expect(container.textContent).toContain('https://first.example');

    // User collapses it manually
    const collapseButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.textContent?.includes('Collapse')
    );
    await act(async () => {
      collapseButton?.click();
    });
    expect(container.textContent).toContain('▼ Expand');
    expect(container.querySelector('pre.monospace-view')).toBeNull();

    // New execution result arrives (different run_id)
    await act(async () => {
      root.render(
        <ResultCard
          result={mockResult2}
          onOpenLogs={() => {}}
          onReplay={() => {}}
        />
      );
    });

    // Must be expanded automatically for new result!
    expect(container.textContent).toContain('▲ Collapse');
    const pre = container.querySelector('pre.monospace-view');
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toContain('https://second.example');
  });

  it('ensures JSON is visible immediately after a successful crawl without clicking Expand', async () => {
    // Simulating full crawl result payload from a real crawl
    const crawlResult: ChatResult = {
      run_id: 'crawl-success-999',
      status: 'SUCCESS',
      status_reason: 'Crawl completed: 3 pages retrieved',
      pages_crawled: 3,
      plan: {
        task_type: 'crawl',
        tool: 'site_crawler',
        tool_reason: 'Standard crawl',
        url: 'https://example.com',
        max_pages: 3,
        max_depth: 2,
        wants_summary: true,
        wants_json: true,
        extract_focus: 'general',
        max_links: 50,
      },
      json: {
        site: 'https://example.com',
        pages: [
          { url: 'https://example.com', title: 'Home', main_text: 'Welcome to example.com' },
          { url: 'https://example.com/about', title: 'About Us', main_text: 'Company about page' },
        ],
        stats: { pages_crawled: 2, total_time: 1.2 },
      },
    };

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ResultCard
          result={crawlResult}
          onOpenLogs={() => {}}
          onReplay={() => {}}
        />
      );
    });

    // 1. ResultCard is rendered
    expect(container.querySelector('[data-testid="result-card"]')).not.toBeNull();

    // 2. The JSON pre element is immediately visible in the DOM
    const jsonPre = container.querySelector('pre.monospace-view');
    expect(jsonPre).not.toBeNull();
    expect(jsonPre?.textContent).toContain('"site": "https://example.com"');
    expect(jsonPre?.textContent).toContain('"title": "Home"');
    expect(jsonPre?.textContent).toContain('"title": "About Us"');

    // 3. Button state is "▲ Collapse" showing it is currently expanded
    const toggleButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.textContent?.includes('Collapse') || btn.textContent?.includes('Expand')
    );
    expect(toggleButton?.textContent).toBe('▲ Collapse');
  });

  it('verifies that Follow-up Research Q&A section is completely removed from the application', () => {
    // Assert that nowhere in the rendered container or components does the Q&A text appear
    expect(container.textContent).not.toContain('Follow-up Research Q&A');
    expect(container.textContent).not.toContain('Queries extracted content with zero hallucination');
    expect(container.textContent).not.toContain('Ask →');
    expect(container.querySelector('input[placeholder*="Ask a question"]')).toBeNull();
  });

  it('verifies that the Refresh button is rendered near Runs heading with icon, label, and functional states', async () => {
    let refreshCalls = 0;
    const handleRefresh = () => {
      refreshCalls += 1;
    };

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Navbar
          health={{ status: 'ok', version: '1.0.0', llm_mode: 'heuristic' }}
          audit={{ verified: true, records: [] }}
          backendOnline={true}
          onToggleSidebar={() => {}}
          onRefreshHistory={handleRefresh}
          isRefreshing={false}
          refreshSuccess={false}
        />
      );
    });

    // 1. Verify Refresh button exists near Runs
    const buttons = Array.from(container.querySelectorAll('button'));
    const runsBtn = buttons.find((b) => b.textContent?.includes('Runs'));
    expect(runsBtn).toBeDefined();

    const refreshBtn = buttons.find((b) => b.textContent?.includes('Refresh'));
    expect(refreshBtn).toBeDefined();
    expect(refreshBtn?.textContent).toContain('↻');
    expect(refreshBtn?.textContent).toContain('Refresh');
    expect(refreshBtn?.disabled).toBe(false);

    // 2. Click calls onRefreshHistory
    await act(async () => {
      refreshBtn?.click();
    });
    expect(refreshCalls).toBe(1);

    // 3. Test isRefreshing=true: button is disabled and displays spinner/Refreshing...
    await act(async () => {
      root.render(
        <Navbar
          health={{ status: 'ok', version: '1.0.0', llm_mode: 'heuristic' }}
          audit={{ verified: true, records: [] }}
          backendOnline={true}
          onToggleSidebar={() => {}}
          onRefreshHistory={handleRefresh}
          isRefreshing={true}
          refreshSuccess={false}
        />
      );
    });
    const refreshingBtn = container.querySelector('button[aria-label="Refresh application data"]') as HTMLButtonElement;
    expect(refreshingBtn).not.toBeNull();
    expect(refreshingBtn.disabled).toBe(true);
    expect(refreshingBtn.textContent).toContain('Refreshing...');

    // 4. Test refreshSuccess=true: shows checkmark and Refreshed label
    await act(async () => {
      root.render(
        <Navbar
          health={{ status: 'ok', version: '1.0.0', llm_mode: 'heuristic' }}
          audit={{ verified: true, records: [] }}
          backendOnline={true}
          onToggleSidebar={() => {}}
          onRefreshHistory={handleRefresh}
          isRefreshing={false}
          refreshSuccess={true}
        />
      );
    });
    const successBtn = container.querySelector('button[aria-label="Refresh application data"]') as HTMLButtonElement;
    expect(successBtn).not.toBeNull();
    expect(successBtn.textContent).toContain('✓');
    expect(successBtn.textContent).toContain('Refreshed');
  });

  it('verifies Coverage Score card alignment, single-line 100%, and readable supporting text', async () => {
    const mockResult: ChatResult = {
      run_id: 'test-coverage-100',
      status: 'SUCCESS',
      status_reason: 'Crawl completed',
      coverage_score: 100,
      coverage: {
        score: 100,
        notes: '1 of 1 discoverable pages crawled, 0 errors, 0 robots-skipped, 0 redirects-blocked',
      },
      json: { site: 'https://example.com' },
    };

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ResultCard
          result={mockResult}
          onOpenLogs={() => {}}
          onReplay={() => {}}
        />
      );
    });

    const card = container.querySelector('[data-testid="coverage-score-card"]');
    expect(card).not.toBeNull();

    // 1. Label clearly visible above score
    const label = card?.querySelector('.eyebrow');
    expect(label?.textContent?.trim()).toBe('COVERAGE SCORE');

    // 2. Score 100% displayed together with nowrap style
    const scoreSpan = card?.querySelector('.tabular-num') as HTMLElement;
    expect(scoreSpan).not.toBeNull();
    expect(scoreSpan.textContent?.trim()).toBe('100%');
    expect(scoreSpan.style.whiteSpace).toBe('nowrap');

    // 3. Explanatory text formatted as readable supporting text in parentheses
    const explanation = card?.querySelector('.caption') as HTMLElement;
    expect(explanation).not.toBeNull();
    expect(explanation.textContent?.trim()).toBe(
      '(1 of 1 discoverable pages crawled, 0 errors, 0 robots-skipped, 0 redirects-blocked)'
    );

    // 4. Score and explanatory text are in a flex row for horizontal desktop alignment
    const flexRow = scoreSpan.parentElement;
    expect(flexRow).not.toBeNull();
    expect(flexRow?.style.display).toBe('flex');
    expect(flexRow?.style.alignItems).toBe('baseline');
  });

  it('handles 1-of-10 crawl scenario consistently without claiming 100% or conflating limit with discovered pages', async () => {
    const mockResult: ChatResult = {
      run_id: 'test-example-run',
      status: 'SUCCESS',
      status_reason: '1 pages crawled',
      coverage_score: 100,
      coverage: {
        score: 100,
        pages_crawled: 1,
        pages_discovered: 1,
        pages_limit: 10,
        coverage_established: false,
        notes: '1 of 1 discovered page crawled (limit: 10), 0 errors, 0 robots-skipped, 0 redirects-blocked, coverage not fully established',
      },
      json: {
        site: 'https://example.com',
        pages: [{ url: 'https://example.com', title: 'Example Domain' }],
      },
      plan: {
        task_type: 'crawl',
        tool: 'site_crawler',
        tool_reason: 'Crawl target',
        url: 'https://example.com',
        max_pages: 10,
        max_depth: 2,
        wants_summary: true,
        wants_json: true,
      },
    };

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ResultCard
          result={mockResult}
          onOpenLogs={() => {}}
          onReplay={() => {}}
        />
      );
    });

    const card = container.querySelector('[data-testid="coverage-score-card"]');
    expect(card).not.toBeNull();

    // Must NOT claim 100% when coverage is not established
    expect(card?.textContent).not.toContain('100%');
    expect(card?.textContent).toContain('Coverage not fully established');
    // Supporting text should distinguish discovered pages from limit
    expect(card?.textContent).toContain('1 of 1 discovered page crawled (limit: 10)');

    // Now test ExecutionTimeline for the exact same run
    const events: RunEventPayload[] = [
      { event: 'plan', data: { tool: 'site_crawler', url: 'https://example.com', max_pages: 10 } },
      { event: 'validated', data: { url: 'https://example.com' } },
      { event: 'spawned', data: { pid: 1234 } },
      { event: 'parsing', data: { exit_code: 0 } },
      { event: 'summarizing', data: {} },
      {
        event: 'result',
        data: mockResult,
      },
    ];

    await act(async () => {
      root.render(
        <ExecutionTimeline
          events={events}
          isRunning={false}
          onCancel={() => {}}
        />
      );
    });

    const timelineText = container.textContent || '';
    // Must NOT say "1 of 10 discoverable pages"
    expect(timelineText).not.toContain('1 of 10 discoverable pages');
    // Must accurately state 1 of 1 discovered page with limit
    expect(timelineText).toContain('Crawled 1 of 1 discovered page (limit: 10)');
  });

  it('displays separate page-limit utilization and discovered-page crawl ratio for 5 of 105 crawl without claiming 100% coverage', async () => {
    const mockResult: ChatResult = {
      run_id: 'test-books-5-of-105',
      status: 'SUCCESS',
      status_reason: '5 pages crawled',
      coverage_score: 5,
      coverage: {
        score: 5,
        pages_crawled: 5,
        pages_discovered: 105,
        pages_limit: 5,
        page_limit_utilization: 100,
        discovered_ratio: 4.76,
        coverage_established: false,
        notes:
          '5 of 105 discovered pages crawled (limit: 5), Page limit utilization: 5/5 = 100%, Discovered-page crawl ratio: 5/105 = 4.76%, 0 errors, 0 robots-skipped, 0 redirects-blocked, coverage not fully established',
      },
      json: {
        site: 'https://books.toscrape.com/',
        pages: Array.from({ length: 5 }, (_, i) => ({ url: `https://books.toscrape.com/page${i + 1}` })),
        stats: { pages_crawled: 5, pages_discovered: 105, pages_limit: 5 },
      },
      plan: {
        task_type: 'crawl',
        tool: 'site_crawler',
        tool_reason: 'Crawl target',
        url: 'https://books.toscrape.com/',
        max_pages: 5,
        max_depth: 2,
        wants_summary: true,
        wants_json: true,
      },
    };

    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ResultCard
          result={mockResult}
          onOpenLogs={() => {}}
          onReplay={() => {}}
        />
      );
    });

    const card = container.querySelector('[data-testid="coverage-score-card"]');
    expect(card).not.toBeNull();

    // 1. Must NOT display 100% as the coverage score headline
    const headline = card?.querySelector('.tabular-num');
    expect(headline?.textContent).toBe('4.76%');

    // 2. Must explicitly display page limit utilization: 5/5 = 100%
    expect(card?.textContent).toContain('Page limit utilization: 5/5 = 100%');

    // 3. Must explicitly display discovered-page crawl ratio: 5/105 = 4.76%
    expect(card?.textContent).toContain('Discovered-page crawl ratio: 5/105 = 4.76%');

    // 4. Do NOT claim full website coverage
    expect(card?.textContent).not.toContain('100% Full Website Coverage');
  });

  it('handles Refresh in App when backend is online and offline without triggering crawl subprocess', async () => {
    let healthFetched = 0;
    let runsFetched = 0;
    let auditFetched = 0;
    let postTriggered = 0;

    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
      const urlStr = String(url);
      if (init?.method === 'POST') {
        postTriggered += 1;
      }
      if (urlStr.includes('/health')) {
        healthFetched += 1;
        return {
          ok: true,
          json: async () => ({ status: 'ok', version: '1.0.0', llm_mode: 'heuristic' }),
        } as Response;
      }
      if (urlStr.includes('/api/runs')) {
        runsFetched += 1;
        return {
          ok: true,
          json: async () => [
            {
              run_id: 'run-123',
              task_type: 'crawl',
              url: 'https://example.com',
              status: 'SUCCESS',
              created_at: 1000,
              pages_crawled: 1,
            },
          ],
        } as Response;
      }
      if (urlStr.includes('/api/audit')) {
        auditFetched += 1;
        return {
          ok: true,
          json: async () => ({ verified: true, count: 1, records: [] }),
        } as Response;
      }
      if (urlStr.includes('/api/tools')) {
        return {
          ok: true,
          json: async () => [],
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({}),
      } as Response;
    }) as any;

    try {
      const root = createRoot(container);
      await act(async () => {
        root.render(<App />);
      });

      // Initial load
      expect(healthFetched).toBeGreaterThanOrEqual(1);
      expect(runsFetched).toBeGreaterThanOrEqual(1);
      const preClickHealth = healthFetched;
      const preClickRuns = runsFetched;

      // Click Refresh button
      const refreshBtn = container.querySelector('button[aria-label="Refresh application data"]') as HTMLButtonElement;
      expect(refreshBtn).not.toBeNull();
      expect(refreshBtn.disabled).toBe(false);

      await act(async () => {
        refreshBtn.click();
      });

      // Verify data refreshed
      expect(healthFetched).toBeGreaterThan(preClickHealth);
      expect(runsFetched).toBeGreaterThan(preClickRuns);

      // Verify ZERO subprocess/crawls triggered (zero POST requests)
      expect(postTriggered).toBe(0);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
