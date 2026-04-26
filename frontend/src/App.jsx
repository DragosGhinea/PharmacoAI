import { useState } from 'react';

import { getMyUser, loginUser } from './api/usersApi';
import AdminUsersPanel from './components/AdminUsersPanel';
import SiteFooter from './components/SiteFooter';
import TopNav from './components/TopNav';
import AdminLoginPage from './pages/AdminLoginPage';
import LandingPageContent from './pages/LandingPageContent';
import PharmacistAccountPage from './pages/PharmacistAccountPage';
import PharmacistChatPage from './pages/PharmacistChatPage';
import PharmacistLoginPage from './pages/PharmacistLoginPage';
import {
  clearAdminSession,
  clearPharmacistSession,
  persistAdminSession,
  persistPharmacistSession,
  readAdminSession,
  readPharmacistSession,
} from './utils/sessionStorage';

const ADMIN_LOGIN_EMAIL = 'admin@pharmacoai.local';

export default function App() {
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '/';
  const isAdminRoute = pathname.startsWith('/admin');
  const isPharmacistRoute = pathname.startsWith('/pharmacist');
  const isPharmacistAccountRoute = pathname.startsWith('/pharmacist/account');
  const isPharmacistChatRoute = pathname.startsWith('/pharmacist/chat') || pathname.startsWith('/pharmacist/agent');
  const isPharmacistRootRoute = pathname === '/pharmacist';
  const currentRoute = isAdminRoute ? 'admin' : isPharmacistRoute ? 'pharmacist' : 'landing';

  const [adminSession, setAdminSession] = useState(() => readAdminSession());
  const [pharmacistSession, setPharmacistSession] = useState(() => readPharmacistSession());

  async function handleAdminLogin({ username, password }) {
    const email = username.includes('@') ? username : ADMIN_LOGIN_EMAIL;
    const user = await loginUser(email, password);

    if (user.role !== 'admin') {
      throw new Error('This account is not an admin account');
    }

    const session = {
      userId: user.user_id,
      username,
      email: user.email,
    };

    persistAdminSession(session);
    setAdminSession(session);
  }

  function handleLogout() {
    clearAdminSession();
    setAdminSession(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  }

  async function handlePharmacistLogin({ email, password }) {
    const user = await loginUser(email, password);

    if (user.role !== 'pharmacist') {
      throw new Error('This account is not a pharmacist account');
    }

    const session = {
      userId: user.user_id,
      email: user.email,
      fullName: user.full_name,
      tier: user.tier,
    };

    persistPharmacistSession(session);
    setPharmacistSession(session);

    if (typeof window !== 'undefined') {
      window.location.href = '/pharmacist/chat';
    }
  }

  function handlePharmacistLogout() {
    clearPharmacistSession();
    setPharmacistSession(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  }

  async function refreshPharmacistSession() {
    if (!pharmacistSession?.userId) {
      return;
    }

    const user = await getMyUser(pharmacistSession.userId);
    const session = {
      userId: user.id,
      email: user.email,
      fullName: user.full_name,
      tier: user.tier,
    };
    persistPharmacistSession(session);
    setPharmacistSession(session);
  }

  return (
    <div className="text-on-surface selection:bg-secondary-container selection:text-on-secondary-container">
      <TopNav
        currentRoute={currentRoute}
        isAdminAuthenticated={Boolean(adminSession)}
        isPharmacistAuthenticated={Boolean(pharmacistSession)}
        onAdminLogout={handleLogout}
      />
      {isAdminRoute ? (
        adminSession ? (
          <main>
            <AdminUsersPanel adminId={adminSession.userId} />
          </main>
        ) : (
          <AdminLoginPage onLogin={handleAdminLogin} />
        )
      ) : isPharmacistRoute ? (
        pharmacistSession ? (
          isPharmacistAccountRoute ? (
            <PharmacistAccountPage
              pharmacistSession={pharmacistSession}
              onLogout={handlePharmacistLogout}
              onSessionRefresh={refreshPharmacistSession}
            />
          ) : isPharmacistChatRoute || isPharmacistRootRoute ? (
            <PharmacistChatPage pharmacistSession={pharmacistSession} />
          ) : (
            <PharmacistChatPage pharmacistSession={pharmacistSession} />
          )
        ) : (
          <PharmacistLoginPage onLogin={handlePharmacistLogin} />
        )
      ) : (
        <LandingPageContent />
      )}
      <SiteFooter />
    </div>
  );
}
