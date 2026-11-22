/** @typedef {{message: string, session_id?: string|null}} ChatRequest */
/** @typedef {{answer: string, domains: string[], confidence: number, needs_clarification: boolean, clarification_question: string|null, is_out_of_scope: boolean, sources: Array<{chunk_id:string,domain:string,source_title:string,page:number|null,score:number|null,source_url:string|null}>, session_id:string|null, metadata: Record<string,unknown>}} ChatResponse */

export const LIVE_API_ENABLED = import.meta.env.VITE_USE_LIVE_API === 'true';
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

/**
 * Call the *existing* CampusOne FastAPI contract; no invented auth endpoints.
 * @param {ChatRequest} request
 * @param {AbortSignal} [signal]
 * @returns {Promise<ChatResponse>}
 */
export async function fetchChatAnswer(request, signal) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        detail = body.detail.map(d => (d && d.msg) ? d.msg : JSON.stringify(d)).join('; ');
      } else if (body && body.detail) {
        detail = JSON.stringify(body.detail);
      }
    } catch { /* response not JSON */ }
    throw new Error(detail || `CampusOne API returned HTTP ${response.status}`);
  }
  const data = await response.json();
  if (!data || typeof data.answer !== 'string' || !Array.isArray(data.domains)) {
    throw new Error('Unexpected response from CampusOne API');
  }
  return data;
}
