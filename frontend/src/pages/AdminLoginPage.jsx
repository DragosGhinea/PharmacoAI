import { useState } from 'react';

export default function AdminLoginPage({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');

    try {
      await onLogin({ username: username.trim(), password });
    } catch (loginError) {
      if (loginError instanceof Error) {
        setError(loginError.message);
      } else {
        setError('Login failed');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <section className="px-8 py-20 bg-surface-container-low min-h-[70vh]">
        <div className="max-w-xl mx-auto bg-surface-container-lowest rounded-3xl p-10 border border-outline-variant/40 shadow-sm">
          <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Admin Access</p>
          <h2 className="text-4xl text-primary font-bold mb-4">Sign In</h2>
          <p className="text-sm text-on-surface-variant mb-8">
            Please log in with your admin credentials to access user management.
          </p>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Username</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
              />
            </label>

            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Password</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>

            {error && <p className="text-sm font-semibold text-error">{error}</p>}

            <button
              className="w-full bg-primary-container text-white rounded-2xl py-3 text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform disabled:opacity-70"
              type="submit"
              disabled={busy}
            >
              {busy ? 'Signing In...' : 'Log In'}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
