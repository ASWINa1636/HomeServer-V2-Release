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

import { useEffect, useState } from 'react';
import {
  Activity,
  HardDrive,
  Users,
  Shield,
  Server,
  Cpu,
  Clock,
  RefreshCw,
  Search,
  UserCheck,
  UserX,
  Trash2,
  Archive,
  Download,
  CheckCircle,
  AlertTriangle,
  FileText,
  X,
  Check,
  Folder
} from 'lucide-react';
import { request, post, put, del } from './api';
import { formatBytes } from './StorageManagement';

type AdminOverviewData = {
  server: {
    name: string;
    version: string;
    migration_version: string;
    python_version: string;
    hostname: string;
    environment: string;
    uptime_seconds: number;
    boot_time: string;
    checked_at: string;
  };
  health: {
    app: string;
    database: string;
    storage: string;
    overall: 'healthy' | 'degraded' | 'critical';
  };
  system: {
    memory: {
      total_bytes: number | null;
      used_bytes: number | null;
      available_bytes: number | null;
    };
    load_average: number[];
  };
  storage: {
    location_name: string;
    container_path: string;
    status: string;
    total_bytes: number | null;
    used_bytes: number | null;
    free_bytes: number | null;
    percent_used: number | null;
    writable: boolean;
    readable: boolean;
    total_files: number;
    total_file_bytes: number;
    largest_files: { id: number; path: string; size_bytes: number; modified_at: string | null }[];
  };
  users: {
    total: number;
    verified: number;
    active: number;
    suspended: number;
    roles: { owners: number; admins: number; members: number };
    pending_invitations: number;
    total_organizations: number;
    total_workspaces: number;
    registration_policy: string;
    recent_registrations: {
      id: number;
      full_name: string;
      email: string;
      username: string;
      role: string;
      is_verified: boolean;
      is_active: boolean;
      created_at: string | null;
    }[];
  };
  security: {
    active_sessions: number;
    recent_audit_events: {
      id: number;
      actor_user_id: number | null;
      action: string;
      target: string;
      created_at: string | null;
    }[];
  };
  network: {
    local_url: string;
    tailscale_configured: boolean;
    public_domain: string | null;
  };
};

type AdminUser = {
  id: number;
  full_name: string;
  email: string;
  username: string;
  role: string;
  is_verified: boolean;
  is_active: boolean;
  created_at: string | null;
  workspaces_count: number;
  files_count: number;
  storage_bytes: number;
};

type AuditItem = {
  id: number;
  actor_user_id: number | null;
  actor_email: string | null;
  action: string;
  target: string;
  created_at: string | null;
};

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  parts.push(`${m}m`);
  return parts.join(' ');
}

export function AdminOverview() {
  const [data, setData] = useState<AdminOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await request<AdminOverviewData>('/admin/overview');
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to load administrator data');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (loading && !data) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 10px', display: 'block' }} />
        <span>Gathering real server diagnostics…</span>
      </div>
    );
  }

  if (error && !data) {
    return <div className="notice notice-error">{error}</div>;
  }

  const memTotal = data?.system.memory.total_bytes;
  const memUsed = data?.system.memory.used_bytes;
  const memPercent = memTotal && memUsed ? Math.round((memUsed / memTotal) * 100) : null;

  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ADMINISTRATOR CONTROL CENTER</p>
          <h1>Server Administration</h1>
          <p className="page-description">
            Live operational telemetry, health verification, resource utilization, and access logs.
          </p>
        </div>
        <button className="button secondary" onClick={load} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh Telemetry
        </button>
      </div>

      {error && <div className="notice notice-error" style={{ marginBottom: '16px' }}>{error}</div>}

      {/* Top Telemetry Cards */}
      <section className="stat-grid" style={{ marginBottom: '20px' }}>
        <article className="stat-card">
          <div className="stat-icon green">
            <Activity size={19} />
          </div>
          <span>Server Health</span>
          <strong style={{ color: data?.health.overall === 'healthy' ? '#16a34a' : '#d97706' }}>
            {data?.health.overall.toUpperCase() || 'UNKNOWN'}
          </strong>
          <small>
            App: {data?.health.app} · DB: {data?.health.database}
          </small>
        </article>

        <article className="stat-card">
          <div className="stat-icon blue">
            <Clock size={19} />
          </div>
          <span>System Uptime</span>
          <strong>{data?.server.uptime_seconds ? formatUptime(data.server.uptime_seconds) : '—'}</strong>
          <small>Host: {data?.server.hostname}</small>
        </article>

        <article className="stat-card">
          <div className="stat-icon purple">
            <Cpu size={19} />
          </div>
          <span>Memory & Load</span>
          <strong>{memPercent !== null ? `${memPercent}% RAM` : 'Active'}</strong>
          <small>
            Load: {data?.system.load_average.map((n) => n.toFixed(2)).join(', ') || '0.00'}
          </small>
        </article>
      </section>

      {/* Grid: System & Storage Overview */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px', marginBottom: '20px' }}>
        {/* System & Runtime Specs */}
        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon lavender"><Server size={18} /></span>
            <div>
              <h2>Environment & Specs</h2>
              <p>Container runtime environment and database versions.</p>
            </div>
          </div>

          <div style={{ display: 'grid', gap: '10px', fontSize: '11px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Application Version</span>
              <strong>HomeServer V2 ({data?.server.version})</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Database Migration</span>
              <code>{data?.server.migration_version}</code>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Python Runtime</span>
              <span>Python {data?.server.python_version}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-light)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Container Hostname</span>
              <code>{data?.server.hostname}</code>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-muted)' }}>Active Sessions</span>
              <strong style={{ color: '#4f46e5' }}>{data?.security.active_sessions} authenticated</strong>
            </div>
          </div>
        </section>

        {/* Storage Telemetry */}
        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon mint"><HardDrive size={18} /></span>
            <div>
              <h2>Storage Utilization</h2>
              <p>Capacity and tracked file records.</p>
            </div>
          </div>

          <div style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '6px' }}>
              <span>{formatBytes(data?.storage.used_bytes)} Used</span>
              <span>{formatBytes(data?.storage.total_bytes)} Total ({data?.storage.percent_used}%)</span>
            </div>
            <div style={{ height: '7px', background: 'var(--border-color)', borderRadius: '4px', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  width: `${Math.min(data?.storage.percent_used || 0, 100)}%`,
                  background: (data?.storage.percent_used || 0) > 85 ? '#dc2626' : '#4f46e5',
                }}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gap: '8px', fontSize: '11px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Tracked Files</span>
              <strong>{data?.storage.total_files} files ({formatBytes(data?.storage.total_file_bytes)})</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Mount Path</span>
              <code>{data?.storage.container_path}</code>
            </div>
          </div>

          {data?.storage.largest_files && data.storage.largest_files.length > 0 && (
            <div style={{ marginTop: '14px', borderTop: '1px solid var(--border-light)', paddingTop: '10px' }}>
              <small style={{ fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase', fontSize: '9px' }}>
                Largest Stored Files
              </small>
              <div style={{ display: 'grid', gap: '6px', marginTop: '6px' }}>
                {data.storage.largest_files.map((lf) => (
                  <div key={lf.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '220px' }}>
                      {lf.path}
                    </span>
                    <strong style={{ color: 'var(--text-muted)' }}>{formatBytes(lf.size_bytes)}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Grid: Users & Security Telemetry */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>
        {/* User Breakdown */}
        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon peach"><Users size={18} /></span>
            <div>
              <h2>User Accounts</h2>
              <p>System registration and role distribution.</p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', textAlign: 'center', marginBottom: '16px' }}>
            <div style={{ background: 'var(--bg-elevated)', padding: '10px', borderRadius: '6px' }}>
              <strong style={{ fontSize: '16px', display: 'block' }}>{data?.users.total}</strong>
              <small style={{ fontSize: '9px', color: 'var(--text-muted)' }}>TOTAL USERS</small>
            </div>
            <div style={{ background: 'var(--bg-elevated)', padding: '10px', borderRadius: '6px' }}>
              <strong style={{ fontSize: '16px', display: 'block', color: '#16a34a' }}>{data?.users.active}</strong>
              <small style={{ fontSize: '9px', color: 'var(--text-muted)' }}>ACTIVE</small>
            </div>
            <div style={{ background: 'var(--bg-elevated)', padding: '10px', borderRadius: '6px' }}>
              <strong style={{ fontSize: '16px', display: 'block', color: '#6366f1' }}>{data?.users.total_organizations}</strong>
              <small style={{ fontSize: '9px', color: 'var(--text-muted)' }}>ORGS</small>
            </div>
          </div>

          <div style={{ fontSize: '11px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-light)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Owners / Admins</span>
              <strong>{data?.users.roles.owners} Owners · {data?.users.roles.admins} Admins</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-light)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Pending Invitations</span>
              <span>{data?.users.pending_invitations}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
              <span style={{ color: 'var(--text-muted)' }}>Registration Policy</span>
              <strong style={{ textTransform: 'capitalize' }}>{data?.users.registration_policy.replace('_', ' ')}</strong>
            </div>
          </div>
        </section>

        {/* Security & Audit Feed */}
        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon lavender"><Shield size={18} /></span>
            <div>
              <h2>Recent Security Audit Events</h2>
              <p>Administrative and security changes.</p>
            </div>
          </div>

          <div style={{ display: 'grid', gap: '8px' }}>
            {data?.security.recent_audit_events.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-subtle)', fontSize: '11px' }}>
                No audit events recorded yet.
              </div>
            ) : (
              data?.security.recent_audit_events.map((ev) => (
                <div
                  key={ev.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    background: 'var(--bg-elevated)',
                    fontSize: '11px',
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, color: '#4f46e5' }}>{ev.action}</span>
                    {ev.target && <span style={{ color: 'var(--text-muted)', marginLeft: '6px' }}>({ev.target})</span>}
                  </div>
                  <small style={{ color: 'var(--text-subtle)', fontSize: '9px' }}>
                    {ev.created_at ? new Date(ev.created_at).toLocaleTimeString() : ''}
                  </small>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [selectedUserForWs, setSelectedUserForWs] = useState<AdminUser | null>(null);
  const [userWorkspaces, setUserWorkspaces] = useState<any[]>([]);
  const [wsLoading, setWsLoading] = useState(false);
  const [wsMessage, setWsMessage] = useState('');
  const [wsError, setWsError] = useState('');

  async function loadUsers() {
    setLoading(true);
    setError('');
    try {
      const res = await request<{ items: AdminUser[] }>('/admin/users');
      setUsers(res.items || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load user list');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  async function openWorkspaceModal(u: AdminUser) {
    setSelectedUserForWs(u);
    setWsLoading(true);
    setWsError('');
    setWsMessage('');
    try {
      const res = await request<{ items: any[] }>(`/admin/users/${u.id}/workspaces`);
      setUserWorkspaces(res.items || []);
    } catch (err: any) {
      setWsError(err.message || 'Failed to load user workspaces');
    } finally {
      setWsLoading(false);
    }
  }

  async function updateUserWorkspaceRole(workspaceId: number, newRole: string) {
    if (!selectedUserForWs) return;
    setWsError('');
    setWsMessage('');
    try {
      const res = await put<{ role: string | null }>(`/admin/users/${selectedUserForWs.id}/workspaces/${workspaceId}`, { role: newRole });
      setWsMessage(`Updated access to ${res.role ? res.role.replace('_', ' ') : 'None'}.`);
      setTimeout(() => setWsMessage(''), 3000);
      const refreshed = await request<{ items: any[] }>(`/admin/users/${selectedUserForWs.id}/workspaces`);
      setUserWorkspaces(refreshed.items || []);
      loadUsers();
    } catch (err: any) {
      setWsError(err.message || 'Failed to update workspace access');
    }
  }

  async function toggleStatus(user: AdminUser) {
    const action = user.is_active ? 'suspend' : 'reactivate';
    if (!confirm(`Are you sure you want to ${action} user "${user.email}"?`)) return;
    try {
      await put(`/admin/users/${user.id}/status`, { is_active: !user.is_active });
      setMessage(`Account status updated for ${user.email}.`);
      setTimeout(() => setMessage(''), 3000);
      loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to update user status');
    }
  }

  async function toggleRole(user: AdminUser) {
    const newRole = user.role === 'system_admin' ? 'member' : 'system_admin';
    if (!confirm(`Change role of "${user.email}" to ${newRole.replace('_', ' ')}?`)) return;
    try {
      await put(`/admin/users/${user.id}/role`, { role: newRole });
      setMessage(`Role updated to ${newRole} for ${user.email}.`);
      setTimeout(() => setMessage(''), 3000);
      loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to update user role');
    }
  }

  async function removeUser(user: AdminUser) {
    if (!confirm(`Permanently remove user "${user.email}"? All personal files will be detached.`)) return;
    try {
      await del(`/admin/users/${user.id}`);
      setMessage(`User ${user.email} removed.`);
      setTimeout(() => setMessage(''), 3000);
      loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to remove user');
    }
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ACCESS & PRIVILEGES</p>
          <h1>User Management</h1>
          <p className="page-description">
            Audit user roles, personal storage quotas, account statuses, and system permissions.
          </p>
        </div>
        <button className="button secondary" onClick={loadUsers} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="notice notice-info" style={{ marginBottom: '16px', fontSize: '11px', display: 'flex', gap: '8px', alignItems: 'center' }}>
        <Shield size={16} />
        <div>
          <strong>Role Architecture:</strong> <b>Server Role</b> controls server administration (backups, user management, audit logs, network). <b>Workspace Role</b> (Owner, Workspace Admin, Member, Read-Only) is managed per workspace to control file upload, folder creation, and editing permissions.
        </div>
      </div>

      {error && <div className="notice notice-error" style={{ marginBottom: '16px' }}>{error}</div>}
      {message && <div className="notice notice-success" style={{ marginBottom: '16px' }}>{message}</div>}

      <section className="panel" style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-subtle)' }}>
              <th style={{ padding: '10px 12px' }}>USER</th>
              <th style={{ padding: '10px 12px' }}>SERVER ROLE</th>
              <th style={{ padding: '10px 12px' }}>STATUS</th>
              <th style={{ padding: '10px 12px' }}>STORAGE USAGE</th>
              <th style={{ padding: '10px 12px' }}>JOINED</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                <td style={{ padding: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className="profile-avatar">{u.full_name.charAt(0).toUpperCase()}</span>
                    <div>
                      <strong>{u.full_name}</strong>
                      <small style={{ display: 'block', color: 'var(--text-muted)' }}>{u.email}</small>
                    </div>
                  </div>
                </td>
                <td style={{ padding: '12px' }}>
                  <span className="role-pill">{u.role.replace('_', ' ')}</span>
                </td>
                <td style={{ padding: '12px' }}>
                  <span
                    className="status-pill"
                    style={{
                      background: u.is_active ? '#ecfdf5' : '#fef2f2',
                      color: u.is_active ? '#065f46' : '#991b1b',
                    }}
                  >
                    {u.is_active ? 'Active' : 'Suspended'}
                  </span>
                </td>
                <td style={{ padding: '12px' }}>
                  <span>{formatBytes(u.storage_bytes)}</span>
                  <small style={{ display: 'block', color: 'var(--text-subtle)', fontSize: '9px' }}>
                    {u.files_count} files
                  </small>
                </td>
                <td style={{ padding: '12px', color: 'var(--text-muted)' }}>
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td style={{ padding: '12px', textAlign: 'right' }}>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                    <button
                      className="button secondary"
                      style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                      onClick={() => openWorkspaceModal(u)}
                      title="Manage Workspace Permissions"
                    >
                      <Folder size={12} style={{ marginRight: '4px' }} /> Workspaces
                    </button>
                    {u.role !== 'system_owner' && (
                      <>
                        <button
                          className="button secondary"
                          style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                          onClick={() => toggleRole(u)}
                          title="Promote or Demote Role"
                        >
                          {u.role === 'system_admin' ? 'Demote to Member' : 'Promote to Admin'}
                        </button>
                        <button
                          className="button secondary"
                          style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                          onClick={() => toggleStatus(u)}
                          title={u.is_active ? 'Suspend Account' : 'Reactivate Account'}
                        >
                          {u.is_active ? <UserX size={13} /> : <UserCheck size={13} />}
                        </button>
                        <button
                          className="button secondary danger-action"
                          style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                          onClick={() => removeUser(u)}
                          title="Delete User"
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {selectedUserForWs && (
        <div className="modal-backdrop" onClick={() => setSelectedUserForWs(null)}>
          <div className="modal-card" style={{ maxWidth: '640px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '15px' }}>Workspace Access</h3>
                <small style={{ color: 'var(--text-muted)' }}>
                  {selectedUserForWs.full_name} ({selectedUserForWs.email})
                </small>
              </div>
              <button className="icon-button" onClick={() => setSelectedUserForWs(null)} aria-label="Close modal">
                <X size={16} />
              </button>
            </div>

            <p style={{ fontSize: '11px', color: 'var(--text-subtle)', marginBottom: '12px' }}>
              Grant or revoke write and admin permissions for each workspace. Workspace Admin and Member roles have upload and file management rights. Read-Only restricts users to browsing and downloading.
            </p>

            {wsError && <div className="notice notice-error" style={{ marginBottom: '10px', fontSize: '11px' }}>{wsError}</div>}
            {wsMessage && <div className="notice notice-success" style={{ marginBottom: '10px', fontSize: '11px' }}>{wsMessage}</div>}

            {wsLoading ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                Loading workspaces…
              </div>
            ) : userWorkspaces.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                No workspaces configured on server.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', marginBottom: '16px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-subtle)' }}>
                    <th style={{ padding: '8px' }}>WORKSPACE</th>
                    <th style={{ padding: '8px' }}>TYPE</th>
                    <th style={{ padding: '8px' }}>CURRENT ACCESS</th>
                    <th style={{ padding: '8px', textAlign: 'right' }}>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {userWorkspaces.map((ws) => (
                    <tr key={ws.workspace_id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: '8px' }}>
                        <strong>{ws.workspace_name}</strong>
                      </td>
                      <td style={{ padding: '8px' }}>
                        <span style={{ textTransform: 'capitalize' }}>{ws.workspace_kind}</span>
                      </td>
                      <td style={{ padding: '8px' }}>
                        {ws.is_owner ? (
                          <span className="role-pill">Owner</span>
                        ) : ws.role ? (
                          <span className="role-pill">{ws.role.replace('_', ' ')}</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>None</span>
                        )}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right' }}>
                        {ws.is_owner ? (
                          <small style={{ color: 'var(--text-muted)' }}>Workspace Owner</small>
                        ) : (
                          <select
                            value={ws.role || 'none'}
                            onChange={(e) => updateUserWorkspaceRole(ws.workspace_id, e.target.value)}
                            style={{ padding: '4px 8px', fontSize: '11px', borderRadius: '4px', border: '1px solid var(--border-color)' }}
                            aria-label={`Role for ${ws.workspace_name}`}
                          >
                            {ws.workspace_kind === 'organization' && (
                              <option value="organization_admin">Workspace Admin</option>
                            )}
                            <option value="member">Member (Write access)</option>
                            <option value="read_only">Read-only (Browse only)</option>
                            <option value="none">No Access (Remove)</option>
                          </select>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="button secondary" onClick={() => setSelectedUserForWs(null)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function AdminAuditLogs() {
  const [logs, setLogs] = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  async function loadLogs(filter = search) {
    setLoading(true);
    setError('');
    try {
      const url = filter ? `/admin/audit?action=${encodeURIComponent(filter)}` : '/admin/audit';
      const res = await request<{ items: AuditItem[] }>(url);
      setLogs(res.items || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLogs('');
  }, []);

  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SECURITY & COMPLIANCE</p>
          <h1>Audit Logs</h1>
          <p className="page-description">
            Chronological audit trail of all security-sensitive operations on the server.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              loadLogs(search);
            }}
            style={{ display: 'flex', gap: '6px' }}
          >
            <div className="search-box">
              <Search size={14} />
              <input
                type="text"
                placeholder="Filter action (e.g. storage, user)"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button className="button secondary" type="submit">
              Search
            </button>
          </form>
          <button className="button secondary" onClick={() => loadLogs(search)} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {error && <div className="notice notice-error" style={{ marginBottom: '16px' }}>{error}</div>}

      <section className="panel" style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-subtle)' }}>
              <th style={{ padding: '10px 12px' }}>TIMESTAMP</th>
              <th style={{ padding: '10px 12px' }}>ACTION</th>
              <th style={{ padding: '10px 12px' }}>ACTOR</th>
              <th style={{ padding: '10px 12px' }}>TARGET RESOURCE</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  No matching audit records.
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                  <td style={{ padding: '12px', color: 'var(--text-muted)' }}>
                    {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                  </td>
                  <td style={{ padding: '12px' }}>
                    <span
                      style={{
                        padding: '3px 7px',
                        borderRadius: '4px',
                        background: 'var(--bg-elevated)',
                        fontWeight: 600,
                        color: log.action.includes('delete') || log.action.includes('suspend') ? '#dc2626' : '#4f46e5',
                      }}
                    >
                      {log.action}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    {log.actor_email || (log.actor_user_id ? `User #${log.actor_user_id}` : 'System')}
                  </td>
                  <td style={{ padding: '12px', color: 'var(--text-muted)' }}>
                    <code>{log.target || '—'}</code>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

type BackupItem = {
  backup_id: string;
  filename: string;
  created_at: string;
  size_bytes: number;
  sha256: string;
  status: string;
  table_counts?: Record<string, number>;
  files_count?: number;
  files_bytes?: number;
};

export function AdminBackups() {
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [creating, setCreating] = useState(false);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifiedMap, setVerifiedMap] = useState<Record<string, boolean>>({});
  const [runbookContent, setRunbookContent] = useState<string | null>(null);

  async function loadBackups() {
    setLoading(true);
    setError('');
    try {
      const res = await request<{ items: BackupItem[] }>('/backups');
      setBackups(res.items || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load backups');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBackups();
  }, []);

  async function handleCreateBackup() {
    setCreating(true);
    setError('');
    setNotice('');
    try {
      const res = await post<BackupItem>('/backups/create');
      setNotice(`Backup ${res.filename} created and integrity verified successfully!`);
      await loadBackups();
    } catch (err: any) {
      setError(err.message || 'Backup creation failed');
    } finally {
      setCreating(false);
    }
  }

  async function handleVerify(id: string) {
    setVerifyingId(id);
    setError('');
    try {
      const res = await post<{ valid: boolean }>(`/backups/${id}/verify`);
      if (res.valid) {
        setVerifiedMap((prev) => ({ ...prev, [id]: true }));
        setNotice(`Backup ${id} passed SHA-256 integrity verification.`);
      }
    } catch (err: any) {
      setError(err.message || 'Verification failed');
    } finally {
      setVerifyingId(null);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm(`Delete backup '${id}'? This cannot be undone.`)) return;
    try {
      await del(`/backups/${id}`);
      await loadBackups();
      setNotice('Backup deleted.');
    } catch (err: any) {
      setError(err.message || 'Failed to delete backup');
    }
  }

  async function openRunbook() {
    try {
      const res = await request<{ runbook: string }>('/backups/runbook');
      setRunbookContent(res.runbook);
    } catch (err: any) {
      setError(err.message || 'Failed to load restore runbook');
    }
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DATA PROTECTION & DISASTER RECOVERY</p>
          <h1>Backup & Recovery</h1>
          <p className="page-description">
            Complete snapshots containing database records, user files, and configuration with SHA-256 integrity verification.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="button secondary" onClick={openRunbook}>
            <FileText size={15} /> Restore Runbook
          </button>
          <button className="button primary" onClick={handleCreateBackup} disabled={creating}>
            <Archive size={15} className={creating ? 'animate-spin' : ''} /> {creating ? 'Creating Archive…' : 'Create Backup'}
          </button>
        </div>
      </div>

      {notice && <div className="notice notice-success" style={{ marginBottom: '16px' }}>{notice}</div>}
      {error && <div className="notice notice-error" style={{ marginBottom: '16px' }}>{error}</div>}

      <section className="panel" style={{ overflowX: 'auto' }}>
        <div className="panel-heading">
          <div>
            <h2>Backup Archive History</h2>
            <p>Stored locally in container storage under <code>/data/backups/</code>.</p>
          </div>
          <span className="count-badge">{backups.length} snapshots</span>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-subtle)' }}>
              <th style={{ padding: '10px 12px' }}>ARCHIVE FILENAME</th>
              <th style={{ padding: '10px 12px' }}>CREATED</th>
              <th style={{ padding: '10px 12px' }}>SIZE</th>
              <th style={{ padding: '10px 12px' }}>SHA-256 CHECKSUM</th>
              <th style={{ padding: '10px 12px' }}>INTEGRITY</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {backups.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {loading ? 'Loading backup archives…' : 'No backups found. Click "Create Backup" above to generate your first full archive.'}
                </td>
              </tr>
            ) : (
              backups.map((b) => (
                <tr key={b.backup_id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                  <td style={{ padding: '12px' }}>
                    <strong>{b.filename}</strong>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                      {b.files_count !== undefined ? `${b.files_count} files` : ''}
                    </div>
                  </td>
                  <td style={{ padding: '12px', color: 'var(--text-muted)' }}>
                    {b.created_at ? new Date(b.created_at).toLocaleString() : '—'}
                  </td>
                  <td style={{ padding: '12px' }}>
                    {formatBytes(b.size_bytes)}
                  </td>
                  <td style={{ padding: '12px' }}>
                    <code style={{ fontSize: '10px', padding: '2px 4px', background: 'var(--bg-elevated)', borderRadius: '3px' }}>
                      {b.sha256 ? `${b.sha256.slice(0, 12)}…${b.sha256.slice(-8)}` : '—'}
                    </code>
                  </td>
                  <td style={{ padding: '12px' }}>
                    {verifiedMap[b.backup_id] ? (
                      <span className="status-pill" style={{ color: '#16a34a' }}>
                        <Check size={12} /> Verified
                      </span>
                    ) : (
                      <button
                        className="button secondary"
                        style={{ padding: '3px 8px', fontSize: '10px' }}
                        onClick={() => handleVerify(b.backup_id)}
                        disabled={verifyingId === b.backup_id}
                      >
                        {verifyingId === b.backup_id ? 'Checking…' : 'Verify Integrity'}
                      </button>
                    )}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                      <a
                        className="button secondary"
                        style={{ padding: '4px 8px', fontSize: '11px' }}
                        href={`/api/v1/backups/${b.backup_id}/download`}
                        title="Download archive"
                      >
                        <Download size={13} /> Download
                      </a>
                      <button
                        className="button text danger-action"
                        style={{ padding: '4px 6px' }}
                        onClick={() => handleDelete(b.backup_id)}
                        title="Delete backup"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {/* Restore Runbook Modal */}
      {runbookContent && (
        <div className="modal-backdrop" onClick={() => setRunbookContent(null)}>
          <div className="modal-card" style={{ maxWidth: '680px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FileText size={18} /> Disaster Recovery Restore Runbook
              </h3>
              <button className="icon-button" onClick={() => setRunbookContent(null)}><X size={16} /></button>
            </div>
            <pre style={{
              background: 'var(--bg-app)',
              padding: '16px',
              borderRadius: '8px',
              overflowX: 'auto',
              fontSize: '11px',
              border: '1px solid var(--border-color)',
              lineHeight: 1.5,
              maxHeight: '440px',
              whiteSpace: 'pre-wrap',
            }}>
              {runbookContent}
            </pre>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '14px' }}>
              <button className="button primary" onClick={() => setRunbookContent(null)}>
                Close Runbook
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

type DiagnosticCheck = {
  name: string;
  category: string;
  status: 'healthy' | 'warning' | 'critical' | 'neutral';
  detail: string;
  corrective_action: string | null;
};

type DiagnosticData = {
  overall_status: 'healthy' | 'warning' | 'critical';
  checks: DiagnosticCheck[];
  checked_at: string;
};

export function AdminDiagnostics() {
  const [data, setData] = useState<DiagnosticData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function runChecks() {
    setLoading(true);
    setError('');
    try {
      const res = await request<DiagnosticData>('/admin/diagnostics');
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to run diagnostics');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    runChecks();
  }, []);

  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SYSTEM HEALTH & VERIFICATION</p>
          <h1>System Diagnostics</h1>
          <p className="page-description">
            Live operational verification of backend API, PostgreSQL database, storage writability, SMTP mail, and remote network posture.
          </p>
        </div>
        <button className="button secondary" onClick={runChecks} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Run Diagnostics
        </button>
      </div>

      {error && <div className="notice notice-error" style={{ marginBottom: '16px' }}>{error}</div>}

      {/* Top Banner Status */}
      <section className="panel" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {data?.overall_status === 'healthy' ? (
              <span className="quick-icon mint"><CheckCircle size={24} style={{ color: '#16a34a' }} /></span>
            ) : data?.overall_status === 'warning' ? (
              <span className="quick-icon peach"><AlertTriangle size={24} style={{ color: '#d97706' }} /></span>
            ) : (
              <span className="quick-icon lavender"><AlertTriangle size={24} style={{ color: '#dc2626' }} /></span>
            )}
            <div>
              <h2 style={{ margin: 0, textTransform: 'uppercase' }}>
                Overall Health: {data?.overall_status || 'CHECKING…'}
              </h2>
              <p style={{ margin: '3px 0 0', color: 'var(--text-muted)', fontSize: '12px' }}>
                Last evaluated: {data?.checked_at ? new Date(data.checked_at).toLocaleTimeString() : '—'}
              </p>
            </div>
          </div>
          <span className={data?.overall_status === 'healthy' ? 'status-pill' : 'not-connected'}>
            {data?.overall_status === 'healthy' ? <><i className="online-dot" /> All Systems Nominal</> : 'Attention Needed'}
          </span>
        </div>
      </section>

      {/* Checks Grid */}
      <div style={{ display: 'grid', gap: '12px' }}>
        {data?.checks.map((chk, idx) => {
          const isHealthy = chk.status === 'healthy';
          const isWarn = chk.status === 'warning';
          return (
            <section
              key={idx}
              className="panel"
              style={{
                borderLeft: `4px solid ${isHealthy ? '#16a34a' : isWarn ? '#d97706' : '#dc2626'}`,
                padding: '16px 20px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: isHealthy ? '#16a34a' : isWarn ? '#d97706' : '#dc2626', fontWeight: 'bold' }}>
                      {isHealthy ? '✓' : '!'}
                    </span>
                    <h3 style={{ margin: 0, fontSize: '13px' }}>{chk.name}</h3>
                    <span style={{ fontSize: '10px', textTransform: 'uppercase', padding: '1px 6px', borderRadius: '4px', background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                      {chk.category}
                    </span>
                  </div>
                  <p style={{ margin: '6px 0 0', fontSize: '12px', color: 'var(--text-main)' }}>
                    {chk.detail}
                  </p>
                  {chk.corrective_action && (
                    <div style={{ marginTop: '8px', fontSize: '11px', color: '#d97706', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <AlertTriangle size={13} />
                      <strong>Corrective Action:</strong> {chk.corrective_action}
                    </div>
                  )}
                </div>
                <span className={isHealthy ? 'status-pill' : 'not-connected'} style={{ textTransform: 'capitalize' }}>
                  {chk.status}
                </span>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
