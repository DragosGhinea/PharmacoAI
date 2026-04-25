import { useState } from 'react';

import { changeMyPassword } from '../api/usersApi';

export default function PharmacistAccountPage({ pharmacistSession, onLogout, onSessionRefresh }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function handlePasswordChange(event) {
    event.preventDefault();
    setMessage('');
    setError('');

    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match');
      return;
    }

    setBusy(true);
    try {
      await changeMyPassword(pharmacistSession.userId, currentPassword, newPassword);
      setMessage('Password updated successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      await onSessionRefresh();
    } catch (passwordError) {
      if (passwordError instanceof Error) {
        setError(passwordError.message);
      } else {
        setError('Could not update password');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <section className="px-8 py-20 bg-surface-container-low min-h-[70vh]">
        <div className="max-w-4xl mx-auto grid md:grid-cols-2 gap-6">
          <div className="bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/40 shadow-sm">
            <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Account</p>
            <h2 className="text-3xl text-primary font-bold mb-4">Your Profile</h2>
            <p className="text-sm text-on-surface-variant mb-6">Manage your session and account security settings.</p>

            <div className="space-y-3 mb-6">
              <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
                <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Name</p>
                <p className="text-primary font-semibold">{pharmacistSession.fullName}</p>
              </div>
              <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
                <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Email</p>
                <p className="text-primary font-semibold break-all">{pharmacistSession.email}</p>
              </div>
              <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
                <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Tier</p>
                <p className="text-primary font-semibold uppercase">{pharmacistSession.tier}</p>
              </div>
            </div>

            <div className="flex gap-3">
              <a className="px-4 py-2 rounded-xl text-sm font-bold bg-surface-container-low hover:bg-surface-container-high transition-colors" href="/pharmacist/chat">
                Back to Agent
              </a>
              <button
                className="px-4 py-2 rounded-xl text-sm font-bold text-error hover:bg-error/10 transition-colors"
                type="button"
                onClick={onLogout}
              >
                Log Out
              </button>
            </div>
          </div>

          <div className="bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/40 shadow-sm">
            <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Security</p>
            <h3 className="text-2xl text-primary font-bold mb-4">Change Password</h3>

            <form className="space-y-4" onSubmit={handlePasswordChange}>
              <label className="block">
                <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Current Password</span>
                <input
                  className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                  type="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  required
                />
              </label>

              <label className="block">
                <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">New Password</span>
                <input
                  className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  minLength={6}
                  required
                />
              </label>

              <label className="block">
                <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Confirm New Password</span>
                <input
                  className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  minLength={6}
                  required
                />
              </label>

              {message && <p className="text-sm font-semibold text-secondary">{message}</p>}
              {error && <p className="text-sm font-semibold text-error">{error}</p>}

              <button
                className="w-full bg-primary-container text-white rounded-2xl py-3 text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform disabled:opacity-70"
                type="submit"
                disabled={busy}
              >
                {busy ? 'Updating...' : 'Update Password'}
              </button>
            </form>
          </div>
        </div>
      </section>
    </main>
  );
}
