import { useEffect, useMemo, useState } from 'react';

import { createUser, deleteUser, listTiers, listUsers, updateUser } from '../api/usersApi';

const EMPTY_FORM = {
  email: '',
  password: '',
  full_name: '',
  tier: 'free',
  role: 'pharmacist',
  is_active: true,
};

function toErrorMessage(error) {
  if (!error) {
    return 'Unexpected error';
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  if (typeof error === 'object') {
    return JSON.stringify(error);
  }
  return String(error);
}

export default function AdminUsersPanel({ adminId }) {
  const [users, setUsers] = useState([]);
  const [tiers, setTiers] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const tierOptions = useMemo(
    () => tiers.map((tierData) => ({ label: tierData.tier.toUpperCase(), value: tierData.tier })),
    [tiers]
  );

  async function loadData() {
    if (!adminId) {
      setError('Admin session missing. Please log in again.');
      return;
    }

    setBusy(true);
    setError('');
    try {
      const [usersPayload, tiersPayload] = await Promise.all([listUsers(adminId), listTiers()]);
      setUsers(usersPayload);
      setTiers(tiersPayload);
    } catch (loadError) {
      setError(toErrorMessage(loadError));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [adminId]);

  async function handleCreateUser(event) {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    setError('');

    try {
      const payload = {
        ...form,
        email: form.email.trim(),
        full_name: form.full_name.trim(),
      };
      await createUser(adminId, payload);
      setMessage('User created successfully.');
      setForm(EMPTY_FORM);
      await loadData();
    } catch (createError) {
      setError(toErrorMessage(createError));
    } finally {
      setBusy(false);
    }
  }

  async function handleTierChange(userId, tier) {
    setBusy(true);
    setMessage('');
    setError('');
    try {
      await updateUser(adminId, userId, { tier });
      setMessage('Tier updated.');
      await loadData();
    } catch (updateError) {
      setError(toErrorMessage(updateError));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteUser(userId) {
    setBusy(true);
    setMessage('');
    setError('');
    try {
      await deleteUser(adminId, userId);
      setMessage('User deleted.');
      await loadData();
    } catch (deleteError) {
      setError(toErrorMessage(deleteError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="px-8 py-20 bg-surface-container-low">
      <div className="max-w-7xl mx-auto grid lg:grid-cols-12 gap-8">
        <div className="lg:col-span-4 bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/40 shadow-sm">
          <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-2">Admin Panel</p>
          <h2 className="text-3xl text-primary font-bold mb-3">Create Pharmacist Users</h2>
          <p className="text-sm text-on-surface-variant mb-8">
            Keep onboarding internal teams simple while assigning feature access by tier.
          </p>

          <form className="space-y-4" onSubmit={handleCreateUser}>
            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Email</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                value={form.email}
                onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                required
              />
            </label>

            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Temporary Password</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                type="password"
                value={form.password}
                onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                minLength={6}
                required
              />
            </label>

            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Full Name</span>
              <input
                className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                value={form.full_name}
                onChange={(event) => setForm((current) => ({ ...current, full_name: event.target.value }))}
                required
              />
            </label>

            <label className="block">
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Tier</span>
              <div className="relative mt-2">
                <select
                  className="block w-full appearance-none rounded-xl border-outline-variant/60 bg-surface px-3 py-2 pr-10 text-sm"
                  value={form.tier}
                  onChange={(event) => setForm((current) => ({ ...current, tier: event.target.value }))}
                >
                  {tierOptions.length === 0 && <option value="free">FREE</option>}
                  {tierOptions.map((tier) => (
                    <option key={tier.value} value={tier.value}>
                      {tier.label}
                    </option>
                  ))}
                </select>
                <span className="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-on-surface-variant">
                  keyboard_arrow_down
                </span>
              </div>
            </label>

            <button
              className="w-full bg-primary-container text-white rounded-2xl py-3 text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform"
              type="submit"
              disabled={busy}
            >
              {busy ? 'Working...' : 'Create User'}
            </button>
          </form>
        </div>

        <div className="lg:col-span-8 bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/40 shadow-sm">
          <div className="flex flex-wrap justify-between items-center gap-4 mb-6">
            <div>
              <p className="text-xs uppercase font-bold tracking-[0.2em] text-secondary mb-1">Team Access</p>
              <h3 className="text-2xl text-primary font-bold">Current Users</h3>
            </div>
            <button
              className="px-4 py-2 rounded-xl text-sm font-bold bg-surface-container-low hover:bg-surface-container-high transition-colors"
              type="button"
              onClick={loadData}
              disabled={busy}
            >
              Refresh
            </button>
          </div>

          {message && <p className="mb-4 text-sm font-semibold text-secondary">{message}</p>}
          {error && <p className="mb-4 text-sm font-semibold text-error">{error}</p>}

          <div className="space-y-3">
            {users.map((user) => (
              <article
                key={user.id}
                className="rounded-2xl border border-outline-variant/40 bg-surface-container-low px-4 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4"
              >
                <div>
                  <h4 className="text-primary font-bold text-lg">{user.full_name}</h4>
                  <p className="text-sm text-on-surface-variant">{user.email}</p>
                  <p className="text-xs text-on-surface-variant mt-1">
                    {user.role.toUpperCase()} · {user.monthly_messages_used}/{user.monthly_message_limit} messages used
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <div className="relative">
                    <select
                      className="block appearance-none rounded-xl border-outline-variant/60 bg-surface px-3 py-2 pr-10 text-sm"
                      value={user.tier}
                      onChange={(event) => handleTierChange(user.id, event.target.value)}
                      disabled={busy || user.role === 'admin'}
                    >
                      {tierOptions.map((tier) => (
                        <option key={tier.value} value={tier.value}>
                          {tier.label}
                        </option>
                      ))}
                    </select>
                    <span className="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-on-surface-variant">
                      keyboard_arrow_down
                    </span>
                  </div>
                  <button
                    className="rounded-xl px-3 py-2 text-sm font-bold text-error hover:bg-error/10 transition-colors disabled:opacity-40"
                    type="button"
                    disabled={busy || user.role === 'admin'}
                    onClick={() => handleDeleteUser(user.id)}
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}

            {!busy && users.length === 0 && (
              <div className="rounded-2xl border border-dashed border-outline-variant/50 px-4 py-6 text-sm text-on-surface-variant">
                No users found. Create your first pharmacist account.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
