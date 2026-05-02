import { useEffect, useState } from 'react';

import { changeMyPassword, createAddonCheckout, getMyUser, listAddonPacks } from '../api/usersApi';

const FALLBACK_ADDON_PACKS = {
  '5':  { count: 5,  price_cents: 99 },
  '10': { count: 10, price_cents: 199 },
  '50': { count: 50, price_cents: 899 },
};

function formatPrice(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function PharmacistAccountPage({ pharmacistSession, onLogout, onSessionRefresh }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [profile, setProfile] = useState(null);
  const [addonPacks, setAddonPacks] = useState(FALLBACK_ADDON_PACKS);
  const [addonBusy, setAddonBusy] = useState('');
  const [addonError, setAddonError] = useState('');

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const [me, packs] = await Promise.all([
          getMyUser(pharmacistSession.userId),
          listAddonPacks().catch(() => FALLBACK_ADDON_PACKS),
        ]);
        if (mounted) {
          setProfile(me);
          setAddonPacks(packs || FALLBACK_ADDON_PACKS);
        }
      } catch (loadError) {
        if (mounted && loadError instanceof Error) {
          setError(loadError.message);
        }
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [pharmacistSession.userId]);

  async function handleBuyAddon(packId) {
    setAddonError('');
    setAddonBusy(packId);
    try {
      const response = await createAddonCheckout(pharmacistSession.userId, packId);
      if (typeof window !== 'undefined' && response?.checkout_url) {
        window.location.href = response.checkout_url;
      }
    } catch (checkoutError) {
      if (checkoutError instanceof Error) {
        setAddonError(checkoutError.message);
      } else {
        setAddonError('Could not start add-on checkout');
      }
    } finally {
      setAddonBusy('');
    }
  }

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

  const addonPackEntries = Object.entries(addonPacks).sort(
    (a, b) => (a[1]?.count ?? 0) - (b[1]?.count ?? 0),
  );
  const usedMessages = profile?.monthly_messages_used ?? 0;
  const monthlyLimit = profile?.monthly_message_limit ?? 0;
  const addonBalance = profile?.addon_messages ?? 0;
  const remainingThisMonth = monthlyLimit > 0 ? Math.max(monthlyLimit - usedMessages, 0) : 0;

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

        <div id="addons" className="max-w-4xl mx-auto mt-6 bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/40 shadow-sm">
          <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Billing</p>
          <h3 className="text-2xl text-primary font-bold mb-2">Buy More Messages</h3>
          <p className="text-sm text-on-surface-variant mb-6">
            Purchase additional AI messages on top of your monthly tier allowance. Add-on messages do not expire and are used after the monthly allowance is exhausted.
          </p>

          <div className="grid sm:grid-cols-3 gap-3 mb-6">
            <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
              <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Tier</p>
              <p className="text-primary font-semibold uppercase">{profile?.tier ?? pharmacistSession.tier}</p>
            </div>
            <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
              <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">This month</p>
              <p className="text-primary font-semibold">{usedMessages}/{monthlyLimit || '—'} used</p>
              {monthlyLimit > 0 && (
                <p className="text-xs text-on-surface-variant mt-1">{remainingThisMonth} remaining</p>
              )}
            </div>
            <div className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-4">
              <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Add-on balance</p>
              <p className="text-primary font-semibold">{addonBalance} messages</p>
            </div>
          </div>

          {addonError && <p className="text-sm font-semibold text-error mb-4">{addonError}</p>}

          <div className="grid sm:grid-cols-3 gap-4">
            {addonPackEntries.map(([packId, info]) => (
              <div key={packId} className="rounded-2xl border border-outline-variant/40 bg-surface-container-low p-5 flex flex-col">
                <p className="text-xs uppercase tracking-wider text-on-surface-variant mb-1">Pack</p>
                <p className="text-3xl text-primary font-bold">{info.count}</p>
                <p className="text-xs text-on-surface-variant mb-3">messages</p>
                <p className="text-lg text-primary font-semibold mb-4">{formatPrice(info.price_cents)}</p>
                <button
                  type="button"
                  onClick={() => handleBuyAddon(packId)}
                  disabled={addonBusy === packId}
                  className="mt-auto px-4 py-2 rounded-xl text-sm font-bold bg-primary-container text-white disabled:opacity-70"
                >
                  {addonBusy === packId ? 'Redirecting...' : 'Buy now'}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
