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

import React, { useEffect, useState } from 'react';
import {
  HardDrive,
  Folder,
  FolderPlus,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Plus,
  ChevronRight,
  X,
  Play,
  Trash2,
  Info,
  Server,
  Laptop,
  Terminal,
  Clock,
} from 'lucide-react';
import { request, post, put, del } from './api';

type StorageStatus = {
  current_location: {
    id: number;
    name: string;
    path: string;
    host_path?: string;
    mount_status?: string;
    is_default: boolean;
  };
  total_bytes: number | null;
  used_bytes: number | null;
  free_bytes: number | null;
  percent_used: number | null;
  readable: boolean;
  writable: boolean;
  status: string;
  health: 'healthy' | 'warning' | 'critical' | 'unknown';
  locations_count: number;
  helper_online?: boolean;
};

type StorageLocationItem = {
  id: number;
  name: string;
  root_key: string;
  relative_path: string;
  target_path: string;
  host_path?: string | null;
  mount_status: string;
  mount_type: string;
  is_default: boolean;
  status: string;
  total_bytes: number | null;
  used_bytes: number | null;
  free_bytes: number | null;
  percent_used: number | null;
  writable: boolean;
  readable: boolean;
  error?: string | null;
};

type HostBrowseResult = {
  current_path: string;
  parent_path: string | null;
  breadcrumbs: { name: string; path: string }[];
  folders: { name: string; path: string; writable: boolean }[];
  writable: boolean;
  error?: string;
};

type HostValidationResult = {
  valid: boolean;
  host_path: string;
  exists: boolean;
  is_dir: boolean;
  readable: boolean;
  writable: boolean;
  total_bytes?: number;
  free_bytes?: number;
  used_bytes?: number;
  percent_used?: number;
  error?: string | null;
};

type ContainerBrowseResult = {
  root_key: string;
  root_name: string;
  container_path: string;
  current_path: string;
  breadcrumbs: { name: string; path: string }[];
  folders: { name: string; path: string; can_write: boolean }[];
  can_write: boolean;
  status: string;
  total_bytes: number | null;
  free_bytes: number | null;
};

type TestCheck = {
  name: string;
  passed: boolean;
  detail: string;
};

type TestResult = {
  target: string;
  path: string;
  host_path?: string | null;
  status: string;
  healthy: boolean;
  total_bytes: number | null;
  free_bytes: number | null;
  used_bytes: number | null;
  percent_used: number | null;
  checks: TestCheck[];
};

export const formatBytes = (bytes: number | null | undefined): string => {
  if (bytes === null || bytes === undefined || isNaN(bytes)) return 'Unavailable';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};

export function StorageManagement({ isAdmin }: { isAdmin: boolean }) {
  const [status, setStatus] = useState<StorageStatus | null>(null);
  const [locations, setLocations] = useState<StorageLocationItem[]>([]);
  const [authorizedRoots, setAuthorizedRoots] = useState<{ key: string; name: string; container_path: string }[]>([]);
  const [helperOnline, setHelperOnline] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Modals state
  const [addOpen, setAddOpen] = useState(false);
  const [containerBrowseOpen, setContainerBrowseOpen] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [instructionModalPath, setInstructionModalPath] = useState<string | null>(null);

  // Restarting / Mount Progress State
  const [restartingModal, setRestartingModal] = useState<{
    active: boolean;
    locationName: string;
    hostPath: string;
    containerPath: string;
    stage: string;
  } | null>(null);

  // Add Location Form state
  const [addMode, setAddMode] = useState<'host' | 'container'>('host');
  const [newLocName, setNewLocName] = useState('');
  const [newLocHostPath, setNewLocHostPath] = useState('');
  const [newLocDefault, setNewLocDefault] = useState(false);
  const [newLocAutoMount, setNewLocAutoMount] = useState(true);
  const [addingBusy, setAddingBusy] = useState(false);

  // Host Browse in Add Modal state
  const [hostBrowseData, setHostBrowseData] = useState<HostBrowseResult | null>(null);
  const [hostBrowseLoading, setHostBrowseLoading] = useState(false);
  const [hostValidation, setHostValidation] = useState<HostValidationResult | null>(null);
  const [validatingHost, setValidatingHost] = useState(false);

  // Container Add state
  const [newLocRoot, setNewLocRoot] = useState('default');
  const [newLocPath, setNewLocPath] = useState('');
  const [newLocCustomPath, setNewLocCustomPath] = useState('');

  // Container Browse modal state
  const [browseRoot, setBrowseRoot] = useState('default');
  const [browsePath, setBrowsePath] = useState('');
  const [browseData, setBrowseData] = useState<ContainerBrowseResult | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [showNewFolderInput, setShowNewFolderInput] = useState(false);

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const statusRes = await request<StorageStatus>('/storage/status');
      setStatus(statusRes);
      setHelperOnline(!!statusRes.helper_online);

      if (isAdmin) {
        const locRes = await request<{
          items: StorageLocationItem[];
          authorized_roots: any[];
          helper_online?: boolean;
          helper_instructions?: string;
        }>('/storage/locations');
        setLocations(locRes.items || []);
        setAuthorizedRoots(locRes.authorized_roots || []);
        if (locRes.helper_online !== undefined) {
          setHelperOnline(locRes.helper_online);
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load storage details');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [isAdmin]);

  // Host Directory Browsing logic
  async function loadHostBrowse(path = '') {
    if (!helperOnline) return;
    setHostBrowseLoading(true);
    try {
      const res = await request<HostBrowseResult>(`/storage/host/browse?path=${encodeURIComponent(path)}`);
      setHostBrowseData(res);
    } catch (err: any) {
      console.warn('Host browse error:', err);
    } finally {
      setHostBrowseLoading(false);
    }
  }

  async function validateHostPath(path: string) {
    if (!path.trim()) return;
    setValidatingHost(true);
    try {
      const res = await post<HostValidationResult>('/storage/host/validate', { path: path.trim() });
      setHostValidation(res);
      if (res.valid && !newLocName.trim()) {
        const parts = res.host_path.split('/').filter(Boolean);
        const folderName = parts[parts.length - 1] || 'Storage';
        setNewLocName(folderName.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()));
      }
    } catch (err: any) {
      setHostValidation({
        valid: false,
        host_path: path,
        exists: false,
        is_dir: false,
        readable: false,
        writable: false,
        error: err.message || 'Path validation failed',
      });
    } finally {
      setValidatingHost(false);
    }
  }

  function handleSelectHostFolder(folderPath: string) {
    setNewLocHostPath(folderPath);
    validateHostPath(folderPath);
  }

  // Open Add modal and initialize host browser
  function handleOpenAddModal() {
    setAddOpen(true);
    setNewLocName('');
    setNewLocHostPath('/home/aswin/data-server');
    setHostValidation(null);
    setNewLocDefault(true);
    setNewLocAutoMount(true);
    if (helperOnline) {
      loadHostBrowse('/home/aswin');
      validateHostPath('/home/aswin/data-server');
    }
  }

  // Container Browser logic
  async function handleContainerBrowse(rootKey = browseRoot, path = browsePath) {
    setBrowseLoading(true);
    setError('');
    try {
      const res = await request<ContainerBrowseResult>(
        `/storage/browse?root_key=${encodeURIComponent(rootKey)}&path=${encodeURIComponent(path)}`
      );
      setBrowseData(res);
      setBrowseRoot(rootKey);
      setBrowsePath(path);
      setContainerBrowseOpen(true);
    } catch (err: any) {
      setError(err.message || 'Could not browse directory');
    } finally {
      setBrowseLoading(false);
    }
  }

  async function handleCreateContainerFolder() {
    if (!newFolderName.trim()) return;
    try {
      await post('/storage/mkdir', {
        root_key: browseRoot,
        path: browsePath,
        name: newFolderName.trim(),
      });
      setNewFolderName('');
      setShowNewFolderInput(false);
      handleContainerBrowse(browseRoot, browsePath);
      setSuccess(`Folder created successfully`);
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to create directory');
    }
  }

  async function handleTest(target: { location_id?: number; root_key?: string; relative_path?: string }) {
    setTestLoading(true);
    setError('');
    try {
      const res = await post<TestResult>('/storage/test', target);
      setTestResult(res);
    } catch (err: any) {
      setError(err.message || 'Storage verification failed');
    } finally {
      setTestLoading(false);
    }
  }

  async function handleSetDefault(id: number) {
    if (!confirm('Set this storage location as the default destination for future uploads?')) return;
    try {
      await put(`/storage/locations/${id}/default`);
      setSuccess('Default storage destination updated.');
      setTimeout(() => setSuccess(''), 3000);
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to set default location');
    }
  }

  async function handleDeleteLocation(id: number, name: string) {
    if (!confirm(`Remove storage location "${name}"? Files on the host will remain intact.`)) return;
    try {
      await del(`/storage/locations/${id}`);
      setSuccess(`Storage location "${name}" removed.`);
      setTimeout(() => setSuccess(''), 3000);
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to remove location');
    }
  }

  // Poll for reconnection when service is restarting
  async function pollForReconnection(targetName: string, hostPath: string) {
    setRestartingModal({
      active: true,
      locationName: targetName,
      hostPath,
      containerPath: `/srv/homeserver/${targetName.toLowerCase().replace(/[^a-z0-9_-]/g, '-')}`,
      stage: 'Configuring Docker Compose and recreating backend container...',
    });

    let attempts = 0;
    const maxAttempts = 35;
    const pollInterval = 1000;

    await new Promise((resolve) => setTimeout(resolve, 2500));

    const check = async () => {
      attempts++;
      try {
        setRestartingModal((prev) =>
          prev ? { ...prev, stage: `Reconnecting to backend service (attempt ${attempts}/${maxAttempts})...` } : null
        );
        const res = await request<StorageStatus>('/storage/status');
        if (res && res.status) {
          setRestartingModal((prev) =>
            prev ? { ...prev, stage: 'Verifying container bind mount permissions...' } : null
          );
          await loadData();
          setTimeout(() => {
            setRestartingModal(null);
            setSuccess(`Host storage "${targetName}" (${hostPath}) successfully mounted and ready!`);
            setTimeout(() => setSuccess(''), 4000);
          }, 800);
          return;
        }
      } catch (e) {
        // Still restarting
      }

      if (attempts < maxAttempts) {
        setTimeout(check, pollInterval);
      } else {
        setRestartingModal(null);
        setError('Mount configuration was applied, but backend reconnect timed out. Please refresh the page.');
        loadData();
      }
    };

    setTimeout(check, pollInterval);
  }

  // Trigger mount for an unmounted location
  async function handleMountLocation(loc: StorageLocationItem) {
    if (!loc.host_path) return;
    if (!helperOnline) {
      setInstructionModalPath(loc.host_path);
      return;
    }

    try {
      await post(`/storage/locations/${loc.id}/mount`, {});
      pollForReconnection(loc.name, loc.host_path);
    } catch (err: any) {
      setError(err.message || 'Failed to initiate mount operation');
    }
  }

  // Form submit for adding storage location
  async function handleAddLocationSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newLocName.trim()) return;

    setAddingBusy(true);
    setError('');

    try {
      if (addMode === 'host') {
        const targetHost = newLocHostPath.trim();
        if (!targetHost) {
          setError('Host directory path is required');
          setAddingBusy(false);
          return;
        }

        const res = await post<any>('/storage/locations', {
          name: newLocName.trim(),
          type: 'host_path',
          host_path: targetHost,
          is_default: newLocDefault,
          auto_mount: newLocAutoMount && helperOnline,
        });

        setAddOpen(false);

        if (res.restarting) {
          pollForReconnection(newLocName.trim(), targetHost);
        } else {
          setSuccess(res.message || 'Host storage location registered.');
          setTimeout(() => setSuccess(''), 4000);
          loadData();
        }
      } else {
        // Container pre-mounted directory
        await post('/storage/locations', {
          name: newLocName.trim(),
          type: 'mounted_dir',
          root_key: newLocRoot,
          relative_path: newLocPath.trim(),
          target_path: newLocCustomPath.trim(),
          is_default: newLocDefault,
        });
        setAddOpen(false);
        setSuccess('Storage location registered.');
        setTimeout(() => setSuccess(''), 3000);
        loadData();
      }
    } catch (err: any) {
      setError(err.message || 'Failed to add storage location');
    } finally {
      setAddingBusy(false);
    }
  }

  return (
    <div className="storage-management-wrapper">
      {error && (
        <div className="notice notice-error" role="alert" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="notice notice-success" role="alert" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle size={16} />
          <span>{success}</span>
        </div>
      )}

      {/* Host Helper Status Strip */}
      <section
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          background: helperOnline ? '#f0fdf4' : '#fffbeb',
          border: `1px solid ${helperOnline ? '#bbf7d0' : '#fde68a'}`,
          borderRadius: '8px',
          marginBottom: '18px',
          fontSize: '11px',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: helperOnline ? '#16a34a' : '#d97706',
              boxShadow: helperOnline ? '0 0 6px #16a34a' : 'none',
            }}
          />
          <div>
            <strong>Host Storage Helper: {helperOnline ? 'Active & Ready' : 'Offline / Standby'}</strong>
            <span style={{ color: '#6b7280', marginLeft: '8px' }}>
              {helperOnline
                ? 'Direct Ubuntu host folder selection and 1-click Docker mounts are enabled.'
                : 'Run helper daemon to browse host folders and auto-configure Docker mounts.'}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {!helperOnline && (
            <button
              className="button secondary"
              style={{ height: '26px', fontSize: '10px', padding: '0 8px' }}
              onClick={() => setInstructionModalPath('/home/aswin/data-server')}
            >
              <Terminal size={12} /> View Host Setup Command
            </button>
          )}
          <button
            className="button secondary"
            style={{ height: '26px', fontSize: '10px', padding: '0 8px' }}
            onClick={() => loadData()}
            disabled={loading}
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Check Status
          </button>
        </div>
      </section>

      {/* Primary Overview Cards */}
      <section className="stat-grid" style={{ marginBottom: '20px' }}>
        <article className="stat-card">
          <div className="stat-icon purple">
            <HardDrive size={19} />
          </div>
          <span>Total capacity</span>
          <strong>{status?.total_bytes ? formatBytes(status.total_bytes) : 'Unavailable'}</strong>
          <small>
            Active destination: <b>{status?.current_location?.name || 'Primary storage'}</b>
          </small>
        </article>

        <article className="stat-card">
          <div className="stat-icon blue">
            <HardDrive size={19} />
          </div>
          <span>Used space</span>
          <strong>
            {status?.used_bytes !== null && status?.used_bytes !== undefined
              ? `${formatBytes(status.used_bytes)} (${status.percent_used ?? 0}%)`
              : 'Unavailable'}
          </strong>
          <small>Files and server data</small>
        </article>

        <article className="stat-card">
          <div className="stat-icon green">
            <CheckCircle size={19} />
          </div>
          <span>Available space</span>
          <strong>{status?.free_bytes ? formatBytes(status.free_bytes) : 'Unavailable'}</strong>
          <small>
            Health:{' '}
            <b
              style={{
                color:
                  status?.health === 'healthy'
                    ? '#16a34a'
                    : status?.health === 'warning'
                    ? '#d97706'
                    : '#dc2626',
              }}
            >
              {status?.health?.toUpperCase() || 'UNKNOWN'}
            </b>
          </small>
        </article>
      </section>

      {/* Main Storage Management Card */}
      <section className="panel" style={{ marginBottom: '20px' }}>
        <div className="panel-heading" style={{ flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ flex: '1 1 300px' }}>
            <span className="eyebrow">STORAGE CONFIGURATION</span>
            <h2>Active Storage Destination</h2>
            <p>All file uploads and workspace storage are routed to this verified physical destination.</p>
          </div>

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              className="button secondary"
              type="button"
              onClick={() => handleTest({ location_id: status?.current_location?.id || 0 })}
              disabled={testLoading}
            >
              <Play size={14} /> {testLoading ? 'Testing…' : 'Test active storage'}
            </button>
            <button className="button secondary" type="button" onClick={() => loadData()} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
            {isAdmin && (
              <>
                <button
                  className="button secondary"
                  type="button"
                  onClick={() => handleContainerBrowse('default', '')}
                >
                  <Folder size={14} /> Browse locations
                </button>
                <button className="button primary" type="button" onClick={handleOpenAddModal}>
                  <Plus size={14} /> Add storage location
                </button>
              </>
            )}
          </div>
        </div>

        {/* Current Active Location Highlight */}
        <div
          style={{
            padding: '16px 20px',
            background: 'var(--bg-elevated, #f8f9fc)',
            borderRadius: '8px',
            border: '1px solid var(--border-color, #eaecf1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <span
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '8px',
                background: '#eef2ff',
                color: '#4f46e5',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <Server size={22} />
            </span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <strong style={{ fontSize: '14px' }}>{status?.current_location?.name || 'Primary storage'}</strong>
                <span className="role-pill" style={{ background: '#ecfdf5', color: '#065f46', fontWeight: 600 }}>
                  Active Default Destination
                </span>
              </div>
              <div style={{ display: 'flex', gap: '16px', marginTop: '4px', fontSize: '11px', color: '#6b7280', flexWrap: 'wrap' }}>
                <span>
                  Host Path: <code>{status?.current_location?.host_path || './data'}</code>
                </span>
                <span>
                  Container Mount: <code>{status?.current_location?.path || '/data'}</code>
                </span>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ textAlign: 'right' }}>
              <small style={{ display: 'block', fontSize: '10px', color: '#9ca3af' }}>MOUNT STATUS</small>
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: status?.writable ? '#16a34a' : '#dc2626',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                {status?.writable ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                {status?.writable ? 'Mounted & Writable' : 'Read-Only / Unmounted'}
              </span>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        {status?.percent_used !== null && status?.percent_used !== undefined && (
          <div style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '6px' }}>
              <span style={{ color: '#6b7280' }}>
                {formatBytes(status.used_bytes)} used of {formatBytes(status.total_bytes)}
              </span>
              <span style={{ fontWeight: 600 }}>{status.percent_used}% Used</span>
            </div>
            <div style={{ height: '7px', background: '#e5e7eb', borderRadius: '4px', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  width: `${Math.min(status.percent_used, 100)}%`,
                  background:
                    status.percent_used > 90 ? '#dc2626' : status.percent_used > 75 ? '#f59e0b' : '#4f46e5',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>
        )}
      </section>

      {/* Storage Locations Table (Admin) */}
      {isAdmin && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">STORAGE TOPOLOGY</span>
              <h2>Storage Locations</h2>
              <p>Physical host computer directories and container mount points configured for HomeServer.</p>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color, #e5e7eb)', textAlign: 'left', color: '#9ca3af' }}>
                  <th style={{ padding: '10px 12px' }}>LOCATION</th>
                  <th style={{ padding: '10px 12px' }}>HOST PATH</th>
                  <th style={{ padding: '10px 12px' }}>CONTAINER MOUNT</th>
                  <th style={{ padding: '10px 12px' }}>CAPACITY</th>
                  <th style={{ padding: '10px 12px' }}>STATUS</th>
                  <th style={{ padding: '10px 12px', textAlign: 'right' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {locations.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: '24px', textAlign: 'center', color: '#6b7280' }}>
                      No custom storage locations registered. Default <code>/data</code> is active.
                    </td>
                  </tr>
                ) : (
                  locations.map((loc) => {
                    const isWritable = loc.writable;

                    return (
                      <tr
                        key={loc.id}
                        style={{
                          borderBottom: '1px solid var(--border-color, #f3f4f6)',
                          background: loc.is_default ? 'rgba(79, 70, 229, 0.03)' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '12px', fontWeight: 600 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <HardDrive size={15} style={{ color: loc.is_default ? '#4f46e5' : '#9ca3af' }} />
                            <span>{loc.name}</span>
                            {loc.is_default && (
                              <span
                                style={{
                                  fontSize: '9px',
                                  background: '#e0e7ff',
                                  color: '#4338ca',
                                  padding: '2px 6px',
                                  borderRadius: '10px',
                                  fontWeight: 700,
                                }}
                              >
                                DEFAULT
                              </span>
                            )}
                          </div>
                        </td>
                        <td style={{ padding: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Laptop size={13} style={{ color: '#6366f1' }} />
                            <code>{loc.host_path || 'Internal volume'}</code>
                          </div>
                        </td>
                        <td style={{ padding: '12px', color: '#6b7280' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Server size={13} style={{ color: '#059669' }} />
                            <code>{loc.target_path || '/data'}</code>
                          </div>
                        </td>
                        <td style={{ padding: '12px' }}>
                          {loc.total_bytes ? (
                            <span>
                              {formatBytes(loc.free_bytes)} free of {formatBytes(loc.total_bytes)}
                            </span>
                          ) : (
                            <span style={{ color: '#9ca3af' }}>Unavailable</span>
                          )}
                        </td>
                        <td style={{ padding: '12px' }}>
                          {loc.mount_status === 'mounted_and_writable' ? (
                            <span
                              className="status-pill"
                              style={{ background: '#ecfdf5', color: '#065f46', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                            >
                              <CheckCircle size={11} /> Mounted & Writable
                            </span>
                          ) : loc.mount_status === 'mounted_read_only' ? (
                            <span
                              className="status-pill"
                              style={{ background: '#fffbeb', color: '#b45309', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                            >
                              <AlertCircle size={11} /> Read-Only
                            </span>
                          ) : loc.mount_status === 'unmounted' ? (
                            <span
                              className="status-pill"
                              style={{ background: '#fef2f2', color: '#991b1b', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                              title={loc.error || 'Requires Docker Compose bind mount'}
                            >
                              <Clock size={11} /> Unmounted (Host only)
                            </span>
                          ) : (
                            <span
                              className="status-pill"
                              style={{ background: '#fef2f2', color: '#991b1b' }}
                            >
                              {loc.status || 'Missing'}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                            {loc.mount_status === 'unmounted' ? (
                              <button
                                className="button primary"
                                style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                                onClick={() => handleMountLocation(loc)}
                                title="Mount this host path to the container"
                              >
                                Mount to Container
                              </button>
                            ) : (
                              <>
                                <button
                                  className="button secondary"
                                  style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                                  onClick={() => handleTest({ location_id: loc.id })}
                                  title="Test read and write permissions"
                                >
                                  <Play size={12} /> Test
                                </button>
                                <button
                                  className="button secondary"
                                  style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                                  onClick={() => handleContainerBrowse(loc.root_key, loc.relative_path)}
                                  title="Browse container folder contents"
                                >
                                  <Folder size={12} /> Browse
                                </button>
                                {!loc.is_default && isWritable && (
                                  <button
                                    className="button primary"
                                    style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                                    onClick={() => handleSetDefault(loc.id)}
                                    title="Set as default destination"
                                  >
                                    Set default
                                  </button>
                                )}
                              </>
                            )}
                            {!loc.is_default && (
                              <button
                                className="button secondary danger-action"
                                style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                                onClick={() => handleDeleteLocation(loc.id, loc.name)}
                                title="Remove location record"
                              >
                                <Trash2 size={12} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Restarting / Service Recreation Modal */}
      {restartingModal && (
        <div className="modal-backdrop" style={backdropStyle}>
          <div className="modal-content" style={{ ...modalContentStyle, maxWidth: '480px', textAlign: 'center' }}>
            <div style={{ display: 'grid', placeItems: 'center', marginBottom: '16px' }}>
              <div
                style={{
                  width: '54px',
                  height: '54px',
                  borderRadius: '50%',
                  background: '#eef2ff',
                  color: '#4f46e5',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <RefreshCw size={26} className="animate-spin" />
              </div>
            </div>

            <h3 style={{ margin: '0 0 8px', fontSize: '17px' }}>Applying Storage Mount</h3>
            <p style={{ color: '#4b5563', fontSize: '12px', margin: '0 0 16px', lineHeight: 1.5 }}>
              Attaching host folder <code>{restartingModal.hostPath}</code> as container mount{' '}
              <code>{restartingModal.containerPath}</code>.
            </p>

            <div
              style={{
                padding: '12px',
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                fontSize: '11px',
                color: '#334155',
                marginBottom: '16px',
                textAlign: 'left',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#4f46e5', fontWeight: 600 }}>
                <Clock size={14} />
                <span>Current Stage:</span>
              </div>
              <div style={{ marginTop: '4px' }}>{restartingModal.stage}</div>
            </div>

            <small style={{ color: '#94a3b8', fontSize: '10px' }}>
              Database, existing volumes, and unrelated containers remain untouched.
            </small>
          </div>
        </div>
      )}

      {/* Manual Mount Instructions Modal (when helper is offline) */}
      {instructionModalPath && (
        <div className="modal-backdrop" style={backdropStyle}>
          <div className="modal-content" style={{ ...modalContentStyle, maxWidth: '540px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <span className="eyebrow">HOST MOUNT SETUP</span>
                <h3 style={{ margin: 0, fontSize: '16px' }}>Mount Host Folder</h3>
              </div>
              <button className="icon-button" onClick={() => setInstructionModalPath(null)}>
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '12px', color: '#4b5563', lineHeight: 1.5, margin: '0 0 14px' }}>
              To attach <code>{instructionModalPath}</code> to the container, execute this command on your Ubuntu host terminal:
            </p>

            <div
              style={{
                background: '#0f172a',
                color: '#f8fafc',
                padding: '12px 14px',
                borderRadius: '6px',
                fontFamily: 'monospace',
                fontSize: '11px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
              }}
            >
              <code>./scripts/manage-storage.sh attach {instructionModalPath} --default</code>
            </div>

            <div
              style={{
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '6px',
                padding: '12px',
                fontSize: '11px',
                color: '#475569',
                lineHeight: 1.5,
                marginBottom: '16px',
              }}
            >
              <strong>Tip: Enable automatic 1-click mounting</strong>
              <p style={{ margin: '4px 0 0' }}>
                Run <code>./scripts/manage-storage.sh daemon-start</code> in your host terminal to enable instant browsing and mounting directly from the web browser.
              </p>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="button primary" onClick={() => setInstructionModalPath(null)}>
                Got it
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Test Access Diagnostics Modal */}
      {testResult && (
        <div className="modal-backdrop" style={backdropStyle}>
          <div className="modal-content" style={modalContentStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <span className="eyebrow">STORAGE VERIFICATION</span>
                <h2 style={{ margin: 0, fontSize: '17px' }}>Access Test: {testResult.target}</h2>
              </div>
              <button className="icon-button" onClick={() => setTestResult(null)} aria-label="Close modal">
                <X size={18} />
              </button>
            </div>

            <div style={{ padding: '12px', background: '#f9fafb', borderRadius: '8px', marginBottom: '16px', fontSize: '11px' }}>
              {testResult.host_path && (
                <div>
                  <strong>Host Path:</strong> <code>{testResult.host_path}</code>
                </div>
              )}
              <div style={{ marginTop: '4px' }}>
                <strong>Container Mount:</strong> <code>{testResult.path}</code>
              </div>
              <div style={{ marginTop: '4px' }}>
                <strong>Overall Status:</strong>{' '}
                <span style={{ color: testResult.healthy ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
                  {testResult.healthy ? 'PASSED & FULLY ACCESSIBLE' : 'ISSUES DETECTED'}
                </span>
              </div>
            </div>

            <div style={{ display: 'grid', gap: '8px', marginBottom: '18px' }}>
              {testResult.checks.map((chk, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 12px',
                    border: '1px solid #e5e7eb',
                    borderRadius: '6px',
                    background: chk.passed ? '#f0fdf4' : '#fef2f2',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {chk.passed ? <CheckCircle size={16} color="#16a34a" /> : <AlertCircle size={16} color="#dc2626" />}
                    <span style={{ fontWeight: 600, fontSize: '11px' }}>{chk.name}</span>
                  </div>
                  <small style={{ color: '#6b7280', fontSize: '10px' }}>{chk.detail}</small>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="button primary" onClick={() => setTestResult(null)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Storage Location Dialog */}
      {addOpen && (
        <div className="modal-backdrop" style={backdropStyle}>
          <div className="modal-content" style={{ ...modalContentStyle, maxWidth: '640px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <span className="eyebrow">STORAGE CONFIGURATION</span>
                <h2 style={{ margin: 0, fontSize: '18px' }}>Add Storage Location</h2>
              </div>
              <button className="icon-button" onClick={() => setAddOpen(false)} aria-label="Close dialog">
                <X size={18} />
              </button>
            </div>

            {/* Mode selection tabs */}
            <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb', marginBottom: '16px' }}>
              <button
                type="button"
                style={{
                  padding: '8px 14px',
                  border: 0,
                  borderBottom: addMode === 'host' ? '2px solid #4f46e5' : '2px solid transparent',
                  background: 'transparent',
                  fontWeight: 600,
                  fontSize: '11px',
                  color: addMode === 'host' ? '#4f46e5' : '#6b7280',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
                onClick={() => setAddMode('host')}
              >
                <Laptop size={14} /> Host Computer Folder (Recommended)
              </button>
              <button
                type="button"
                style={{
                  padding: '8px 14px',
                  border: 0,
                  borderBottom: addMode === 'container' ? '2px solid #4f46e5' : '2px solid transparent',
                  background: 'transparent',
                  fontWeight: 600,
                  fontSize: '11px',
                  color: addMode === 'container' ? '#4f46e5' : '#6b7280',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
                onClick={() => setAddMode('container')}
              >
                <Server size={14} /> Mounted Container Directory
              </button>
            </div>

            <form onSubmit={handleAddLocationSubmit} className="form-stack">
              {addMode === 'host' ? (
                <>
                  {/* Host Browser Component if Helper is Online */}
                  {helperOnline ? (
                    <div
                      style={{
                        background: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px',
                        padding: '12px',
                        marginBottom: '14px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 600, color: '#334155', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Folder size={14} color="#4f46e5" /> Browse Host Directories:
                        </span>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            type="button"
                            className="button secondary"
                            style={{ height: '24px', fontSize: '10px', padding: '0 6px' }}
                            onClick={() => loadHostBrowse('/home/aswin')}
                          >
                            Home
                          </button>
                          <button
                            type="button"
                            className="button secondary"
                            style={{ height: '24px', fontSize: '10px', padding: '0 6px' }}
                            onClick={() => handleSelectHostFolder('/home/aswin/data-server')}
                          >
                            Target: /home/aswin/data-server
                          </button>
                        </div>
                      </div>

                      {/* Breadcrumbs */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '11px',
                          padding: '6px 8px',
                          background: '#fff',
                          border: '1px solid #cbd5e1',
                          borderRadius: '4px',
                          marginBottom: '8px',
                          overflowX: 'auto',
                        }}
                      >
                        <span style={{ color: '#64748b' }}>Path:</span>
                        {hostBrowseData?.breadcrumbs.map((b, idx) => (
                          <span key={idx} style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                            <button
                              type="button"
                              style={{ border: 0, background: 'transparent', color: '#4f46e5', cursor: 'pointer', padding: 0 }}
                              onClick={() => loadHostBrowse(b.path)}
                            >
                              {b.name}
                            </button>
                            <span style={{ color: '#94a3b8' }}>/</span>
                          </span>
                        ))}
                      </div>

                      {/* Folder List */}
                      <div
                        style={{
                          maxHeight: '140px',
                          overflowY: 'auto',
                          background: '#fff',
                          border: '1px solid #cbd5e1',
                          borderRadius: '4px',
                        }}
                      >
                        {hostBrowseLoading ? (
                          <div style={{ padding: '20px', textAlign: 'center', fontSize: '11px', color: '#64748b' }}>
                            Loading host folders…
                          </div>
                        ) : hostBrowseData?.folders.length === 0 ? (
                          <div style={{ padding: '16px', textAlign: 'center', fontSize: '11px', color: '#94a3b8' }}>
                            No subfolders in this location
                          </div>
                        ) : (
                          hostBrowseData?.folders.map((fld) => (
                            <div
                              key={fld.path}
                              style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                padding: '6px 10px',
                                borderBottom: '1px solid #f1f5f9',
                                fontSize: '11px',
                                cursor: 'pointer',
                              }}
                              onClick={() => loadHostBrowse(fld.path)}
                              onMouseEnter={(e) => (e.currentTarget.style.background = '#f8fafc')}
                              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <Folder size={13} color="#4f46e5" />
                                <span>{fld.name}</span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <span style={{ fontSize: '9px', color: fld.writable ? '#16a34a' : '#dc2626' }}>
                                  {fld.writable ? 'Writable' : 'Read-only'}
                                </span>
                                <button
                                  type="button"
                                  className="button secondary"
                                  style={{ height: '20px', padding: '0 6px', fontSize: '9px' }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleSelectHostFolder(fld.path);
                                  }}
                                >
                                  Select
                                </button>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  ) : (
                    <div
                      style={{
                        background: '#fffbeb',
                        border: '1px solid #fde68a',
                        borderRadius: '6px',
                        padding: '12px',
                        fontSize: '11px',
                        marginBottom: '14px',
                      }}
                    >
                      <strong style={{ color: '#b45309' }}>Host Storage Helper is offline</strong>
                      <p style={{ margin: '4px 0 6px', color: '#78350f', lineHeight: 1.4 }}>
                        Run this command on your host to enable 1-click live folder browsing and automatic Docker Compose configuration:
                      </p>
                      <code style={{ background: '#fef3c7', padding: '3px 6px', borderRadius: '4px', display: 'inline-block' }}>
                        ./scripts/manage-storage.sh daemon-start
                      </code>
                    </div>
                  )}

                  <label className="field">
                    <span>Host Directory Path</span>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input
                        type="text"
                        placeholder="e.g. /home/aswin/data-server"
                        value={newLocHostPath}
                        onChange={(e) => {
                          setNewLocHostPath(e.target.value);
                          setHostValidation(null);
                        }}
                        required
                        style={{ flex: 1 }}
                      />
                      {helperOnline && (
                        <button
                          type="button"
                          className="button secondary"
                          style={{ height: '36px', fontSize: '11px' }}
                          onClick={() => validateHostPath(newLocHostPath)}
                          disabled={validatingHost}
                        >
                          {validatingHost ? 'Validating…' : 'Validate'}
                        </button>
                      )}
                    </div>
                  </label>

                  {/* Validation Feedback */}
                  {hostValidation && (
                    <div
                      style={{
                        padding: '10px 12px',
                        borderRadius: '6px',
                        fontSize: '11px',
                        background: hostValidation.valid ? '#f0fdf4' : '#fef2f2',
                        border: `1px solid ${hostValidation.valid ? '#bbf7d0' : '#fecaca'}`,
                        marginBottom: '12px',
                      }}
                    >
                      {hostValidation.valid ? (
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#16a34a', fontWeight: 600 }}>
                            <CheckCircle size={14} /> Directory verified on host computer
                          </div>
                          <div style={{ marginTop: '4px', color: '#4b5563' }}>
                            Capacity: {formatBytes(hostValidation.free_bytes)} free of {formatBytes(hostValidation.total_bytes)} • Writable: Yes
                          </div>
                        </div>
                      ) : (
                        <div style={{ color: '#dc2626' }}>
                          <AlertCircle size={14} style={{ display: 'inline', marginRight: '4px' }} />
                          {hostValidation.error || 'Invalid host path'}
                        </div>
                      )}
                    </div>
                  )}

                  <label className="field">
                    <span>Location Display Name</span>
                    <input
                      type="text"
                      placeholder="e.g. Data Server"
                      value={newLocName}
                      onChange={(e) => setNewLocName(e.target.value)}
                      required
                    />
                  </label>

                  {/* Container Mount Path Preview */}
                  <div
                    style={{
                      padding: '10px 12px',
                      background: '#f8fafc',
                      borderRadius: '6px',
                      border: '1px solid #e2e8f0',
                      fontSize: '11px',
                      color: '#475569',
                      marginBottom: '12px',
                    }}
                  >
                    <strong>Container Bind Mount Destination:</strong>
                    <div style={{ marginTop: '2px', color: '#059669' }}>
                      <code>
                        /srv/homeserver/{newLocName.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-') || 'storage'}
                      </code>
                    </div>
                  </div>

                  {helperOnline && (
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', cursor: 'pointer', marginBottom: '8px' }}>
                      <input
                        type="checkbox"
                        checked={newLocAutoMount}
                        onChange={(e) => setNewLocAutoMount(e.target.checked)}
                      />
                      <span>Automatically attach bind mount in Docker Compose and restart backend (~3s)</span>
                    </label>
                  )}

                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={newLocDefault}
                      onChange={(e) => setNewLocDefault(e.target.checked)}
                    />
                    <span>Set as active default storage destination for all new uploads</span>
                  </label>

                  <div
                    style={{
                      background: '#f1f5f9',
                      borderRadius: '6px',
                      padding: '10px 12px',
                      fontSize: '10px',
                      color: '#475569',
                      marginTop: '10px',
                      lineHeight: 1.4,
                    }}
                  >
                    <Info size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: '-2px' }} />
                    Docker compose configuration updates only the backend container. Database, existing files, and unrelated containers remain untouched.
                  </div>
                </>
              ) : (
                <>
                  <label className="field">
                    <span>Location Display Name</span>
                    <input
                      type="text"
                      placeholder="e.g. Media Vault"
                      value={newLocName}
                      onChange={(e) => setNewLocName(e.target.value)}
                      required
                    />
                  </label>

                  <label className="field">
                    <span>Authorized Storage Root</span>
                    <select value={newLocRoot} onChange={(e) => setNewLocRoot(e.target.value)}>
                      {authorizedRoots.map((r) => (
                        <option key={r.key} value={r.key}>
                          {r.name} ({r.container_path})
                        </option>
                      ))}
                      <option value="custom">Pre-mounted Custom Container Path</option>
                    </select>
                  </label>

                  {newLocRoot === 'custom' ? (
                    <label className="field">
                      <span>Pre-mounted Container Path</span>
                      <input
                        type="text"
                        placeholder="e.g. /srv/homeserver/my-volume"
                        value={newLocCustomPath}
                        onChange={(e) => setNewLocCustomPath(e.target.value)}
                        required
                      />
                      <small style={{ color: '#6b7280', fontSize: '10px' }}>
                        Must already be mounted inside the container via Docker Compose.
                      </small>
                    </label>
                  ) : (
                    <label className="field">
                      <span>Relative Subfolder (optional)</span>
                      <input
                        type="text"
                        placeholder="e.g. uploads or media"
                        value={newLocPath}
                        onChange={(e) => setNewLocPath(e.target.value)}
                      />
                    </label>
                  )}

                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={newLocDefault}
                      onChange={(e) => setNewLocDefault(e.target.checked)}
                    />
                    <span>Set as active default storage destination</span>
                  </label>
                </>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '16px' }}>
                <button type="button" className="button secondary" onClick={() => setAddOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="button primary" disabled={addingBusy}>
                  {addingBusy ? 'Processing…' : addMode === 'host' && helperOnline ? 'Mount & Add Location' : 'Register Location'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Container Directory Browser Modal */}
      {containerBrowseOpen && browseData && (
        <div className="modal-backdrop" style={backdropStyle}>
          <div className="modal-content" style={{ ...modalContentStyle, maxWidth: '680px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <span className="eyebrow">CONTAINER STORAGE BROWSER</span>
                <h2 style={{ margin: 0, fontSize: '17px' }}>Browse Storage Directory</h2>
              </div>
              <button className="icon-button" onClick={() => setContainerBrowseOpen(false)} aria-label="Close browse dialog">
                <X size={18} />
              </button>
            </div>

            {/* Root Selection & Breadcrumbs */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '10px 12px',
                background: '#f8f9fa',
                borderRadius: '7px',
                marginBottom: '14px',
                flexWrap: 'wrap',
              }}
            >
              <label style={{ fontSize: '11px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>Root:</span>
                <select
                  value={browseRoot}
                  onChange={(e) => handleContainerBrowse(e.target.value, '')}
                  style={{ height: '28px', fontSize: '11px', borderRadius: '4px' }}
                >
                  {authorizedRoots.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', flex: 1, minWidth: '150px' }}>
                <button
                  type="button"
                  style={{ background: 'transparent', border: 0, color: '#4f46e5', cursor: 'pointer', padding: 0 }}
                  onClick={() => handleContainerBrowse(browseRoot, '')}
                >
                  /
                </button>
                {browseData.breadcrumbs.map((crumb, idx) => (
                  <span key={idx} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <ChevronRight size={13} color="#9ca3af" />
                    <button
                      type="button"
                      style={{ background: 'transparent', border: 0, color: '#4f46e5', cursor: 'pointer', padding: 0 }}
                      onClick={() => handleContainerBrowse(browseRoot, crumb.path)}
                    >
                      {crumb.name}
                    </button>
                  </span>
                ))}
              </div>

              <button
                className="button secondary"
                style={{ height: '28px', padding: '0 8px', fontSize: '10px' }}
                onClick={() => setShowNewFolderInput(!showNewFolderInput)}
              >
                <FolderPlus size={13} /> New folder
              </button>
            </div>

            {/* Inline New Folder Input */}
            {showNewFolderInput && (
              <div
                style={{
                  display: 'flex',
                  gap: '8px',
                  marginBottom: '12px',
                  padding: '8px',
                  background: '#f0f4ff',
                  borderRadius: '6px',
                }}
              >
                <input
                  type="text"
                  placeholder="New folder name"
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  style={{ flex: 1, height: '32px', padding: '0 8px', fontSize: '11px', borderRadius: '4px', border: '1px solid #c7d2fe' }}
                />
                <button className="button primary" style={{ height: '32px', fontSize: '11px' }} onClick={handleCreateContainerFolder}>
                  Create
                </button>
                <button
                  className="button secondary"
                  style={{ height: '32px', fontSize: '11px' }}
                  onClick={() => setShowNewFolderInput(false)}
                >
                  Cancel
                </button>
              </div>
            )}

            {/* Folder Listing */}
            <div
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                maxHeight: '260px',
                overflowY: 'auto',
                marginBottom: '16px',
              }}
            >
              {browseLoading ? (
                <div style={{ padding: '30px', textAlign: 'center', color: '#6b7280', fontSize: '11px' }}>
                  Loading folder contents…
                </div>
              ) : browseData.folders.length === 0 ? (
                <div style={{ padding: '30px', textAlign: 'center', color: '#9ca3af', fontSize: '11px' }}>
                  <Folder size={24} style={{ margin: '0 auto 6px', display: 'block', opacity: 0.5 }} />
                  No subdirectories in this location.
                </div>
              ) : (
                browseData.folders.map((fld) => (
                  <div
                    key={fld.path}
                    onClick={() => handleContainerBrowse(browseRoot, fld.path)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      borderBottom: '1px solid #f3f4f6',
                      cursor: 'pointer',
                      fontSize: '11px',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = '#f9fafb')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Folder size={16} color="#4f46e5" />
                      <strong>{fld.name}</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#9ca3af' }}>
                      <span style={{ fontSize: '9px' }}>{fld.can_write ? 'Writable' : 'Read-only'}</span>
                      <ChevronRight size={14} />
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Selected Path & Bottom Actions */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingTop: '12px',
                borderTop: '1px solid #e5e7eb',
                flexWrap: 'wrap',
                gap: '10px',
              }}
            >
              <div style={{ fontSize: '11px' }}>
                <span style={{ color: '#6b7280' }}>Selected: </span>
                <code>{browseData.container_path}</code>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="button secondary"
                  onClick={() => handleTest({ root_key: browseRoot, relative_path: browsePath })}
                  disabled={testLoading}
                >
                  <Play size={13} /> Test access
                </button>
                <button className="button primary" onClick={() => setContainerBrowseOpen(false)}>
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const backdropStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(15, 23, 42, 0.55)',
  backdropFilter: 'blur(3px)',
  display: 'grid',
  placeItems: 'center',
  zIndex: 100,
  padding: '16px',
};

const modalContentStyle: React.CSSProperties = {
  background: 'var(--bg-surface, #fff)',
  borderRadius: '10px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
  width: '100%',
  maxWidth: '520px',
  padding: '24px',
  border: '1px solid var(--border-color, #e5e7eb)',
  maxHeight: '90vh',
  overflowY: 'auto',
};
