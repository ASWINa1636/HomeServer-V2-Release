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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

const owner = { id: 1, name: 'Server Owner', email: 'owner@example.test', username: 'owner', role: 'system_owner' };
function json(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }); }
function boot(path: string) { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>); }

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/auth/me')) return json(owner);
    if (url.endsWith('/setup/status')) return json({ initialized: false, server_name: 'HomeServer' });
    if (url.endsWith('/workspaces')) return json({ items: [{ id: 1, name: 'My workspace', kind: 'personal', role: 'owner' }] });
    if (url.includes('/files?path=')) return json({ items: [] });
    if (url.endsWith('/health/ready')) return json({ status: 'ready' });
    if (url.endsWith('/auth/bootstrap-status')) return json({ available: true });
    if (url.endsWith('/setup/')) return json({ initialized: true });
    if (url.endsWith('/storage/status')) return json({
      current_location: { name: 'Primary storage', path: '/data', is_default: true },
      total_bytes: 107374182400,
      used_bytes: 10737418240,
      free_bytes: 96636764160,
      percent_used: 10,
      readable: true,
      writable: true,
      status: 'available',
      health: 'healthy',
      locations_count: 1,
    });
    if (url.endsWith('/storage/locations')) return json({
      items: [{
        id: 1,
        name: 'Primary storage',
        root_key: 'default',
        relative_path: '',
        target_path: '/data',
        is_default: true,
        status: 'available',
        total_bytes: 107374182400,
        used_bytes: 10737418240,
        free_bytes: 96636764160,
        percent_used: 10,
        writable: true,
        readable: true,
      }],
      authorized_roots: [{ key: 'default', name: 'Primary Storage (/data)', container_path: '/data' }],
    });
    if (url.includes('/storage/browse')) return json({
      root_key: 'default',
      root_name: 'Primary Storage (/data)',
      container_path: '/data',
      current_path: '',
      breadcrumbs: [],
      folders: [{ name: 'users', path: 'users', can_write: true }],
      can_write: true,
      status: 'available',
      total_bytes: 107374182400,
      free_bytes: 96636764160,
    });
    if (url.endsWith('/storage/test')) return json({
      target: 'Primary storage',
      path: '/data',
      status: 'available',
      healthy: true,
      total_bytes: 107374182400,
      free_bytes: 96636764160,
      used_bytes: 10737418240,
      percent_used: 10,
      checks: [
        { name: 'Directory exists', passed: true, detail: 'Path: /data' },
        { name: 'Read permission', passed: true, detail: 'Readable' },
        { name: 'Write permission', passed: true, detail: 'Writable' },
        { name: 'Capacity measurement', passed: true, detail: 'Space available' },
      ],
    });
    if (url.endsWith('/admin/overview')) return json({
      server: {
        name: 'HomeServer V2',
        version: '2.0.0',
        migration_version: '0003_storage_locations',
        python_version: '3.12.9',
        hostname: 'homeserver-test',
        environment: 'testing',
        uptime_seconds: 3600,
        boot_time: new Date().toISOString(),
        checked_at: new Date().toISOString(),
      },
      health: {
        app: 'ok',
        database: 'ok',
        storage: 'available',
        overall: 'healthy',
      },
      system: {
        memory: { total_bytes: 16000000000, used_bytes: 8000000000, available_bytes: 8000000000 },
        load_average: [0.15, 0.20, 0.18],
      },
      storage: {
        location_name: 'Primary storage',
        container_path: '/data',
        status: 'available',
        total_bytes: 107374182400,
        used_bytes: 10737418240,
        free_bytes: 96636764160,
        percent_used: 10,
        writable: true,
        readable: true,
        total_files: 5,
        total_file_bytes: 10240,
        largest_files: [],
      },
      users: {
        total: 2,
        verified: 2,
        active: 2,
        suspended: 0,
        roles: { owners: 1, admins: 0, members: 1 },
        pending_invitations: 0,
        total_organizations: 1,
        total_workspaces: 2,
        registration_policy: 'open',
        recent_registrations: [],
      },
      security: {
        active_sessions: 1,
        recent_audit_events: [],
      },
      network: {
        local_url: 'http://localhost:8081',
        tailscale_configured: false,
        public_domain: null,
      },
    });
    if (url.endsWith('/admin/users')) return json({
      items: [
        {
          id: 1,
          full_name: 'Server Owner',
          email: 'owner@example.test',
          username: 'owner',
          role: 'system_owner',
          is_verified: true,
          is_active: true,
          created_at: new Date().toISOString(),
          workspaces_count: 1,
          files_count: 2,
          storage_bytes: 1024,
        },
      ],
      total: 1,
    });
    if (url.includes('/admin/users/') && url.endsWith('/workspaces')) return json({
      items: [
        {
          workspace_id: 1,
          workspace_name: 'Engineering Workspace',
          workspace_kind: 'organization',
          is_member: true,
          role: 'member',
          is_owner: false,
        },
      ],
    });
    if (url.includes('/admin/audit')) return json({
      items: [
        {
          id: 1,
          actor_user_id: 1,
          actor_email: 'owner@example.test',
          action: 'user.login',
          target: 'session',
          created_at: new Date().toISOString(),
        },
      ],
      total: 1,
    });
    if (url.includes('/network/tailscale')) return json({
      status: 'connected',
      is_configured: true,
      auto_detected: true,
      device_name: 'test-server',
      target: 'test-server.tailnet.ts.net',
      port: 8081,
      full_url: 'http://test-server.tailnet.ts.net:8081',
      last_checked: new Date().toISOString(),
      checks: [
        { name: 'Target syntax check', passed: true, detail: 'Valid MagicDNS' },
        { name: 'DNS resolution', passed: true, detail: 'Resolved to 100.79.132.16' },
        { name: 'TCP port 8081 probe', passed: true, detail: 'Port is open' },
        { name: 'Application health probe', passed: true, detail: 'HTTP /health/ready returned 200 OK' },
      ],
    });
    if (url.includes('/network/public')) return json({
      is_configured: false,
      domain: null,
      method: 'caddy',
      status: 'not_configured',
      public_url: null,
      last_checked: null,
      checks: [],
      security: {
        cookie_secure: false,
        trusted_hosts: 'localhost',
        database_isolated: true,
      },
    });
    if (url.includes('/backups/runbook')) return json({ runbook: '# Disaster Recovery & Restore Runbook\nStep 1...' });
    if (url.includes('/backups')) return json({
      items: [
        {
          backup_id: 'backup_20261009_120000',
          filename: 'backup_20261009_120000.tar.gz',
          created_at: new Date().toISOString(),
          size_bytes: 204800,
          sha256: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
          status: 'verified',
          files_count: 5,
        },
      ],
    });
    if (url.includes('/admin/diagnostics')) return json({
      overall_status: 'healthy',
      checked_at: new Date().toISOString(),
      checks: [
        { name: 'Backend Application Health', category: 'core', status: 'healthy', detail: 'FastAPI runtime is responsive', corrective_action: null },
        { name: 'Database Connectivity', category: 'database', status: 'healthy', detail: 'PostgreSQL is healthy (latency: 1.2 ms)', corrective_action: null },
        { name: 'Storage Read & Write', category: 'storage', status: 'healthy', detail: 'Writable and healthy (90.0 GB free)', corrective_action: null },
      ],
    });
    if (url.includes('/invitations/verify-token')) return json({ valid: true, email: 'invited@example.test', workspace_name: 'Dev Workspace', role: 'member' });
    if (url.includes('/auth/registration-policy')) return json({ policy: 'open' });
    if (url.endsWith('/invitations')) return json({
      items: [
        {
          id: 1,
          workspace_id: 1,
          email: 'alice@example.test',
          role: 'member',
          expires_at: new Date(Date.now() + 86400000).toISOString(),
          revoked: false,
          delivery_status: 'sent',
        },
      ],
    });
    if (url.includes('/invitations/1/link')) return json({ invite_url: 'http://localhost:8081/signup?token=fresh-token-123' });
    if (url.includes('/workspaces/1/members')) return json({
      items: [
        { id: 1, membership_id: 1, full_name: 'Server Owner', email: 'owner@example.test', role: 'owner', is_owner: true },
        { id: 2, membership_id: 2, full_name: 'Bob Member', email: 'bob@example.test', role: 'member', is_owner: false },
      ],
    });
    return json({ message: 'ok' }, 202);
  }));
});


afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('HomeServer V2 user flows', () => {
  it('shows the sign-in form', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => String(input).endsWith('/auth/me') ? json({}, 401) : json({}));
    boot('/login');
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeTruthy();
    expect(screen.getByLabelText('Email or username')).toBeTruthy();
  });

  it('submits credentials and opens the dashboard', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/me')) return json({}, 401);
      if (url.endsWith('/auth/login')) return json(owner);
      if (url.endsWith('/setup/status')) return json({ initialized: true });
      if (url.includes('/files?path=')) return json({ items: [] });
      return json({ status: 'ready' });
    });
    boot('/login');
    await userEvent.type(await screen.findByLabelText('Email or username'), 'owner');
    await userEvent.type(screen.getByLabelText('Password'), 'test-password');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByText(/good to see you, server/i)).toBeTruthy();
  });

  it('submits email verification codes', async () => {
    sessionStorage.setItem('verifyEmail', 'verify@example.com');
    boot('/verify');
    await userEvent.type(await screen.findByLabelText('Verification code'), '123456');
    await userEvent.click(screen.getByRole('button', { name: /verify email/i }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/v1/auth/verify', expect.objectContaining({ method: 'POST' })));
  });

  it('offers invited people sign-in and registration paths', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => String(input).endsWith('/auth/me') ? json({}, 401) : json({}));
    boot('/accept-invitation?token=invitation-secret');
    expect(await screen.findByRole('heading', { name: 'Workspace invitation' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /create account and accept/i }).getAttribute('href')).toContain('invite=invitation-secret');
    expect(screen.getByRole('link', { name: /sign in and accept/i }).getAttribute('href')).toContain('invite=invitation-secret');
  });

  it('renders first-run setup for the owner and persists wizard choices', async () => {
    boot('/');
    await screen.findByRole('heading', { name: /let’s make this server yours/i });
    await userEvent.click(screen.getByRole('button', { name: /continue/i }));
    const name = await screen.findByLabelText('Server name');
    await userEvent.clear(name);
    await userEvent.type(name, 'Family Cloud');
    await userEvent.click(screen.getByRole('button', { name: /continue/i }));
    await userEvent.click(screen.getByRole('button', { name: /continue/i }));
    await userEvent.click(screen.getByRole('button', { name: /continue/i }));
    await userEvent.click(screen.getByRole('button', { name: /continue/i }));
    await userEvent.selectOptions(screen.getByLabelText('New account access'), 'invitation_only');
    await userEvent.click(screen.getByRole('button', { name: /initialize server/i }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/v1/setup/', expect.objectContaining({ method: 'PUT', body: expect.stringContaining('Family Cloud') })));
  });

  it('shows the empty file manager state', async () => {
    boot('/files');
    expect(await screen.findByRole('heading', { name: 'My files' })).toBeTruthy();
    expect(await screen.findByText('This folder is empty')).toBeTruthy();
  });

  it('renders storage management and opens the browse modal', async () => {
    boot('/settings');
    expect(await screen.findByRole('heading', { name: 'Settings & storage' })).toBeTruthy();
    expect(await screen.findByText(/Active Storage Destination/i)).toBeTruthy();
    expect(screen.getByText(/Total capacity/i)).toBeTruthy();

    const browseBtn = await screen.findByRole('button', { name: /browse locations/i });
    await userEvent.click(browseBtn);
    expect(await screen.findByRole('heading', { name: /Browse Storage Directory/i })).toBeTruthy();
    expect(await screen.findByText('users')).toBeTruthy();
  });

  it('toggles dark mode and persists theme preference', async () => {
    boot('/');
    const themeBtn = await screen.findByRole('button', { name: /toggle theme/i });
    expect(themeBtn).toBeTruthy();

    await userEvent.click(themeBtn);
    expect(document.documentElement.getAttribute('data-theme')).toBeTruthy();
    expect(localStorage.getItem('hs_theme')).toBeTruthy();

    cleanup();
    boot('/settings');
    expect(await screen.findByRole('heading', { name: /Interface Theme/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Dark/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Light/i })).toBeTruthy();
  });

  it('renders administrator overview and displays real server health telemetry', async () => {
    boot('/admin');
    expect(await screen.findByRole('heading', { name: /Server Administration/i })).toBeTruthy();
    expect(await screen.findByRole('heading', { name: /Environment & Specs/i })).toBeTruthy();
    expect(screen.getByRole('heading', { name: /User Accounts/i })).toBeTruthy();
    expect(screen.getByRole('heading', { name: /Recent Security Audit Events/i })).toBeTruthy();
  });

  it('renders network management with local address and verified Tailscale status', async () => {
    boot('/network');
    expect(await screen.findByRole('heading', { name: /Reach Your Server/i })).toBeTruthy();
    expect(await screen.findByText(/Local Area Network Access/i)).toBeTruthy();
    expect(await screen.findByText(/Tailscale Private Network/i)).toBeTruthy();
    expect(screen.getByText(/http:\/\/test-server.tailnet.ts.net:8081/i)).toBeTruthy();
  });

  it('renders backup management and displays backup archive list', async () => {
    boot('/admin/backups');
    expect(await screen.findByRole('heading', { name: /Backup & Recovery/i })).toBeTruthy();
    expect(await screen.findByText('backup_20261009_120000.tar.gz')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Create Backup/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Restore Runbook/i })).toBeTruthy();
  });

  it('renders system diagnostics and displays health checks', async () => {
    boot('/admin/diagnostics');
    expect(await screen.findByRole('heading', { name: /System Diagnostics/i })).toBeTruthy();
    expect(await screen.findByText(/All Systems Nominal/i)).toBeTruthy();
    expect(screen.getByText(/Backend Application Health/i)).toBeTruthy();
    expect(screen.getByText(/Database Connectivity/i)).toBeTruthy();
  });

  it('renders dedicated /signup page with invitation token validation', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/me')) return json({}, 401);
      if (url.endsWith('/auth/bootstrap-status')) return json({ available: false });
      if (url.endsWith('/auth/registration-policy')) return json({ policy: 'open' });
      if (url.includes('/invitations/verify-token')) return json({ valid: true, email: 'invited@example.test', workspace_name: 'Dev Workspace', role: 'member' });
      return json({ message: 'ok' }, 202);
    });
    boot('/signup?token=valid-test-token');
    expect(await screen.findByRole('heading', { name: /Accept invitation & create account/i })).toBeTruthy();
    expect(await screen.findByText(/Dev Workspace/i)).toBeTruthy();
    expect(screen.getByLabelText('Full name')).toBeTruthy();
    expect(screen.getByLabelText('Email address')).toBeTruthy();
  });

  it('renders People & access page with invitation status badges and actions', async () => {
    boot('/people');
    expect(await screen.findByRole('heading', { name: /Share your server/i })).toBeTruthy();
    expect(await screen.findByText('alice@example.test')).toBeTruthy();
    expect(await screen.findByText(/Email sent/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /Copy link/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Revoke/i })).toBeTruthy();
  });

  it('allows changing workspace member role between Member and Read-only member', async () => {
    let currentRole = 'member';
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method || 'GET';
      if (url.endsWith('/auth/me')) return json(owner);
      if (url.endsWith('/workspaces')) return json({ items: [{ id: 1, name: 'My workspace', kind: 'personal', role: 'owner' }] });
      if (url.endsWith('/invitations')) return json({ items: [] });
      if (url.includes('/workspaces/1/members') && method === 'GET') {
        return json({
          items: [
            { id: 1, membership_id: 1, full_name: 'Server Owner', email: 'owner@example.test', role: 'owner', is_owner: true },
            { id: 2, membership_id: 2, full_name: 'Bob Member', email: 'bob@example.test', role: currentRole, is_owner: false },
          ],
        });
      }
      if (url.includes('/workspaces/1/members/2/role') && method === 'PUT') {
        const body = JSON.parse(String(init?.body || '{}'));
        currentRole = body.role;
        return json({ user_id: 2, workspace_id: 1, email: 'bob@example.test', role: body.role });
      }
      return json({ status: 'ok' });
    });

    boot('/people');
    expect(await screen.findByRole('heading', { name: /Your workspaces & members/i })).toBeTruthy();
    expect(await screen.findByText('Bob Member')).toBeTruthy();

    const roleSelect = await screen.findByLabelText('Role for Bob Member') as HTMLSelectElement;
    expect(roleSelect.value).toBe('member');

    // Change Member -> Read-only member
    await userEvent.selectOptions(roleSelect, 'read_only');
    expect(await screen.findByText(/Role for bob@example.test updated to read only/i)).toBeTruthy();

    // Change Read-only member -> Member
    await userEvent.selectOptions(roleSelect, 'member');
    expect(await screen.findByText(/Role for bob@example.test updated to member/i)).toBeTruthy();
  });

  it('opens Tailscale onboarding modal with remote link and instructions', async () => {
    boot('/network');
    const inviteBtn = await screen.findByRole('button', { name: /Invite user via Tailscale/i });
    expect(inviteBtn).toBeTruthy();
    await userEvent.click(inviteBtn);
    expect(await screen.findByRole('heading', { name: /Tailscale Remote Onboarding/i })).toBeTruthy();
    expect(screen.getByText(/How remote onboarding works:/i)).toBeTruthy();
  });

  it('allows promoting member to Workspace Admin in organization workspace', async () => {
    let currentRole = 'member';
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method || 'GET';
      if (url.endsWith('/auth/me')) return json(owner);
      if (url.endsWith('/workspaces')) return json({ items: [{ id: 5, name: 'Tech Team', kind: 'organization', role: 'organization_admin' }] });
      if (url.endsWith('/invitations')) return json({ items: [] });
      if (url.includes('/workspaces/5/members') && method === 'GET') {
        return json({
          workspace_kind: 'organization',
          items: [
            { id: 1, membership_id: 1, full_name: 'Server Owner', email: 'owner@example.test', role: 'organization_admin', is_owner: true },
            { id: 3, membership_id: 3, full_name: 'Alice Dev', email: 'alice@example.test', role: currentRole, is_owner: false },
          ],
        });
      }
      if (url.includes('/workspaces/5/members/3/role') && method === 'PUT') {
        const body = JSON.parse(String(init?.body || '{}'));
        currentRole = body.role;
        return json({ user_id: 3, workspace_id: 5, email: 'alice@example.test', role: body.role });
      }
      return json({ status: 'ok' });
    });

    boot('/people');
    expect(await screen.findByRole('heading', { name: /Your workspaces & members/i })).toBeTruthy();
    const roleSelect = await screen.findByLabelText('Role for Alice Dev') as HTMLSelectElement;
    expect(roleSelect.value).toBe('member');

    // Verify Workspace Admin option exists and can be selected
    const options = Array.from(roleSelect.options).map(o => o.value);
    expect(options).toContain('organization_admin');

    await userEvent.selectOptions(roleSelect, 'organization_admin');
    expect(await screen.findByText(/Role for alice@example.test updated to organization admin/i)).toBeTruthy();
  });

  it('displays read-only indicators and suppresses write buttons when workspace is read-only', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/me')) return json({ id: 4, name: 'Auditor User', email: 'auditor@example.test', username: 'auditor', role: 'system_admin' });
      if (url.endsWith('/workspaces')) return json({
        items: [
          { id: 8, name: 'Audited Workspace', kind: 'organization', role: 'read_only' },
        ],
      });
      if (url.includes('/files?path=')) return json({
        items: [{ name: 'report.pdf', path: 'report.pdf', kind: 'file', size: 1024, modified_at: new Date().toISOString() }],
      });
      return json({ status: 'ok' });
    });

    boot('/files');
    expect(await screen.findByText(/AUDITED WORKSPACE • READ-ONLY/i)).toBeTruthy();
    expect(await screen.findByText(/Viewing files in read-only mode/i)).toBeTruthy();
    // New folder and Upload buttons must NOT be present
    expect(screen.queryByRole('button', { name: /New folder/i })).toBeNull();
    expect(screen.queryByText(/Upload files/i)).toBeNull();
  });

  it('renders workspace access modal in Admin User Directory', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/me')) return json(owner);
      if (url.endsWith('/admin/users')) return json({
        items: [
          {
            id: 1,
            full_name: 'Server Owner',
            email: 'owner@example.test',
            username: 'owner',
            role: 'system_owner',
            is_verified: true,
            is_active: true,
            created_at: new Date().toISOString(),
            workspaces_count: 1,
            files_count: 2,
            storage_bytes: 1024,
          },
        ],
        total: 1,
      });
      if (url.includes('/admin/users/') && url.endsWith('/workspaces')) return json({
        items: [
          {
            workspace_id: 1,
            workspace_name: 'Engineering Workspace',
            workspace_kind: 'organization',
            is_member: true,
            role: 'member',
            is_owner: false,
          },
        ],
      });
      return json({ status: 'ok' });
    });

    boot('/admin/users');
    expect(await screen.findByRole('heading', { name: /User Management/i })).toBeTruthy();
    const wsBtn = await screen.findByRole('button', { name: /Workspaces/i });
    expect(wsBtn).toBeTruthy();
    await userEvent.click(wsBtn);
    expect(await screen.findByRole('heading', { name: /Workspace Access/i })).toBeTruthy();
    expect(await screen.findByText('Engineering Workspace')).toBeTruthy();
  });
});






