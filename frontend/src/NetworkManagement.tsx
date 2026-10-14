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
import QRCode from 'qrcode';
import {
  Network,
  Check,
  Copy,
  RefreshCw,
  QrCode,
  Globe,
  Server,
  FileCode,
  X,
  ExternalLink,
  Users
} from 'lucide-react';
import { request, post } from './api';

type CheckItem = {
  name: string;
  passed: boolean;
  detail: string;
};

type TailscaleData = {
  status: string;
  is_configured: boolean;
  auto_detected?: boolean;
  device_name: string | null;
  target: string | null;
  port: number;
  full_url: string | null;
  last_checked: string | null;
  checks: CheckItem[];
  error?: string | null;
};

type PublicData = {
  is_configured: boolean;
  domain: string | null;
  method: 'caddy' | 'cloudflare' | 'external_proxy';
  status: string;
  public_url: string | null;
  last_checked: string | null;
  checks: CheckItem[];
  security: {
    cookie_secure: boolean;
    trusted_hosts: string;
    database_isolated: boolean;
  };
};

export function NetworkManagement({ isAdmin }: { isAdmin: boolean }) {
  const [tailscale, setTailscale] = useState<TailscaleData | null>(null);
  const [publicData, setPublicData] = useState<PublicData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Modals
  const [qrModalUrl, setQrModalUrl] = useState<string | null>(null);
  const [qrSvg, setQrSvg] = useState<string>('');
  const [showTsModal, setShowTsModal] = useState(false);
  const [showPubModal, setShowPubModal] = useState(false);
  const [showConfigSnippet, setShowConfigSnippet] = useState<{ title: string; content: string } | null>(null);
  const [showTsInviteModal, setShowTsInviteModal] = useState(false);
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [inviteWsId, setInviteWsId] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviteGeneratedUrl, setInviteGeneratedUrl] = useState('');
  const [inviteQrDataUrl, setInviteQrDataUrl] = useState('');
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const [inviteSuccessMsg, setInviteSuccessMsg] = useState('');

  // Tailscale Form
  const [tsTarget, setTsTarget] = useState('');
  const [tsDevice, setTsDevice] = useState('');
  const [tsPort, setTsPort] = useState(8081);
  const [tsBusy, setTsBusy] = useState(false);
  const [tsError, setTsError] = useState('');

  // Public Form
  const [pubDomain, setPubDomain] = useState('');
  const [pubMethod, setPubMethod] = useState<'caddy' | 'cloudflare' | 'external_proxy'>('caddy');
  const [pubBusy, setPubBusy] = useState(false);
  const [pubError, setPubError] = useState('');

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [tsRes, pubRes] = await Promise.all([
        request<TailscaleData>('/network/tailscale'),
        request<PublicData>('/network/public'),
      ]);
      setTailscale(tsRes);
      setPublicData(pubRes);
      if (tsRes.target) {
        setTsTarget(tsRes.target);
        setTsDevice(tsRes.device_name || '');
        setTsPort(tsRes.port || 8081);
      }
      if (pubRes.domain) {
        setPubDomain(pubRes.domain);
        setPubMethod(pubRes.method || 'caddy');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load network settings');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function copyText(text: string, key: string) {
    await navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1800);
  }

  async function openQr(url: string) {
    try {
      const svg = await QRCode.toString(url, { type: 'svg', margin: 2, width: 220 });
      setQrSvg(svg);
      setQrModalUrl(url);
    } catch (e: any) {
      setError(e.message || 'Failed to generate QR code');
    }
  }

  async function handleVerifyTailscale() {
    setTsBusy(true);
    setError('');
    try {
      const res = await post<TailscaleData>('/network/tailscale/verify');
      setTailscale(res);
    } catch (e: any) {
      setError(e.message || 'Verification failed');
    } finally {
      setTsBusy(false);
    }
  }

  async function handleSaveTailscale(e: React.FormEvent) {
    e.preventDefault();
    setTsBusy(true);
    setTsError('');
    try {
      const res = await post<TailscaleData>('/network/tailscale/configure', {
        target: tsTarget,
        device_name: tsDevice,
        port: Number(tsPort),
      });
      setTailscale(res);
      setShowTsModal(false);
    } catch (e: any) {
      setTsError(e.message || 'Failed to configure Tailscale');
    } finally {
      setTsBusy(false);
    }
  }

  async function handleResetTailscale() {
    if (!confirm('Are you sure you want to disconnect Tailscale settings?')) return;
    setTsBusy(true);
    try {
      await post('/network/tailscale/reset');
      await loadData();
    } catch (e: any) {
      setError(e.message || 'Failed to reset Tailscale');
    } finally {
      setTsBusy(false);
    }
  }

  async function handleVerifyPublic() {
    setPubBusy(true);
    setError('');
    try {
      const res = await post<PublicData>('/network/public/verify');
      setPublicData(res);
    } catch (e: any) {
      setError(e.message || 'Verification failed');
    } finally {
      setPubBusy(false);
    }
  }

  async function handleSavePublic(e: React.FormEvent) {
    e.preventDefault();
    setPubBusy(true);
    setPubError('');
    try {
      const res = await post<PublicData>('/network/public/configure', {
        domain: pubDomain,
        method: pubMethod,
      });
      setPublicData(res);
      setShowPubModal(false);
    } catch (e: any) {
      setPubError(e.message || 'Failed to configure public access');
    } finally {
      setPubBusy(false);
    }
  }

  async function fetchCaddyfile() {
    try {
      const res = await request<{ caddyfile: string }>('/network/public/caddyfile');
      setShowConfigSnippet({ title: 'Production Caddyfile Template', content: res.caddyfile });
    } catch (e: any) {
      setError(e.message || 'Failed to load Caddyfile');
    }
  }

  async function fetchCloudflare() {
    try {
      const res = await request<{ config_yml: string }>('/network/public/cloudflare');
      setShowConfigSnippet({ title: 'Cloudflare Tunnel (config.yml) Template', content: res.config_yml });
    } catch (e: any) {
      setError(e.message || 'Failed to load Cloudflare configuration');
    }
  }

  async function openTsInviteModal() {
    setInviteError('');
    setInviteSuccessMsg('');
    setShowTsInviteModal(true);
    try {
      const res = await request<{ items: any[] }>('/workspaces');
      setWorkspaces(res.items);
      if (res.items.length) {
        setInviteWsId(String(res.items[0].id));
      }
    } catch {}
    if (tailscale?.full_url) {
      const signupUrl = `${tailscale.full_url.replace(/\/+$/, '')}/signup`;
      setInviteGeneratedUrl(signupUrl);
      try {
        const qr = await QRCode.toDataURL(signupUrl, { width: 220, margin: 1 });
        setInviteQrDataUrl(qr);
      } catch {}
    }
  }

  async function handleCreateTsInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!tailscale?.full_url) return;
    setInviteBusy(true);
    setInviteError('');
    setInviteSuccessMsg('');
    try {
      let finalUrl = `${tailscale.full_url.replace(/\/+$/, '')}/signup`;
      if (inviteEmail.trim() && inviteWsId) {
        const res = await post<any>(`/workspaces/${inviteWsId}/invitations`, {
          email: inviteEmail.trim(),
          role: inviteRole,
        });
        if (res.invite_url) {
          const match = res.invite_url.match(/token=([^&]+)/);
          if (match) {
            finalUrl = `${tailscale.full_url.replace(/\/+$/, '')}/signup?token=${match[1]}`;
          }
        }
        setInviteSuccessMsg(`Invitation registered for ${inviteEmail.trim()}! Remote Tailscale link generated.`);
      }
      setInviteGeneratedUrl(finalUrl);
      const qr = await QRCode.toDataURL(finalUrl, { width: 220, margin: 1 });
      setInviteQrDataUrl(qr);
    } catch (err: any) {
      setInviteError(err.message || 'Failed to create invitation');
    } finally {
      setInviteBusy(false);
    }
  }

  const localUrl = `http://${window.location.hostname}:8081`;

  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">NETWORK & REMOTE CONNECTIVITY</p>
          <h1>Reach Your Server</h1>
          <p className="page-description">
            Connect devices from your local network, access securely via Tailscale VPN, or set up public domain HTTPS.
          </p>
        </div>
        <button className="button secondary" onClick={loadData} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh Network
        </button>
      </div>

      {error && <div className="notice notice-error" style={{ marginBottom: '16px' }}>{error}</div>}

      {/* SECTION 1: Local Network */}
      <section className="panel network-panel" style={{ marginBottom: '24px' }}>
        <div className="network-status">
          <span className="status-ring">
            <Network size={22} />
          </span>
          <div>
            <p className="eyebrow">LOCAL NETWORK</p>
            <h2>Local Area Network Access</h2>
            <p>Devices connected to the same Wi-Fi router or LAN can reach the server directly.</p>
          </div>
          <span className="status-pill">
            <i className="online-dot" /> Port 8081 Active
          </span>
        </div>

        <div className="address-box" style={{ marginTop: '16px' }}>
          <div>
            <small>SERVER LAN ADDRESS</small>
            <strong>{localUrl}</strong>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="button secondary" onClick={() => copyText(localUrl, 'local')}>
              {copiedKey === 'local' ? <Check size={16} /> : <Copy size={16} />}
              {copiedKey === 'local' ? 'Copied' : 'Copy address'}
            </button>
            <button className="button secondary" onClick={() => openQr(localUrl)} title="Show QR Code">
              <QrCode size={16} />
            </button>
          </div>
        </div>

        <div className="steps-list" style={{ marginTop: '16px' }}>
          <div>
            <span>1</span>
            <p>Ensure client devices (phones, laptops) are connected to your local network.</p>
          </div>
          <div>
            <span>2</span>
            <p>Ensure host firewall allows incoming connections on port <code>8081</code>.</p>
          </div>
          <div>
            <span>3</span>
            <p>Open <code>{localUrl}</code> in any browser on your network.</p>
          </div>
        </div>
      </section>

      {/* SECTION 2 & 3 GRID: Tailscale & Public Access */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '20px' }}>
        {/* Tailscale Panel */}
        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon mint"><Network size={19} /></span>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2>Tailscale Private Network</h2>
                <span className={tailscale?.status === 'connected' ? 'status-pill' : 'not-connected'}>
                  {tailscale?.status === 'connected' ? <><i className="online-dot" /> Connected & Verified</> : (tailscale?.status || 'Not configured')}
                </span>
              </div>
              <p>End-to-end encrypted mesh VPN access from trusted devices without opening public router ports.</p>
            </div>
          </div>

          <div style={{ padding: '4px 0' }}>
            {tailscale?.is_configured && tailscale.full_url ? (
              <>
                <div className="address-box" style={{ marginBottom: '14px' }}>
                  <div>
                    <small>VERIFIED TAILSCALE ADDRESS</small>
                    <strong>{tailscale.full_url}</strong>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Node: {tailscale.device_name || tailscale.target} · Port: {tailscale.port}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="button secondary" onClick={() => copyText(tailscale.full_url!, 'ts')}>
                      {copiedKey === 'ts' ? <Check size={16} /> : <Copy size={16} />}
                      {copiedKey === 'ts' ? 'Copied' : 'Copy'}
                    </button>
                    <button className="button secondary" onClick={() => openQr(tailscale.full_url!)} title="Show QR Code">
                      <QrCode size={16} />
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
                  <button className="button primary" onClick={openTsInviteModal}>
                    <Users size={15} /> Invite user via Tailscale
                  </button>
                  <button className="button secondary" onClick={() => copyText(`${tailscale.full_url?.replace(/\/+$/, '')}/signup`, 'ts-signup')}>
                    {copiedKey === 'ts-signup' ? <Check size={15} /> : <Copy size={15} />}
                    {copiedKey === 'ts-signup' ? 'Access link copied' : 'Copy access link'}
                  </button>
                </div>

                <div style={{ display: 'grid', gap: '8px', marginBottom: '16px' }}>
                  <div style={{ padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: '6px', fontSize: '11px', lineHeight: 1.5, border: '1px solid var(--border-color)' }}>
                    <strong>Device Authorization:</strong> Recipients must be connected to your Tailnet before accessing this URL.
                  </div>
                  <div style={{ padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: '6px', fontSize: '11px', lineHeight: 1.5, border: '1px solid var(--border-color)' }}>
                    <strong>Account Authentication:</strong> Recipients must authenticate with their own HomeServer accounts. Your credentials are never shared.
                  </div>
                  <div style={{ padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: '6px', fontSize: '11px', lineHeight: 1.5, color: 'var(--text-muted)', border: '1px solid var(--border-color)' }}>
                    <strong>Transport Security:</strong> WireGuard mesh encrypts all network packets. Add HTTPS certificates via Tailscale certs if browser TLS indicators are required.
                  </div>
                </div>
              </>
            ) : (
              <div style={{ padding: '16px', background: 'var(--bg-elevated)', borderRadius: '8px', marginBottom: '16px', fontSize: '12px' }}>
                <strong>Tailscale is not yet active.</strong>
                <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>
                  Install Tailscale on the host OS or configure a sidecar container, then enter your MagicDNS or Tailscale IP to verify connection.
                </p>
              </div>
            )}

            {/* Checks list */}
            {tailscale?.checks && tailscale.checks.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <small style={{ fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  CONNECTION VERIFICATION CHECKS
                </small>
                <div style={{ display: 'grid', gap: '6px' }}>
                  {tailscale.checks.map((chk, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', padding: '6px 10px', background: 'var(--bg-elevated)', borderRadius: '6px' }}>
                      <span style={{ color: chk.passed ? '#16a34a' : '#dc2626' }}>
                        {chk.passed ? '✓' : '✗'}
                      </span>
                      <strong style={{ minWidth: '130px' }}>{chk.name}:</strong>
                      <span style={{ color: 'var(--text-muted)' }}>{chk.detail}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', borderTop: '1px solid var(--border-light)', paddingTop: '14px' }}>
              {isAdmin && (
                <>
                  <button className="button primary" onClick={() => setShowTsModal(true)}>
                    {tailscale?.is_configured ? 'Edit Tailscale Config' : 'Configure Tailscale'}
                  </button>
                  {tailscale?.is_configured && (
                    <button className="button secondary" onClick={handleVerifyTailscale} disabled={tsBusy}>
                      <RefreshCw size={14} className={tsBusy ? 'animate-spin' : ''} /> Verify Connection
                    </button>
                  )}
                  {tailscale?.is_configured && (
                    <button className="button text" style={{ color: '#dc2626' }} onClick={handleResetTailscale} disabled={tsBusy}>
                      Disconnect
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </section>

        {/* Public Domain & HTTPS Panel */}
        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon lavender"><Globe size={19} /></span>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2>Public Domain & HTTPS</h2>
                <span className={publicData?.status === 'connected' ? 'status-pill' : 'not-connected'}>
                  {publicData?.status === 'connected' ? <><i className="online-dot" /> HTTPS Active</> : (publicData?.status || 'Not configured')}
                </span>
              </div>
              <p>Secure public access using a custom domain with automatic TLS or Cloudflare Zero Trust Tunnel.</p>
            </div>
          </div>

          <div style={{ padding: '4px 0' }}>
            {publicData?.is_configured && publicData.public_url ? (
              <div className="address-box" style={{ marginBottom: '16px' }}>
                <div>
                  <small>PUBLIC HTTPS URL</small>
                  <strong>{publicData.public_url}</strong>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    Method: {publicData.method.toUpperCase()} · Database Isolated: Yes
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="button secondary" onClick={() => copyText(publicData.public_url!, 'pub')}>
                    {copiedKey === 'pub' ? <Check size={16} /> : <Copy size={16} />}
                    {copiedKey === 'pub' ? 'Copied' : 'Copy'}
                  </button>
                  <a className="button secondary" href={publicData.public_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink size={16} />
                  </a>
                </div>
              </div>
            ) : (
              <div style={{ padding: '16px', background: 'var(--bg-elevated)', borderRadius: '8px', marginBottom: '16px', fontSize: '12px' }}>
                <strong>No public domain configured.</strong>
                <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>
                  For external access, configure a domain with Caddy (automatic SSL) or Cloudflare Tunnel to keep your private server protected.
                </p>
              </div>
            )}

            {/* Checks list */}
            {publicData?.checks && publicData.checks.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <small style={{ fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  SECURITY & DOMAIN VERIFICATION
                </small>
                <div style={{ display: 'grid', gap: '6px' }}>
                  {publicData.checks.map((chk, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', padding: '6px 10px', background: 'var(--bg-elevated)', borderRadius: '6px' }}>
                      <span style={{ color: chk.passed ? '#16a34a' : '#dc2626' }}>
                        {chk.passed ? '✓' : '✗'}
                      </span>
                      <strong style={{ minWidth: '150px' }}>{chk.name}:</strong>
                      <span style={{ color: 'var(--text-muted)' }}>{chk.detail}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Template links and Actions */}
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', borderTop: '1px solid var(--border-light)', paddingTop: '14px' }}>
              {isAdmin && (
                <>
                  <button className="button primary" onClick={() => setShowPubModal(true)}>
                    {publicData?.is_configured ? 'Edit Domain Setup' : 'Configure Domain'}
                  </button>
                  {publicData?.is_configured && (
                    <button className="button secondary" onClick={handleVerifyPublic} disabled={pubBusy}>
                      <RefreshCw size={14} className={pubBusy ? 'animate-spin' : ''} /> Verify Domain
                    </button>
                  )}
                  <button className="button secondary" onClick={fetchCaddyfile}>
                    <FileCode size={14} /> Caddyfile Template
                  </button>
                  <button className="button secondary" onClick={fetchCloudflare}>
                    <Server size={14} /> Cloudflare Config
                  </button>
                </>
              )}
            </div>
          </div>
        </section>
      </div>

      {/* QR Code Modal */}
      {qrModalUrl && (
        <div className="modal-backdrop" onClick={() => setQrModalUrl(null)}>
          <div className="modal-card" style={{ maxWidth: '340px', textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 style={{ margin: 0, fontSize: '15px' }}>Scan with Phone</h3>
              <button className="icon-button" onClick={() => setQrModalUrl(null)}><X size={16} /></button>
            </div>
            <div
              style={{ background: '#ffffff', padding: '16px', borderRadius: '12px', display: 'inline-block', margin: '0 auto 12px' }}
              dangerouslySetInnerHTML={{ __html: qrSvg }}
            />
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', wordBreak: 'break-all', margin: 0 }}>
              {qrModalUrl}
            </p>
          </div>
        </div>
      )}

      {/* Tailscale Config Modal */}
      {showTsModal && (
        <div className="modal-backdrop" onClick={() => setShowTsModal(false)}>
          <div className="modal-card" style={{ maxWidth: '520px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0 }}>Configure Tailscale Node</h3>
              <button className="icon-button" onClick={() => setShowTsModal(false)}><X size={16} /></button>
            </div>

            {tsError && <div className="notice notice-error" style={{ marginBottom: '14px' }}>{tsError}</div>}

            <form onSubmit={handleSaveTailscale} className="form-stack">
              <label className="field">
                <span>Tailscale MagicDNS Domain or CGNAT IP</span>
                <input
                  type="text"
                  placeholder="e.g. homeserver.yak-zebra.ts.net or 100.79.132.16"
                  value={tsTarget}
                  onChange={(e) => setTsTarget(e.target.value)}
                  required
                />
                <small className="helper">
                  Find this by running <code>tailscale status</code> or checking your Tailscale admin console.
                </small>
              </label>

              <label className="field">
                <span>Device / Machine Label (Optional)</span>
                <input
                  type="text"
                  placeholder="e.g. Home Server"
                  value={tsDevice}
                  onChange={(e) => setTsDevice(e.target.value)}
                />
              </label>

              <label className="field">
                <span>Application Port</span>
                <input
                  type="number"
                  value={tsPort}
                  onChange={(e) => setTsPort(Number(e.target.value))}
                  min={1}
                  max={65535}
                  required
                />
                <small className="helper">HomeServer V2 runs on port 8081.</small>
              </label>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="button secondary" onClick={() => setShowTsModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="button primary" disabled={tsBusy}>
                  {tsBusy ? 'Testing & Saving…' : 'Save & Verify'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Public Access Config Modal */}
      {showPubModal && (
        <div className="modal-backdrop" onClick={() => setShowPubModal(false)}>
          <div className="modal-card" style={{ maxWidth: '520px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0 }}>Configure Public Access</h3>
              <button className="icon-button" onClick={() => setShowPubModal(false)}><X size={16} /></button>
            </div>

            {pubError && <div className="notice notice-error" style={{ marginBottom: '14px' }}>{pubError}</div>}

            <form onSubmit={handleSavePublic} className="form-stack">
              <label className="field">
                <span>Fully Qualified Domain Name (FQDN)</span>
                <input
                  type="text"
                  placeholder="e.g. cloud.yourdomain.com"
                  value={pubDomain}
                  onChange={(e) => setPubDomain(e.target.value)}
                  required
                />
                <small className="helper">Domain or subdomain pointing to this server.</small>
              </label>

              <label className="field">
                <span>Access & Reverse Proxy Method</span>
                <select value={pubMethod} onChange={(e) => setPubMethod(e.target.value as any)}>
                  <option value="caddy">Caddy Reverse Proxy (Automatic HTTPS)</option>
                  <option value="cloudflare">Cloudflare Tunnel (No port forwarding)</option>
                  <option value="external_proxy">External Reverse Proxy (Nginx, Traefik, etc.)</option>
                </select>
              </label>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" className="button secondary" onClick={() => setShowPubModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="button primary" disabled={pubBusy}>
                  {pubBusy ? 'Validating…' : 'Save & Validate'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Template Code Snippet Modal */}
      {showConfigSnippet && (
        <div className="modal-backdrop" onClick={() => setShowConfigSnippet(null)}>
          <div className="modal-card" style={{ maxWidth: '640px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ margin: 0 }}>{showConfigSnippet.title}</h3>
              <button className="icon-button" onClick={() => setShowConfigSnippet(null)}><X size={16} /></button>
            </div>
            <pre style={{
              background: 'var(--bg-app)',
              padding: '16px',
              borderRadius: '8px',
              overflowX: 'auto',
              fontSize: '11px',
              border: '1px solid var(--border-color)',
              lineHeight: 1.5,
              maxHeight: '360px',
            }}>
              <code>{showConfigSnippet.content}</code>
            </pre>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '14px' }}>
              <button className="button secondary" onClick={() => copyText(showConfigSnippet.content, 'snippet')}>
                {copiedKey === 'snippet' ? <Check size={16} /> : <Copy size={16} />}
                {copiedKey === 'snippet' ? 'Copied' : 'Copy Configuration'}
              </button>
              <button className="button primary" onClick={() => setShowConfigSnippet(null)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tailscale Onboarding & Invite Modal */}
      {showTsInviteModal && (
        <div className="modal-backdrop" onClick={() => setShowTsInviteModal(false)}>
          <div className="modal-card" style={{ maxWidth: '580px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="quick-icon mint" style={{ width: '28px', height: '28px' }}><Network size={16} /></span>
                <h3 style={{ margin: 0 }}>Tailscale Remote Onboarding</h3>
              </div>
              <button className="icon-button" onClick={() => setShowTsInviteModal(false)}><X size={16} /></button>
            </div>

            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Generate a remote signup or invitation URL powered by your verified Tailscale IP / MagicDNS address.
            </p>

            {inviteError && <div className="notice notice-error" style={{ marginBottom: '12px' }}>{inviteError}</div>}
            {inviteSuccessMsg && <div className="notice notice-success" style={{ marginBottom: '12px' }}>{inviteSuccessMsg}</div>}

            <form onSubmit={handleCreateTsInvite} className="form-stack">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <label className="field">
                  <span>Workspace</span>
                  <select value={inviteWsId} onChange={(e) => setInviteWsId(e.target.value)}>
                    {workspaces.map((w) => (
                      <option key={w.id} value={w.id}>{w.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Role</span>
                  <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                    <option value="member">Member</option>
                    <option value="read_only">Read-only</option>
                  </select>
                </label>
              </div>

              <label className="field">
                <span>Recipient Email Address (Optional for general signup link)</span>
                <input
                  type="email"
                  placeholder="name@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                />
              </label>

              <button type="submit" className="button primary full" disabled={inviteBusy}>
                {inviteBusy ? 'Generating Link…' : (inviteEmail ? 'Create Invitation & Tailscale Link' : 'Generate Remote Access Link')}
              </button>
            </form>

            {inviteGeneratedUrl && (
              <div style={{ marginTop: '16px', borderTop: '1px solid var(--border-light)', paddingTop: '16px' }}>
                <small style={{ fontWeight: 600, color: 'var(--text-muted)' }}>REMOTE ONBOARDING URL</small>
                <div className="copy-link-box" style={{ marginTop: '6px' }}>
                  <code>{inviteGeneratedUrl}</code>
                  <button className="button secondary" onClick={() => copyText(inviteGeneratedUrl, 'remote-url')}>
                    {copiedKey === 'remote-url' ? <Check size={14} /> : <Copy size={14} />}
                    {copiedKey === 'remote-url' ? 'Copied' : 'Copy'}
                  </button>
                </div>

                {inviteQrDataUrl && (
                  <div className="qr-preview-card">
                    <img src={inviteQrDataUrl} alt="Remote Onboarding QR Code" />
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '8px' }}>
                      Scan from any Tailscale-connected mobile device
                    </span>
                  </div>
                )}

                <div style={{ background: 'var(--bg-elevated)', padding: '12px', borderRadius: '8px', fontSize: '11px', lineHeight: 1.5 }}>
                  <strong>How remote onboarding works:</strong>
                  <ol style={{ paddingLeft: '18px', margin: '6px 0 0' }}>
                    <li>Recipient must have the Tailscale app active and connected to your Tailnet.</li>
                    <li>Recipient opens the link or scans the QR code.</li>
                    <li>Recipient registers their own username/password and verifies email OTP.</li>
                    <li>Recipient only gains access to their authorized workspace. Private server owner files remain isolated.</li>
                  </ol>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button className="button secondary" onClick={() => setShowTsInviteModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
