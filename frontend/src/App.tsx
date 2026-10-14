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

import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  Archive,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Bell,
  Check,
  CheckCircle,
  ChevronRight,
  Cloud,
  Copy,
  Files,
  Folder,
  HardDrive,
  LayoutDashboard,
  LogOut,
  Menu,
  Network,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Shield,
  Trash2,
  Upload,
  Users,
  X
} from 'lucide-react';
import { post, request } from './api';
import { StorageManagement } from './StorageManagement';
import { ThemeProvider, ThemeToggle, ThemeSelector } from './theme';
import { AdminOverview, AdminUsers, AdminAuditLogs, AdminBackups, AdminDiagnostics } from './AdminDashboard';
import { NetworkManagement } from './NetworkManagement';

type User = { id: number; name: string; email: string; username: string; role: string };
type Item = { name: string; path: string; kind: 'file' | 'folder'; size: number; modified_at: string };
const pretty = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;


function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    request<User>('/auth/me').then(setUser).catch(() => setUser(null)).finally(() => setReady(true));
  }, []);

  if (!ready) return <div className="loading-page"><div className="spinner"/><span>Loading your private cloud…</span></div>;

  return (
    <ThemeProvider>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/"/> : <Login onLogin={setUser}/>}/>
        <Route path="/signup" element={user ? <Navigate to="/"/> : <Signup onLogin={setUser}/>}/>
        <Route path="/register" element={user ? <Navigate to="/"/> : <Signup onLogin={setUser}/>}/>
        <Route path="/verify" element={<Verify onLogin={setUser}/>}/>
        <Route path="/reset-password" element={<ResetPassword/>}/>
        <Route path="/accept-invitation" element={<AcceptInvitation user={user}/>}/>
        <Route path="*" element={user ? <Shell user={user} onLogout={() => setUser(null)}/> : <Navigate to="/login" replace/>}/>
      </Routes>
    </ThemeProvider>
  );
}


function AuthFrame({ children, title, subtitle }: { children: ReactNode; title: string; subtitle: string }) {
  return (
    <main className="auth-layout">
      <div className="auth-aside">
        <div className="brand-mark"><Cloud size={22}/></div>
        <div>
          <p className="eyebrow light">YOUR FILES. YOUR SERVER.</p>
          <h1>A calmer home<br/>for your digital life.</h1>
          <p className="aside-copy">Keep the things that matter close, private, and available to the people you trust.</p>
        </div>
        <div className="aside-foot"><Shield size={15}/> Private by design · Stored on your hardware</div>
      </div>
      <section className="auth-main">
        <div className="auth-card">
          <Link className="brand compact" to="/login">
            <span className="brand-mark"><Cloud size={18}/></span>
            <span>HomeServer <b>V2</b></span>
          </Link>
          <p className="eyebrow">GET STARTED</p>
          <h2>{title}</h2>
          <p className="auth-subtitle">{subtitle}</p>
          {children}
        </div>
      </section>
    </main>
  );
}

function Message({ error, success }: { error?: string; success?: string }) {
  return error || success ? <div role="alert" className={`notice ${error ? 'notice-error' : 'notice-success'}`}>{error || success}</div> : null;
}

function Field({ label, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return <label className="field"><span>{label}</span><input {...props}/></label>;
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const form = new FormData(event.currentTarget);
    try {
      const user = await post<User>('/auth/login', {
        identifier: form.get('identifier'),
        password: form.get('password'),
      });
      onLogin(user);
      const token = params.get('invite') || params.get('token');
      if (token) {
        try {
          await post('/invitations/accept', { token });
        } catch {}
        navigate('/people');
      } else {
        navigate('/');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame title="Welcome back" subtitle="Sign in to reach the files you keep at home.">
      <form onSubmit={submit} className="form-stack">
        <Message error={error} />
        <Field label="Email or username" name="identifier" autoComplete="username" required />
        <Field label="Password" name="password" type="password" autoComplete="current-password" required />
        <div className="form-row">
          <span />
          <Link to="/reset-password">Forgot password?</Link>
        </div>
        <button className="button primary full" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'} <ArrowRight size={17} />
        </button>
        <p className="center helper">
          New to HomeServer? <Link to="/signup">Create an account</Link>
        </p>
      </form>
    </AuthFrame>
  );
}

function Signup(_props: { onLogin?: (user: User) => void }) {
  const [params] = useSearchParams();
  const token = params.get('token') || params.get('invite');
  const navigate = useNavigate();

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [bootstrap, setBootstrap] = useState(false);
  const [policy, setPolicy] = useState('open');
  const [invitedInfo, setInvitedInfo] = useState<{ email: string; workspace_name: string; role: string } | null>(null);

  useEffect(() => {
    request<{ available: boolean }>('/auth/bootstrap-status')
      .then((v) => setBootstrap(v.available))
      .catch(() => {});

    request<{ policy: string }>('/auth/registration-policy')
      .then((p) => setPolicy(p.policy))
      .catch(() => {});

    if (token) {
      request<{ valid: boolean; email: string; workspace_name: string; role: string }>(`/invitations/verify-token?token=${encodeURIComponent(token)}`)
        .then((res) => {
          if (res.valid) {
            setInvitedInfo(res);
          }
        })
        .catch((e) => setError(e.message || 'Invitation is invalid or has expired'));
    }
  }, [token]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setSuccess('');
    const form = new FormData(e.currentTarget);
    const password = String(form.get('password'));
    const confirm = String(form.get('confirm'));
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    const email = String(form.get('email')).trim();
    const body = {
      full_name: String(form.get('name')).trim(),
      email,
      username: String(form.get('username')).trim(),
      password,
      invitation_token: token || undefined,
    };
    setBusy(true);
    try {
      await post(bootstrap ? '/auth/bootstrap' : '/auth/register', body);
      sessionStorage.setItem('verifyEmail', email);
      sessionStorage.setItem('verifyPassword', password);
      setSuccess('Verification code sent! Check your inbox.');
      setTimeout(() => navigate('/verify'), 600);
    } catch (err: any) {
      setError(err.message || 'Registration failed');
    } finally {
      setBusy(false);
    }
  }

  const isInviteOnlyBlocked = !bootstrap && policy === 'invitation_only' && !token;

  return (
    <AuthFrame
      title={bootstrap ? 'Create your server owner account' : (invitedInfo ? 'Accept invitation & create account' : 'Create your account')}
      subtitle={bootstrap ? 'Set up the initial administrator for your HomeServer.' : 'We’ll send a one-time code to confirm your email address.'}
    >
      {invitedInfo && (
        <div className="invite-alert success" style={{ marginBottom: '14px' }}>
          <strong>You are invited!</strong>
          <span>Join <b>{invitedInfo.workspace_name}</b> as a {invitedInfo.role.replace('_', ' ')}.</span>
        </div>
      )}

      {isInviteOnlyBlocked ? (
        <div className="form-stack">
          <div className="invite-alert warning">
            <strong>Registration is invitation only</strong>
            <p style={{ margin: '4px 0 0' }}>
              Only users with an active invitation link can create an account on this server. If an administrator sent you an invitation, please click the link in your email.
            </p>
          </div>
          <Link className="button secondary full" to="/login">
            Back to sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="form-stack">
          <Message error={error} success={success} />
          <Field label="Full name" name="name" autoComplete="name" minLength={2} required />
          <Field
            label="Email address"
            name="email"
            type="email"
            autoComplete="email"
            defaultValue={invitedInfo?.email || ''}
            required
          />
          <Field label="Username" name="username" autoComplete="username" minLength={3} required />
          <Field label="Password" name="password" type="password" autoComplete="new-password" minLength={12} required />
          <Field label="Confirm password" name="confirm" type="password" autoComplete="new-password" required />
          <p className="helper">Use at least 12 characters. Your password is never shared with administrators.</p>
          <button className="button primary full" disabled={busy}>
            {busy ? 'Creating account…' : 'Continue'} <ArrowRight size={17} />
          </button>
          <p className="center helper">
            Already registered? <Link to="/login">Sign in</Link>
          </p>
        </form>
      )}
    </AuthFrame>
  );
}

function Verify({ onLogin }: { onLogin?: (user: User) => void }) {
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    if (cooldown > 0) {
      const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [cooldown]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError('');
    const f = new FormData(e.currentTarget);
    const email = String(f.get('email') || '').trim();
    const code = String(f.get('code') || '').trim();
    try {
      await post('/auth/verify', { email, code });
      setSuccess('Email verified successfully! You can now sign in.');
      const savedPw = sessionStorage.getItem('verifyPassword');
      if (savedPw && onLogin) {
        try {
          const u = await post<User>('/auth/login', { identifier: email, password: savedPw });
          sessionStorage.removeItem('verifyPassword');
          onLogin(u);
          navigate('/');
          return;
        } catch {}
      }
      setTimeout(() => navigate('/login'), 1200);
    } catch (x: any) {
      setError(x.message);
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    const email = sessionStorage.getItem('verifyEmail') || '';
    if (!email) {
      setError('Please enter your email above before requesting a code');
      return;
    }
    try {
      await post('/auth/resend', { email });
      setSuccess('If verification is pending, a new code has been sent.');
      setCooldown(60);
    } catch (x: any) {
      setError(x.message);
    }
  }

  return (
    <AuthFrame title="Check your email" subtitle="Enter the six-digit code we sent you. It expires in five minutes.">
      <form className="form-stack" onSubmit={submit}>
        <Message error={error} success={success} />
        <Field label="Email address" name="email" type="email" defaultValue={sessionStorage.getItem('verifyEmail') || ''} required />
        <Field label="Verification code" name="code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="000000" required />
        <button className="button primary full" disabled={busy}>
          {busy ? 'Verifying…' : 'Verify email'} <ArrowRight size={17} />
        </button>
        <button type="button" className="button text full" onClick={resend} disabled={cooldown > 0}>
          {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Send a new code'}
        </button>
        <p className="center helper">
          Return to <Link to="/login">Sign in</Link>
        </p>
      </form>
    </AuthFrame>
  );
}

function ResetPassword() {
  const [step, setStep] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      if (!step) {
        await post('/auth/password-reset', { email: f.get('email') });
        setStep(true);
        setSuccess('If the account exists, a reset code has been sent.');
      } else {
        if (f.get('password') !== f.get('confirm')) throw Error('Passwords do not match');
        await post('/auth/password-reset/confirm', { email: f.get('email'), code: f.get('code'), new_password: f.get('password') });
        setSuccess('Password updated. You can now sign in.');
      }
    } catch (x: any) {
      setError(x.message);
    }
  }

  return (
    <AuthFrame title="Reset your password" subtitle="We’ll send a one-time code to your verified email.">
      <form className="form-stack" onSubmit={submit}>
        <Message error={error} success={success} />
        <Field label="Email address" name="email" type="email" required />
        {step && (
          <>
            <Field label="Reset code" name="code" inputMode="numeric" required />
            <Field label="New password" name="password" type="password" minLength={12} required />
            <Field label="Confirm password" name="confirm" type="password" required />
          </>
        )}
        <button className="button primary full">{step ? 'Update password' : 'Send reset code'} <ArrowRight size={17} /></button>
        <Link className="center helper" to="/login">Back to sign in</Link>
      </form>
    </AuthFrame>
  );
}

const nav = [
  { label: 'Overview', path: '/', icon: LayoutDashboard },
  { label: 'My files', path: '/files', icon: Files },
  { label: 'People & access', path: '/people', icon: Users },
  { label: 'Network', path: '/network', icon: Network },
  { label: 'Settings', path: '/settings', icon: Settings }
];

const adminNav = [
  { label: 'Admin Overview', path: '/admin', icon: Shield },
  { label: 'User Directory', path: '/admin/users', icon: Users },
  { label: 'Backups & Recovery', path: '/admin/backups', icon: Archive },
  { label: 'System Diagnostics', path: '/admin/diagnostics', icon: CheckCircle },
  { label: 'Audit Logs', path: '/admin/audit', icon: Activity },
];

function Shell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const isAdmin = ['system_owner', 'system_admin'].includes(user.role);

  async function logout() {
    try {
      await post('/auth/logout');
    } finally {
      onLogout();
      navigate('/login');
    }
  }

  const activeLabel = [...nav, ...adminNav].find((n) => n.path === location.pathname)?.label || 'Workspace';

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menu ? 'sidebar-open' : ''}`}>
        <Link to="/" className="brand">
          <span className="brand-mark"><Cloud size={18} /></span>
          <span>HomeServer <b>V2</b></span>
        </Link>
        <div className="workspace-switch">
          <div className="workspace-avatar">H</div>
          <div><strong>Home workspace</strong><small>Personal server</small></div>
          <ChevronRight size={15} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {nav.map((item) => (
            <Link key={item.path} to={item.path} onClick={() => setMenu(false)} className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}>
              <item.icon size={18} />
              {item.label}
              {item.path === '/people' && <span className="nav-dot" />}
            </Link>
          ))}
        </nav>
        {isAdmin && (
          <>
            <p className="nav-label" style={{ marginTop: '18px' }}>ADMINISTRATION</p>
            <nav>
              {adminNav.map((item) => (
                <Link key={item.path} to={item.path} onClick={() => setMenu(false)} className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}>
                  <item.icon size={18} />
                  {item.label}
                </Link>
              ))}
            </nav>
          </>
        )}
        <div className="sidebar-bottom">
          <div className="server-mini"><div><b>Your server</b><small>Local private cloud</small></div><Activity size={16} /></div>
          <div className="profile-row">
            <div className="profile-avatar">{user.name.slice(0, 1).toUpperCase()}</div>
            <div className="profile-copy"><b>{user.name}</b><small>{user.role.replace('_', ' ')}</small></div>
            <button className="icon-button" aria-label="Sign out" onClick={logout}><LogOut size={17} /></button>
          </div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button className="mobile-menu icon-button" aria-label="Open menu" onClick={() => setMenu(!menu)}>{menu ? <X /> : <Menu />}</button>
          <div className="breadcrumbs"><span>Home</span><ChevronRight size={14} /><b>{activeLabel}</b></div>
          <div className="top-actions">
            <ThemeToggle />
            <span className="secure-chip"><Shield size={14} /> Private server</span>
            <button className="icon-button" aria-label="Notifications"><Bell size={18} /></button>
            <div className="profile-avatar top-avatar">{user.name.slice(0, 1).toUpperCase()}</div>
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route index element={<Dashboard user={user} />} />
            <Route path="files" element={<FileManager />} />
            <Route path="people" element={<People user={user} />} />
            <Route path="network" element={<NetworkManagement isAdmin={isAdmin} />} />
            <Route path="settings" element={<SettingsPage user={user} />} />
            <Route path="admin" element={isAdmin ? <AdminOverview /> : <Navigate to="/" replace />} />
            <Route path="admin/users" element={isAdmin ? <AdminUsers /> : <Navigate to="/" replace />} />
            <Route path="admin/backups" element={isAdmin ? <AdminBackups /> : <Navigate to="/" replace />} />
            <Route path="admin/diagnostics" element={isAdmin ? <AdminDiagnostics /> : <Navigate to="/" replace />} />
            <Route path="admin/audit" element={isAdmin ? <AdminAuditLogs /> : <Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  );
}

function Dashboard({ user }: { user: User }) {
  const [setup, setSetup] = useState<any>(null);
  const [stats, setStats] = useState<Item[] | null>(null);
  const [err, setErr] = useState('');
  const [online, setOnline] = useState(false);

  useEffect(() => {
    if (['system_owner', 'system_admin'].includes(user.role)) request('/setup/status').then(setSetup).catch((e) => setErr(e.message));
    request<{ items: Item[] }>('/files').then((r) => setStats(r.items)).catch(() => {});
    fetch('/health/ready').then((r) => setOnline(r.ok)).catch(() => setOnline(false));
  }, [user.role]);

  return (
    <>
      <PageHeading eyebrow="YOUR PRIVATE CLOUD" title={`Good to see you, ${user.name.split(' ')[0]}`} description="Your files, people, and server are all in one place." action={<Link className="button primary" to="/files"><Upload size={16} /> Upload files</Link>} />
      <Message error={err} />
      {setup && !setup.initialized && <SetupWizard onDone={() => request('/setup/status').then(setSetup)} />}
      <section className="stat-grid">
        <article className="stat-card">
          <div className="stat-icon purple"><HardDrive size={19} /></div>
          <span>Root-level file size</span>
          <strong>{stats ? pretty(stats.reduce((sum, f) => sum + f.size, 0)) : 'Loading'}</strong>
          <small>Usage from the files in your home folder</small>
        </article>
        <article className="stat-card">
          <div className="stat-icon green"><Files size={19} /></div>
          <span>Files in your space</span>
          <strong>{stats?.length ?? '—'}</strong>
          <small>Stored on your configured server</small>
        </article>
        <article className="stat-card">
          <div className="stat-icon blue"><Activity size={19} /></div>
          <span>Server status</span>
          <strong className="status-text">{online ? <><i className="online-dot" /> Online</> : 'Checking'}</strong>
          <small>Application and database health check</small>
        </article>
      </section>
      <section className="section-heading">
        <div><p className="eyebrow">YOUR SPACE</p><h2>Pick up where you left off</h2></div>
        <Link to="/files" className="link-arrow">Open file manager <ArrowRight size={15} /></Link>
      </section>
      <div className="quick-grid">
        <Link to="/files" className="quick-card"><span className="quick-icon lavender"><Folder /></span><div><b>My files</b><span>Browse your personal storage</span></div><ArrowRight size={17} /></Link>
        <Link to="/people" className="quick-card"><span className="quick-icon peach"><Users /></span><div><b>Share with people</b><span>Invite family or teammates</span></div><ArrowRight size={17} /></Link>
        <Link to="/network" className="quick-card"><span className="quick-icon mint"><Network /></span><div><b>Connect from anywhere</b><span>See local access guidance</span></div><ArrowRight size={17} /></Link>
      </div>
      <div className="tip-card">
        <div className="tip-icon"><Shield size={20} /></div>
        <div><b>Your server, your rules</b><p>Your files stay on storage that you control. Add a mounted drive when you need more room.</p></div>
        <Link to="/settings">Storage settings <ArrowRight size={15} /></Link>
      </div>
      {['system_owner', 'system_admin'].includes(user.role) && (
        <div className="tip-card" style={{ marginTop: '12px' }}>
          <div className="tip-icon"><Shield size={20} /></div>
          <div><b>Server administration</b><p>Monitor real-time host telemetry, manage users, and review audit logs.</p></div>
          <Link to="/admin">Admin overview <ArrowRight size={15} /></Link>
        </div>
      )}
    </>
  );
}

function SetupWizard({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [serverName, setServerName] = useState('My HomeServer');
  const [workspaceKind, setWorkspaceKind] = useState('personal');
  const [policy, setPolicy] = useState('open');
  const labels = ['Welcome', 'Server name', 'Workspace', 'Storage', 'Network', 'Security'];

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      await request('/setup/', {
        method: 'PUT',
        body: JSON.stringify({ server_name: serverName, workspace_kind: workspaceKind, registration_policy: policy }),
      });
      onDone();
    } catch (x: any) {
      setError(x.message);
    }
  }

  return (
    <section className="wizard-card">
      <div className="wizard-top">
        <span className="wizard-badge"><Check size={14} /> FIRST-RUN SETUP</span>
        <span className="wizard-count">{Math.min(step + 1, labels.length)} of {labels.length}</span>
      </div>
      <div className="wizard-progress">{labels.map((l, i) => <i key={l} className={i <= step ? 'filled' : ''} />)}</div>
      <form onSubmit={step === labels.length - 1 ? submit : (e) => { e.preventDefault(); setStep(step + 1); }}>
        <Message error={error} />
        <p className="eyebrow">{labels[step]}</p>
        {step === 0 ? (
          <><h2>Let’s make this server yours.</h2><p>We’ll set a name, confirm your workspace, and choose who can create accounts.</p></>
        ) : step === 1 ? (
          <><h2>What should we call your server?</h2><Field label="Server name" name="server" value={serverName} onChange={(e) => setServerName(e.target.value)} required /></>
        ) : step === 2 ? (
          <><h2>Who is this server for?</h2><label className="field"><span>Workspace type</span><select name="workspace" value={workspaceKind} onChange={(e) => setWorkspaceKind(e.target.value)}><option value="personal">Personal</option><option value="organization">Family or organization</option></select></label></>
        ) : step === 3 ? (
          <><h2>Your storage is ready to configure.</h2><p>HomeServer uses the mounted <code>/data</code> folder. Add host drives in Docker Compose, then choose a folder from this location in My files.</p></>
        ) : step === 4 ? (
          <><h2>Connect on your local network.</h2><p>Open port 8081 on your server host’s firewall. We only show network addresses when configured by your operator.</p></>
        ) : (
          <><h2>Choose your registration policy.</h2><label className="field"><span>New account access</span><select name="policy" value={policy} onChange={(e) => setPolicy(e.target.value)}><option value="open">Open registration</option><option value="invitation_only">Invitation only</option></select></label></>
        )}
        <div className="wizard-actions">
          {step > 0 && <button className="button secondary" type="button" onClick={() => setStep(step - 1)}><ArrowLeft size={16} /> Back</button>}
          <button className="button primary" type="submit">{step === labels.length - 1 ? 'Initialize server' : 'Continue'} <ArrowRight size={16} /></button>
        </div>
      </form>
    </section>
  );
}

function FileManager() {
  const [path, setPath] = useState('');
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');

  const currentWorkspace = workspaces.find((w) => String(w.id) === String(workspaceId));
  const canWrite = currentWorkspace ? ['owner', 'organization_admin', 'member'].includes(currentWorkspace.role) : false;
  const isReadOnly = currentWorkspace ? currentWorkspace.role === 'read_only' : false;

  const workspaceQuery = (id = workspaceId) => id ? `&workspace_id=${encodeURIComponent(id)}` : '';

  async function load(p = path, id = workspaceId) {
    if (!id) return;
    setLoading(true);
    setError('');
    try {
      const result = await request<{ items: Item[] }>(`/files?path=${encodeURIComponent(p)}${workspaceQuery(id)}`);
      setItems(result.items);
      setPath(p);
    } catch (e: any) {
      setItems([]);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function reloadWorkspaces(targetId?: string) {
    try {
      const result = await request<{ items: any[] }>('/workspaces');
      setWorkspaces(result.items);
      const chosenId = targetId || workspaceId;
      const found = result.items.find((w) => String(w.id) === String(chosenId));
      if (!found && result.items.length > 0) {
        const initial = result.items.find((w) => w.kind === 'personal' && (w.role === 'owner' || w.role === 'system_owner'))
          || result.items.find((w) => w.kind === 'personal')
          || result.items[0];
        setWorkspaceId(String(initial.id));
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function refreshAll() {
    await reloadWorkspaces();
    await load();
  }

  useEffect(() => {
    reloadWorkspaces();
  }, []);

  useEffect(() => {
    if (workspaceId) {
      setItems([]);
      setPath('');
      setQuery('');
      load('', workspaceId);
    }
  }, [workspaceId]);

  const crumbs = path.split('/').filter(Boolean);

  async function upload(e: FormEvent<HTMLInputElement>) {
    if (!canWrite) {
      setError('This workspace is read-only for your account');
      return;
    }
    const input = e.currentTarget, files = input.files;
    if (!files?.length) return;
    const form = new FormData();
    Array.from(files).forEach((file) => form.append('files', file));
    setBusy(true);
    setError('');
    try {
      await request(`/files/upload?path=${encodeURIComponent(path)}${workspaceQuery()}`, { method: 'POST', body: form });
      await load();
    } catch (x: any) {
      setError(x.message);
    } finally {
      setBusy(false);
      input.value = '';
    }
  }

  async function createFolder() {
    if (!canWrite) {
      setError('This workspace is read-only for your account');
      return;
    }
    const name = prompt('Folder name');
    if (!name) return;
    setError('');
    try {
      await post('/files/folders', { path, new_name: name, workspace_id: Number(workspaceId) });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function rename(item: Item) {
    if (!canWrite) {
      setError('This workspace is read-only for your account');
      return;
    }
    const newName = prompt('New name', item.name);
    if (!newName) return;
    setError('');
    try {
      await request('/files/rename', { method: 'PUT', body: JSON.stringify({ path: item.path, new_name: newName, workspace_id: Number(workspaceId) }) });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(item: Item) {
    if (!canWrite) {
      setError('This workspace is read-only for your account');
      return;
    }
    if (!confirm(`Delete ${item.name}? This removes it from your server.`)) return;
    setError('');
    try {
      await request(`/files?path=${encodeURIComponent(item.path)}${workspaceQuery()}`, { method: 'DELETE' });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function search(value: string) {
    setQuery(value);
    if (!value) {
      load();
      return;
    }
    setLoading(true);
    setError('');
    try {
      const r = await request<{ items: Item[] }>(`/files/search?q=${encodeURIComponent(value)}${workspaceQuery()}`);
      setItems(r.items);
    } catch (e: any) {
      setItems([]);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const downloadUrl = (item: Item) => `/api/v1/files/download?path=${encodeURIComponent(item.path)}${workspaceQuery()}`;

  return (
    <>
      <PageHeading
        eyebrow={currentWorkspace ? `${currentWorkspace.name.toUpperCase()}${isReadOnly ? ' • READ-ONLY' : (currentWorkspace.role === 'organization_admin' ? ' • ADMIN' : '')}` : 'YOUR SPACE'}
        title="My files"
        description={isReadOnly ? 'Viewing files in read-only mode. You can browse and download files.' : 'Keep your folders organized and share the things that matter.'}
        action={
          <>
            <button className="button secondary" onClick={refreshAll} title="Refresh files and permissions"><RefreshCw size={15} /> Refresh</button>
            {canWrite && (
              <>
                <button className="button secondary" onClick={createFolder}><Plus size={16} /> New folder</button>
                <label className="button primary upload-button">
                  <Upload size={16} />{busy ? 'Uploading…' : 'Upload'}
                  <input type="file" multiple onChange={upload} disabled={busy} />
                </label>
              </>
            )}
          </>
        }
      />
      <Message error={error} />
      <section className="file-panel">
        <div className="file-toolbar">
          <div className="breadcrumbs file-crumbs">
            <button onClick={() => load('')}>{currentWorkspace?.name || 'My files'}</button>
            {crumbs.map((crumb, i) => (
              <span key={i}>
                <ChevronRight size={14} />
                <button onClick={() => load(crumbs.slice(0, i + 1).join('/'))}>{crumb}</button>
              </span>
            ))}
          </div>
          <label className="field workspace-select">
            <span>Workspace</span>
            <select aria-label="Workspace" value={workspaceId} onChange={(e) => { setPath(''); setQuery(''); setWorkspaceId(e.target.value); }}>
              {workspaces.map((w) => {
                const roleBadge = w.role === 'read_only' ? ' (Read-only)' : (w.role === 'organization_admin' ? ' (Admin)' : '');
                const kindBadge = w.kind === 'organization' ? ' [Org]' : '';
                return <option key={w.id} value={w.id}>{w.name}{kindBadge}{roleBadge}</option>;
              })}
            </select>
          </label>
          <label className="search-box">
            <Search size={16} />
            <input value={query} onChange={(e) => search(e.target.value)} placeholder="Search files" aria-label="Search files" />
            <kbd>/</kbd>
          </label>
        </div>
        <div className="file-list-head"><span>Name</span><span>Modified</span><span>Size</span><span /></div>
        {loading ? (
          <div className="empty-state">
            <b>Loading files…</b>
          </div>
        ) : error ? (
          <div className="empty-state">
            <div className="empty-icon"><Shield size={24} /></div>
            <b>Access restricted</b>
            <p>{error}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><Folder size={24} /></div>
            <b>{query ? 'No matching files' : 'This folder is empty'}</b>
            <p>{query ? 'Try a different search term.' : (isReadOnly ? 'No files in this folder yet.' : 'Upload a file or create a folder to get started.')}</p>
            {!query && canWrite && (
              <label className="button secondary upload-button"><Upload size={15} /> Upload files<input type="file" multiple onChange={upload} /></label>
            )}
          </div>
        ) : (
          items.map((item) => (
            <div className="file-row" key={item.path}>
              <button className="file-name" onClick={() => item.kind === 'folder' ? load(item.path) : undefined}>
                <span className={`file-icon ${item.kind}`}><ItemIcon kind={item.kind} /></span>
                <span>{item.name}</span>
              </button>
              <span className="file-date">{item.modified_at ? new Date(item.modified_at).toLocaleDateString() : '—'}</span>
              <span className="file-size">{item.kind === 'folder' ? '—' : pretty(item.size || 0)}</span>
              <div className="file-actions">
                {item.kind === 'file' && <a aria-label={`Download ${item.name}`} href={downloadUrl(item)}><ArrowDownToLine size={16} /></a>}
                {canWrite && (
                  <>
                    <button aria-label={`Rename ${item.name}`} onClick={() => rename(item)}>Rename</button>
                    <button aria-label={`Delete ${item.name}`} className="danger-action" onClick={() => remove(item)}><Trash2 size={15} /></button>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </section>
      <p className="storage-footnote"><Shield size={14} /> Members can access files in workspaces they belong to.</p>
    </>
  );
}

function ItemIcon({ kind }: { kind: 'file' | 'folder' }) {
  return kind === 'folder' ? <Folder size={17} /> : <Files size={17} />;
}

function People({ user }: { user: User }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('member');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [invitations, setInvitations] = useState<any[]>([]);
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [workspaceMembers, setWorkspaceMembers] = useState<Record<number, any[]>>({});
  const [workspace, setWorkspace] = useState('');
  const [copiedId, setCopiedId] = useState<number | 'new' | null>(null);
  const [createdInviteUrl, setCreatedInviteUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const [w, i] = await Promise.all([
        request<{ items: any[] }>('/workspaces'),
        request<{ items: any[] }>('/invitations'),
      ]);
      setWorkspaces(w.items);
      setInvitations(i.items);
      if (!workspace && w.items.length) setWorkspace(String(w.items[0].id));

      const memberMap: Record<number, any[]> = {};
      await Promise.all(
        w.items.map(async (ws) => {
          try {
            const m = await request<{ items: any[] }>(`/workspaces/${ws.id}/members`);
            memberMap[ws.id] = m.items;
          } catch {}
        })
      );
      setWorkspaceMembers(memberMap);
    } catch (e: any) {
      setError(e.message || 'Failed to refresh workspace data');
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function invite(e: FormEvent) {
    e.preventDefault();
    setError('');
    setMessage('');
    setCreatedInviteUrl(null);
    setBusy(true);
    try {
      const res = await post<any>(`/workspaces/${workspace}/invitations`, { email: email.trim(), role });
      if (res.delivery_status === 'role_updated') {
        setMessage(res.message || `Role updated for ${res.email} to ${res.role.replace('_', ' ')}.`);
      } else if (res.delivery_status === 'sent') {
        setMessage(`Invitation email sent to ${res.email}.`);
      } else {
        setMessage(`Invitation created for ${res.email}. Email delivery failed (${res.delivery_error || 'SMTP service unavailable'}). You can copy the invitation link below.`);
      }
      if (res.invite_url) {
        setCreatedInviteUrl(res.invite_url);
      }
      setEmail('');
      await refresh();
    } catch (e: any) {
      setError(e.message || 'Failed to send invitation or update role');
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateMemberRole(workspaceId: number, memberUserId: number, newRole: string) {
    setError('');
    setMessage('');
    try {
      const res = await request<any>(`/workspaces/${workspaceId}/members/${memberUserId}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role: newRole }),
      });
      setMessage(`Role for ${res.email} updated to ${res.role.replace('_', ' ')}.`);
      await refresh();
    } catch (err: any) {
      setError(err.message || 'Failed to update member role');
    }
  }

  async function handleRemoveMember(workspaceId: number, memberUserId: number, memberEmail: string) {
    if (!confirm(`Are you sure you want to remove ${memberEmail} from this workspace?`)) return;
    setError('');
    setMessage('');
    try {
      await request<any>(`/workspaces/${workspaceId}/members/${memberUserId}`, {
        method: 'DELETE',
      });
      setMessage(`Removed ${memberEmail} from workspace.`);
      await refresh();
    } catch (err: any) {
      setError(err.message || 'Failed to remove member');
    }
  }

  async function revoke(id: number) {
    if (!confirm('Are you sure you want to revoke this invitation?')) return;
    try {
      await request(`/invitations/${id}`, { method: 'DELETE' });
      await refresh();
      setMessage('Invitation revoked.');
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function resend(id: number) {
    setError('');
    setMessage('');
    try {
      const res = await post<any>(`/invitations/${id}/resend`);
      if (res.delivery_status === 'sent') {
        setMessage('Invitation email resent successfully.');
      } else {
        setMessage(`Email delivery failed (${res.delivery_error || 'SMTP unavailable'}). You can copy the link.`);
      }
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function copyInviteLink(id: number) {
    try {
      const res = await post<{ invite_url: string }>(`/invitations/${id}/link`);
      await navigator.clipboard.writeText(res.invite_url);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function createOrg() {
    const name = prompt('Organization name');
    if (!name) return;
    try {
      await post('/organizations', { name });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const canInvite = ['system_owner', 'system_admin'].includes(user.role) || workspaces.some((w) => w.role === 'owner' || w.role === 'organization_admin');

  return (
    <>
      <PageHeading
        eyebrow="PEOPLE & ACCESS"
        title="Share your server"
        description="Invite family, friends, or teammates to the workspaces you choose."
        action={<button className="button secondary" onClick={createOrg}><Plus size={16} /> New organization</button>}
      />
      <Message error={error} success={message} />

      {createdInviteUrl && (
        <div className="invite-alert warning" style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <strong>Manual Invitation Link</strong>
            <button
              className="button secondary"
              style={{ padding: '4px 8px', fontSize: '11px' }}
              onClick={async () => {
                await navigator.clipboard.writeText(createdInviteUrl);
                setCopiedId('new');
                setTimeout(() => setCopiedId(null), 2000);
              }}
            >
              {copiedId === 'new' ? <Check size={13} /> : <Copy size={13} />}
              {copiedId === 'new' ? 'Copied' : 'Copy link'}
            </button>
          </div>
          <p style={{ margin: '4px 0 0', fontSize: '11px' }}>
            Share this link directly with the recipient so they can register and join:
          </p>
          <div className="copy-link-box" style={{ marginTop: '6px' }}>
            <code>{createdInviteUrl}</code>
          </div>
        </div>
      )}

      <div className="people-layout">
        <section className="panel invite-panel">
          <div className="panel-heading">
            <span className="quick-icon lavender"><Users size={19} /></span>
            <div>
              <h2>Invite someone</h2>
              <p>They’ll verify their email and choose their own password.</p>
            </div>
          </div>
          {canInvite ? (
            <form className="invite-form" onSubmit={invite}>
              <label className="field">
                <span>Email address</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="name@example.com"
                />
              </label>
              <label className="field">
                <span>Workspace</span>
                <select value={workspace} onChange={(e) => setWorkspace(e.target.value)}>
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>{w.name}{w.kind === 'organization' ? ' (Organization)' : ''}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Access role</span>
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  {workspaces.find((w) => String(w.id) === String(workspace))?.kind === 'organization' && (
                    <option value="organization_admin">Workspace Admin</option>
                  )}
                  <option value="member">Member</option>
                  <option value="read_only">Read-only member</option>
                </select>
              </label>
              <button className="button primary full" disabled={busy}>
                <Plus size={16} /> {busy ? 'Creating invitation…' : 'Send invitation'}
              </button>
            </form>
          ) : (
            <p className="helper">You can create organizations and invite members from a workspace you administer.</p>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Pending invitations</h2>
              <p>Access can be revoked at any time.</p>
            </div>
            <span className="count-badge">{invitations.filter((i) => !i.revoked).length}</span>
          </div>
          {invitations.length ? (
            <div className="invite-list">
              {invitations.map((i) => (
                <div className="invite-row" key={i.id}>
                  <span className="profile-avatar pale">{i.email.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <b>{i.email}</b>
                      {i.revoked ? (
                        <span className="status-badge revoked">Revoked</span>
                      ) : i.delivery_status === 'failed' ? (
                        <span className="status-badge failed" title={i.delivery_error || 'SMTP delivery failed'}>
                          <AlertTriangle size={11} /> Email failed
                        </span>
                      ) : (
                        <span className="status-badge sent">
                          <CheckCircle size={11} /> Email sent
                        </span>
                      )}
                    </div>
                    <small>{i.role.replace('_', ' ')} · expires {new Date(i.expires_at).toLocaleDateString()}</small>
                  </div>
                  <div className="invite-actions">
                    {!i.revoked ? (
                      <>
                        <button
                          className="invite-btn"
                          title="Copy invitation link"
                          onClick={() => copyInviteLink(i.id)}
                        >
                          {copiedId === i.id ? <Check size={12} /> : <Copy size={12} />}
                          {copiedId === i.id ? 'Copied' : 'Copy link'}
                        </button>
                        <button
                          className="invite-btn"
                          title="Retry sending email"
                          onClick={() => resend(i.id)}
                        >
                          <RefreshCw size={12} /> Retry
                        </button>
                        <button className="invite-btn danger" onClick={() => revoke(i.id)}>
                          Revoke
                        </button>
                      </>
                    ) : (
                      <span className="revoked-label">Revoked</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-small">
              <Users size={21} />
              <b>No invitations yet</b>
              <span>Invited people will show up here.</span>
            </div>
          )}
        </section>
      </div>

      <section className="panel workspace-panel">
        <div className="panel-heading">
          <div>
            <h2>Your workspaces & members</h2>
            <p>Each workspace has its own membership and access roles.</p>
          </div>
        </div>
        {workspaces.map((w) => {
          const members = workspaceMembers[w.id] || [];
          const canManage = ['system_owner', 'system_admin'].includes(user.role) || ['owner', 'organization_admin'].includes(w.role);
          return (
            <div key={w.id} style={{ borderTop: '1px solid var(--border-light)', paddingTop: '12px', marginTop: '12px' }}>
              <div className="workspace-row" style={{ borderTop: 'none', padding: '0 0 8px 0' }}>
                <span className="workspace-avatar">{w.name[0]}</span>
                <div>
                  <b>{w.name}</b>
                  <small>{w.kind} workspace</small>
                </div>
                <span className="role-pill">{w.role.replace('_', ' ')}</span>
              </div>

              {members.length > 0 && (
                <div style={{ marginLeft: '12px', marginTop: '8px', display: 'grid', gap: '6px' }}>
                  <small style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '10px', textTransform: 'uppercase' }}>
                    Workspace Members ({members.length})
                  </small>
                  {members.map((m) => (
                    <div
                      key={m.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 12px',
                        background: 'var(--bg-elevated)',
                        borderRadius: '6px',
                        fontSize: '11px',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="profile-avatar pale" style={{ width: '22px', height: '22px', fontSize: '10px' }}>
                          {m.full_name.charAt(0).toUpperCase()}
                        </span>
                        <div>
                          <strong>{m.full_name}</strong>
                          <span style={{ color: 'var(--text-muted)', marginLeft: '6px' }}>{m.email}</span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {canManage && !m.is_owner && m.id !== user.id ? (
                          <>
                            <select
                              value={m.role}
                              onChange={(e) => handleUpdateMemberRole(w.id, m.id, e.target.value)}
                              className="member-role-select"
                              aria-label={`Role for ${m.full_name}`}
                            >
                              {w.kind === 'organization' && (
                                <option value="organization_admin">Workspace Admin</option>
                              )}
                              <option value="member">Member</option>
                              <option value="read_only">Read-only member</option>
                            </select>
                            <button
                              className="invite-btn danger"
                              style={{ padding: '3px 8px', fontSize: '10px' }}
                              onClick={() => handleRemoveMember(w.id, m.id, m.email)}
                              title="Remove member"
                            >
                              Remove
                            </button>
                          </>
                        ) : (
                          <span className="role-pill">{m.role.replace('_', ' ')}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </section>
    </>
  );
}

function SettingsPage({ user }: { user: User }) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [current, setCurrent] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [policy, setPolicy] = useState('open');
  const [policyMessage, setPolicyMessage] = useState('');
  const isAdmin = ['system_owner', 'system_admin'].includes(user.role);

  useEffect(() => {
    if (isAdmin) {
      request<{ policy: string }>('/auth/registration-policy')
        .then((res) => setPolicy(res.policy))
        .catch(() => {});
    }
  }, [isAdmin]);

  async function updatePolicy(newPolicy: string) {
    try {
      await request('/auth/registration-policy', {
        method: 'PUT',
        body: JSON.stringify({ policy: newPolicy }),
      });
      setPolicy(newPolicy);
      setPolicyMessage(`Registration policy updated to: ${newPolicy === 'open' ? 'Open registration' : 'Invitation only'}`);
      setTimeout(() => setPolicyMessage(''), 3000);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function change(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    try {
      await post('/auth/password', { current_password: current, new_password: password });
      setMessage('Password changed. Sign in again with your new password.');
      setError('');
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <>
      <PageHeading eyebrow="SERVER SETTINGS" title="Settings & storage" description="Manage storage destinations, accounts, and server security." />
      <Message error={error} success={message} />
      {policyMessage && <div className="notice notice-success" style={{ marginBottom: '16px' }}>{policyMessage}</div>}
      <div style={{ marginBottom: '24px' }}>
        <StorageManagement isAdmin={isAdmin} />
      </div>

      <div className="settings-grid">
        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon lavender"><Shield size={18} /></span>
            <div>
              <h2>Change password</h2>
              <p>Choose a unique password with at least 12 characters.</p>
            </div>
          </div>
          <form className="form-stack settings-form" onSubmit={change}>
            <Field label="Current password" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
            <Field label="New password" type="password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} required />
            <Field label="Confirm new password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            <button className="button primary">Update password</button>
          </form>
        </section>

        {isAdmin && (
          <section className="panel">
            <div className="panel-heading">
              <span className="quick-icon peach"><Users size={18} /></span>
              <div>
                <h2>Registration Policy</h2>
                <p>Control who can create an account on your server.</p>
              </div>
            </div>
            <div style={{ display: 'grid', gap: '14px', padding: '6px 0' }}>
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="policy_choice"
                  value="open"
                  checked={policy === 'open'}
                  onChange={() => updatePolicy('open')}
                  style={{ marginTop: '3px' }}
                />
                <div>
                  <strong>Open registration</strong>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    Anyone on your local network or Tailnet can sign up with email OTP verification.
                  </div>
                </div>
              </label>

              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="policy_choice"
                  value="invitation_only"
                  checked={policy === 'invitation_only'}
                  onChange={() => updatePolicy('invitation_only')}
                  style={{ marginTop: '3px' }}
                />
                <div>
                  <strong>Invitation only (Recommended)</strong>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    Only people with a valid, unexpired administrator invitation token can register.
                  </div>
                </div>
              </label>
            </div>
          </section>
        )}

        <section className="panel">
          <div className="panel-heading">
            <span className="quick-icon mint"><Shield size={18} /></span>
            <div>
              <h2>Interface Theme</h2>
              <p>Choose your preferred appearance or follow your system.</p>
            </div>
          </div>
          <ThemeSelector />
        </section>

        <section className="panel account-panel">
          <div className="panel-heading">
            <span className="profile-avatar">{user.name[0]}</span>
            <div>
              <h2>Your account</h2>
              <p>Account details and access role.</p>
            </div>
          </div>
          <div className="account-details">
            <div><small>NAME</small><b>{user.name}</b></div>
            <div><small>EMAIL</small><b>{user.email}</b></div>
            <div><small>USERNAME</small><b>{user.username}</b></div>
            <div><small>ROLE</small><b>{user.role.replace('_', ' ')}</b></div>
          </div>
        </section>
      </div>
    </>
  );
}

function AcceptInvitation({ user }: { user: User | null }) {
  const [params] = useSearchParams();
  const [message, setMessage] = useState('Accept the workspace invitation sent to your email.');
  const [error, setError] = useState('');
  const token = params.get('token') || params.get('invite');

  useEffect(() => {
    if (!user || !token) return;
    post<{ role: string }>('/invitations/accept', { token })
      .then((result) => setMessage(`Invitation accepted. You now have ${result.role} access.`))
      .catch((e) => setError((e as Error).message));
  }, [user?.id, token]);

  if (!user) {
    return (
      <AuthFrame title="Workspace invitation" subtitle="Sign in with the invited email or create an account to join this workspace.">
        <div className="form-stack">
          <Message error={token ? undefined : 'Invitation link is missing its token.'} />
          <Link className="button primary full" to={`/signup?token=${encodeURIComponent(token || '')}&invite=${encodeURIComponent(token || '')}`}>
            Create account and accept <ArrowRight size={16} />
          </Link>
          <Link className="button secondary full" to={`/login?invite=${encodeURIComponent(token || '')}&token=${encodeURIComponent(token || '')}`}>
            Sign in and accept
          </Link>
        </div>
      </AuthFrame>
    );
  }

  return (
    <div className="auth-card standalone">
      <span className="quick-icon lavender"><Users /></span>
      <h2>Workspace invitation</h2>
      <p>{message}</p>
      <Message error={error} />
    </div>
  );
}

export default App;
