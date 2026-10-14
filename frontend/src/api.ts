/*
 * Copyright 2026 Aswin A
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const API = '/api/v1';
function csrf() { return document.cookie.split('; ').find((row) => row.startsWith('hs_v2_csrf='))?.split('=').slice(1).join('=') || ''; }
export async function request<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (init.method && !['GET', 'HEAD'].includes(init.method.toUpperCase())) headers.set('X-CSRF-Token', decodeURIComponent(csrf()));
  const response = await fetch(`${API}${path}`, { ...init, headers, credentials: 'include' });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch { /* keep status */ }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });
export const put = <T,>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });
export const del = <T,>(path: string) => request<T>(path, { method: 'DELETE' });

