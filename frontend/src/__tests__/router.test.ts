import { describe, expect, it } from 'vitest';
import { parsePath } from '../App';

describe('Router path parser', () => {
  it('parses root route /', () => {
    expect(parsePath('/')).toEqual({ view: 'home', path: '/' });
    expect(parsePath('')).toEqual({ view: 'home', path: '/' });
  });

  it('parses /runs list route', () => {
    expect(parsePath('/runs')).toEqual({ view: 'runs', path: '/runs' });
    expect(parsePath('/runs/')).toEqual({ view: 'runs', path: '/runs' });
  });

  it('parses /runs/:id detail route', () => {
    expect(parsePath('/runs/run-456')).toEqual({
      view: 'run-detail',
      path: '/runs/run-456',
      runId: 'run-456',
    });
  });

  it('parses /runs/:id/details logs route', () => {
    expect(parsePath('/runs/run-456/details')).toEqual({
      view: 'run-logs',
      path: '/runs/run-456/details',
      runId: 'run-456',
    });
  });

  it('returns not-found for unknown routes', () => {
    expect(parsePath('/unknown')).toEqual({
      view: 'not-found',
      path: '/unknown',
    });
    expect(parsePath('/runs/run-123/details/extra')).toEqual({
      view: 'not-found',
      path: '/runs/run-123/details/extra',
    });
    expect(parsePath('/admin')).toEqual({
      view: 'not-found',
      path: '/admin',
    });
  });
});
