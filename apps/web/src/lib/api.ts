const headers = { "X-Tenant-ID": "00000000-0000-0000-0000-000000000001", "X-User-ID": "00000000-0000-0000-0000-000000000001", "X-Roles": "admin,reviewer" };

export type RequestItem = { id: string; scope_id: string; status: string; policy_version: string; created_at: string; updated_at: string };
export type DocumentItem = { id: string; request_id: string; original_name: string; mime_type: string; size_bytes: number; pages: number; status: string; created_at: string };
export type Evidence = { id: string; page_id: string; start_offset: number; end_offset: number; bbox: Record<string, unknown>; entity_type: string; semantic_role: string | null; score: number; detector: string; reason_codes: string[]; review_status: string; original_text?: string | null };
export type SafeText = { request_id: string; revision: number; text: string; validation_report: Record<string, unknown>; approved: boolean };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { ...headers, ...(init?.headers ?? {}) } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message ?? body.detail ?? `HTTP ${response.status}`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  createRequest: () => request<RequestItem>("/api/v1/requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ policy: { categories: "italian-pii", manual_approval: true } }) }),
  upload: (requestId: string, file: File) => { const form = new FormData(); form.append("file", file); return request<DocumentItem>(`/api/v1/requests/${requestId}/documents`, { method: "POST", body: form }); },
  documents: (requestId: string) => request<DocumentItem[]>(`/api/v1/requests/${requestId}/documents`),
  extract: (documentId: string) => request<DocumentItem>(`/api/v1/documents/${documentId}/extract`, { method: "POST" }),
  detect: (requestId: string) => request<Record<string, unknown>>(`/api/v1/requests/${requestId}/detect`, { method: "POST" }),
  evidences: (requestId: string) => request<Evidence[]>(`/api/v1/requests/${requestId}/evidences`),
  approve: (requestId: string) => request<Record<string, unknown>>(`/api/v1/requests/${requestId}/review/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm_all: true }) }),
  pseudonymize: (requestId: string) => request<SafeText>(`/api/v1/requests/${requestId}/pseudonymize`, { method: "POST" }),
  safeText: (requestId: string) => request<SafeText>(`/api/v1/requests/${requestId}/pseudonymized-text`),
  validate: (requestId: string) => request<Record<string, unknown>>(`/api/v1/requests/${requestId}/validate`, { method: "POST" }),
  send: (requestId: string) => request<Record<string, unknown>>(`/api/v1/requests/${requestId}/send`, { method: "POST" }),
};
