import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ChatInput } from './components/ChatInput';
import { ErrorBanner } from './components/ErrorBanner';
import { ExecutionTimeline } from './components/ExecutionTimeline';
import { GuardrailRow } from './components/GuardrailRow';
import { HeroSection } from './components/HeroSection';
import { LogsDrawer } from './components/LogsDrawer';
import { Navbar } from './components/Navbar';
import { PlanCard } from './components/PlanCard';
import { ResultCard } from './components/ResultCard';
import { RunHistorySidebar } from './components/RunHistorySidebar';
import { SecurityFindingsPanel } from './components/SecurityFindingsPanel';
import type {
  AuditChain,
  ChatResult,
  HealthResponse,
  Plan,
  RunEventPayload,
  RunListItem,
  RunStatus,
  ToolConfig,
} from './types';
import {
  cancelRun,
  fetchAudit,
  fetchHealth,
  fetchRun,
  fetchRuns,
  fetchTools,
  replayRunStream,
  startChatStream,
} from './utils/api';

export interface RouteInfo {
  view: 'home' | 'runs' | 'run-detail' | 'run-logs' | 'not-found';
  path: string;
  runId?: string;
}

export function parsePath(pathname: string): RouteInfo {
  const norm = pathname.replace(/\/+$/, '') || '/';
  if (norm === '/') {
    return { view: 'home', path: '/' };
  }
  if (norm === '/runs') {
    return { view: 'runs', path: '/runs' };
  }
  const detailsMatch = norm.match(/^\/runs\/([^/]+)\/details$/);
  if (detailsMatch) {
    return { view: 'run-logs', path: norm, runId: detailsMatch[1] };
  }
  const runMatch = norm.match(/^\/runs\/([^/]+)$/);
  if (runMatch) {
    return { view: 'run-detail', path: norm, runId: runMatch[1] };
  }
  return { view: 'not-found', path: norm };
}

export const App: React.FC = () => {
  // Routing state
  const [route, setRoute] = useState<RouteInfo>(() =>
    parsePath(typeof window !== 'undefined' ? window.location.pathname : '/')
  );

  // System status
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [audit, setAudit] = useState<AuditChain | null>(null);
  const [tools, setTools] = useState<ToolConfig[]>([]);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [backendOnline, setBackendOnline] = useState<boolean>(true);

  // Active run state
  const [activeRunId, setActiveRunId] = useState<string>('');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [events, setEvents] = useState<RunEventPayload[]>([]);
  const [currentPlan, setCurrentPlan] = useState<Plan | null>(null);
  const [result, setResult] = useState<ChatResult | null>(null);
  const [terminalStatus, setTerminalStatus] = useState<RunStatus | undefined>(undefined);

  // Errors & UI state
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState<number | undefined>(undefined);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 768 : false
  );
  const [showLogsDrawer, setShowLogsDrawer] = useState<boolean>(false);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Navigation helper
  const navigate = useCallback((path: string) => {
    if (typeof window !== 'undefined' && window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }
    setRoute(parsePath(path));
  }, []);

  // Sync popstate (browser back/forward)
  useEffect(() => {
    const handlePopState = () => {
      setRoute(parsePath(window.location.pathname));
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Fetch initial system state
  const loadSystemState = useCallback(async () => {
    try {
      const [h, a, t, r] = await Promise.all([
        fetchHealth(),
        fetchAudit().catch(() => null),
        fetchTools().catch(() => []),
        fetchRuns().catch(() => []),
      ]);
      setHealth(h);
      if (a) setAudit(a);
      setTools(t);
      setRuns(r);
      setBackendOnline(true);
      setErrorMsg(null);
    } catch {
      setBackendOnline(false);
      setErrorMsg('Cannot connect to backend. Ensure the backend server is running.');
    }
  }, []);

  useEffect(() => {
    loadSystemState();
  }, [loadSystemState]);

  // Select a run from history or route
  const handleSelectRun = useCallback(async (runId: string) => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
    try {
      const data = await fetchRun(runId);
      setActiveRunId(runId);
      setErrorMsg(null);

      if (Array.isArray(data.events)) {
        setEvents(data.events as RunEventPayload[]);
      }

      if (data.plan) {
        setCurrentPlan(data.plan as Plan);
      } else {
        setCurrentPlan(null);
      }

      if (data.result) {
        const res = data.result as ChatResult;
        setResult(res);
        setTerminalStatus(res.status);
      } else {
        setResult(null);
        setTerminalStatus(data.status as RunStatus);
      }
    } catch (err: unknown) {
      setActiveRunId(runId);
      setEvents([]);
      setCurrentPlan(null);
      setResult(null);
      setTerminalStatus(undefined);
      setErrorMsg(
        err instanceof Error
          ? `Run "${runId}" not found or backend was restarted.`
          : 'Failed to load run details'
      );
    }
  }, []);

  // React to route changes (direct load or navigation)
  useEffect(() => {
    if ((route.view === 'run-detail' || route.view === 'run-logs') && route.runId) {
      if (route.runId !== activeRunId) {
        handleSelectRun(route.runId);
      }
      if (route.view === 'run-logs') {
        setShowLogsDrawer(true);
      } else {
        setShowLogsDrawer(false);
      }
    } else if (route.view === 'runs') {
      setIsSidebarOpen(true);
      setShowLogsDrawer(false);
    } else if (route.view === 'home') {
      setShowLogsDrawer(false);
    }
  }, [route, activeRunId, handleSelectRun]);

  // Handle Event from SSE Stream
  const handleIncomingEvent = useCallback((evt: RunEventPayload) => {
    setEvents((prev) => [...prev, evt]);

    if (evt.run_id) {
      setActiveRunId(evt.run_id);
    }

    if (evt.event === 'plan' && evt.data) {
      setCurrentPlan(evt.data as unknown as Plan);
    } else if (evt.event === 'result' && evt.data) {
      const res = evt.data as unknown as ChatResult;
      setResult(res);
      setTerminalStatus(res.status);
    } else if (evt.event === 'error' && evt.data) {
      const err = (evt.data.error as string) || 'Execution failed';
      setErrorMsg(err);
      setTerminalStatus('FAILED');
    } else if (evt.event === 'cancelled') {
      setTerminalStatus('CANCELLED');
    } else if (evt.event === 'timeout') {
      setTerminalStatus('TIMEOUT');
    }
  }, []);

  // Submit Prompt
  const handlePromptSubmit = async (prompt: string) => {
    setErrorMsg(null);
    setRetryAfter(undefined);
    setEvents([]);
    setCurrentPlan(null);
    setResult(null);
    setTerminalStatus(undefined);
    setIsRunning(true);

    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    try {
      await startChatStream(prompt, handleIncomingEvent, abortCtrl.signal);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'status' in err) {
        const apiErr = err as { status: number; message: string; retry_after_s?: number };
        setErrorMsg(apiErr.message);
        if (apiErr.retry_after_s) {
          setRetryAfter(apiErr.retry_after_s);
        }
      } else {
        setErrorMsg(err instanceof Error ? err.message : 'Error starting stream');
      }
      setTerminalStatus('FAILED');
    } finally {
      setIsRunning(false);
      abortControllerRef.current = null;
      // Refresh past runs and audit chain
      fetchRuns().then(setRuns).catch(() => {});
      fetchAudit().then(setAudit).catch(() => {});
    }
  };

  // Cancel execution
  const handleCancelRun = async () => {
    if (activeRunId) {
      try {
        await cancelRun(activeRunId);
      } catch {
        // ignore
      }
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsRunning(false);
    setTerminalStatus('CANCELLED');
  };

  // Replay run stream
  const handleReplay = async () => {
    if (!activeRunId) return;
    setEvents([]);
    setErrorMsg(null);
    setIsRunning(true);
    try {
      await replayRunStream(activeRunId, handleIncomingEvent);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Replay failed');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', width: '100%' }}>
      {/* Top Navbar */}
      <Navbar
        health={health}
        audit={audit}
        backendOnline={backendOnline}
        onToggleSidebar={() => {
          const next = !isSidebarOpen;
          setIsSidebarOpen(next);
          if (next) navigate('/runs');
        }}
        onRefreshHistory={loadSystemState}
        onNavigateHome={() => navigate('/')}
      />

      {/* Main Workspace with Sidebar */}
      <div style={{ display: 'flex', flex: 1, position: 'relative', minWidth: 0 }}>
        {/* Run History Sidebar */}
        <RunHistorySidebar
          runs={runs}
          activeRunId={activeRunId}
          onSelectRun={(runId) => navigate(`/runs/${runId}`)}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
        />

        {/* Primary Page Canvas */}
        <main className="main-canvas">
          {/* Error Banner */}
          <ErrorBanner
            error={errorMsg}
            retryAfterSeconds={retryAfter}
            onDismiss={() => setErrorMsg(null)}
          />

          {route.view === 'not-found' ? (
            <div
              data-testid="not-found-view"
              className="card-panel"
              style={{
                backgroundColor: 'var(--card)',
                textAlign: 'center',
                padding: '48px 24px',
                margin: '32px auto',
                maxWidth: '600px',
                border: '1px solid var(--hairline)',
              }}
            >
              <div
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: '48px',
                  fontWeight: 800,
                  color: 'var(--ink)',
                  lineHeight: 1.1,
                  marginBottom: '12px',
                }}
              >
                404
              </div>
              <h2
                style={{
                  fontSize: '20px',
                  fontWeight: 700,
                  color: 'var(--ink)',
                  marginBottom: '12px',
                }}
              >
                Page Not Found
              </h2>
              <p
                style={{
                  color: 'var(--muted)',
                  fontSize: '15px',
                  marginBottom: '24px',
                  lineHeight: 1.5,
                }}
              >
                The requested route{' '}
                <code style={{ backgroundColor: 'var(--page)', padding: '2px 6px', borderRadius: '4px' }}>
                  {route.path}
                </code>{' '}
                was not found on this server.
              </p>
              <button
                type="button"
                className="btn-primary"
                onClick={() => navigate('/')}
                style={{
                  backgroundColor: 'var(--navy)',
                  color: '#FFFFFF',
                  padding: '10px 24px',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '14px',
                  cursor: 'pointer',
                  border: 'none',
                }}
              >
                Back to Home
              </button>
            </div>
          ) : (
            <>
              {/* Guardrails Overview */}
              <GuardrailRow tools={tools} health={health} />

              {/* Hero Section */}
              <HeroSection />

              {/* Chat / Prompt Input with Example Chips */}
              <ChatInput
                onSubmit={handlePromptSubmit}
                isRunning={isRunning}
                onCancel={handleCancelRun}
              />

              {/* Parsed Execution Plan */}
              {currentPlan && <PlanCard plan={currentPlan} />}

              {/* Live Execution Timeline */}
              {(isRunning || events.length > 0) && (
                <ExecutionTimeline
                  events={events}
                  runId={activeRunId}
                  isRunning={isRunning}
                  terminalStatus={terminalStatus}
                  onCancel={handleCancelRun}
                />
              )}

              {/* Security Findings Panel (if findings detected) */}
              {result?.security_findings && result.security_findings.length > 0 && (
                <SecurityFindingsPanel findings={result.security_findings} />
              )}

              {/* Final Result Card */}
              {result && (
                <ResultCard
                  result={result}
                  onOpenLogs={() => {
                    setShowLogsDrawer(true);
                    navigate(`/runs/${activeRunId}/details`);
                  }}
                  onReplay={handleReplay}
                />
              )}
            </>
          )}
        </main>
      </div>

      {/* Slide-out Subprocess Logs Drawer */}
      {showLogsDrawer && activeRunId && (
        <LogsDrawer
          runId={activeRunId}
          onClose={() => {
            setShowLogsDrawer(false);
            navigate(activeRunId ? `/runs/${activeRunId}` : '/');
          }}
        />
      )}
    </div>
  );
};
export default App;