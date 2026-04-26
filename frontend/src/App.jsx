import { useState, useEffect } from 'react';

import { confirmSubscription, createSubscriptionCheckout, getMyUser, loginUser } from './api/usersApi';
import AdminUsersPanel from './components/AdminUsersPanel';
import SiteFooter from './components/SiteFooter';
import TopNav from './components/TopNav';
import AdminLoginPage from './pages/AdminLoginPage';
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

const BILLING_SESSION_KEY = 'pharmacoai_billing_session';
const ADMIN_LOGIN_EMAIL = 'admin@pharmacoai.local';

function readBillingSession() {
  if (typeof window === 'undefined') {
    return null;
  }

  const raw = window.localStorage.getItem(BILLING_SESSION_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw);
    if (parsed?.userId && parsed?.email) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

function persistBillingSession(session) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(BILLING_SESSION_KEY, JSON.stringify(session));
}

function clearBillingSession() {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(BILLING_SESSION_KEY);
}

const SUBSCRIPTION_PLANS = [
  {
    tier: 'free',
    name: 'Free',
    priceLabel: '$0',
    cadence: '/month',
    tagline: 'For solo pharmacies getting started',
    userLimit: '1 admin user',
    messageLimit: '150 messages/month',
    agents: ['Drug Explainer'],
    cardClass: 'bg-white border-slate-200',
    buttonClass: 'bg-slate-900 text-white hover:bg-slate-700',
  },
  {
    tier: 'pro',
    name: 'Pro',
    priceLabel: '$99',
    cadence: '/month',
    tagline: 'For pharmacies scaling clinical throughput',
    userLimit: 'Up to 8 users',
    messageLimit: '3,000 messages/month',
    agents: ['Drug Explainer', 'Ingredient Analyst', 'Summary Agent'],
    cardClass: 'bg-emerald-50 border-emerald-300',
    buttonClass: 'bg-emerald-700 text-white hover:bg-emerald-600',
  },
  {
    tier: 'ultimate',
    name: 'Ultimate',
    priceLabel: '$299',
    cadence: '/month',
    tagline: 'For enterprise pharmacies with large teams',
    userLimit: 'Up to 50 users',
    messageLimit: '20,000 messages/month',
    agents: ['Drug Explainer', 'Ingredient Analyst', 'Summary Agent'],
    cardClass: 'bg-amber-50 border-amber-300',
    buttonClass: 'bg-amber-700 text-white hover:bg-amber-600',
  },
];

function resolveSelectedPlan() {
  if (typeof window === 'undefined') {
    return SUBSCRIPTION_PLANS[1];
  }

  const params = new URLSearchParams(window.location.search);
  const requestedTier = params.get('plan') ?? 'pro';
  return SUBSCRIPTION_PLANS.find((plan) => plan.tier === requestedTier) ?? SUBSCRIPTION_PLANS[1];
}

function LandingPageContent({ checkoutSession }) {
  const checkoutStatus =
    typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('checkout') : null;
  const [accountProfile, setAccountProfile] = useState(null);

  useEffect(() => {
    let mounted = true;
    async function loadProfile() {
      if (!checkoutSession?.userId) {
        setAccountProfile(null);
        return;
      }

      try {
        const profile = await getMyUser(checkoutSession.userId);
        if (mounted) {
          setAccountProfile(profile);
        }
      } catch {
        if (mounted) {
          setAccountProfile(null);
        }
      }
    }

    loadProfile();
    return () => {
      mounted = false;
    };
  }, [checkoutSession?.userId]);

  function goToSignup(tier) {
    if (typeof window !== 'undefined') {
      window.location.href = `/subscribe?plan=${tier}`;
    }
  }

  const currentTier = accountProfile?.tier;

  return (
    <main>
      <section className="relative pt-24 pb-32 px-8 overflow-hidden">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-12 gap-16 items-center">
          <div className="lg:col-span-7 z-10">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-secondary-container/30 text-secondary rounded-full mb-6">
              <span className="material-symbols-outlined text-sm">auto_awesome</span>
              <span className="text-xs font-bold uppercase tracking-wider">Next-Gen Clinical Intelligence</span>
            </div>
            <h1 className="text-5xl md:text-7xl font-bold text-primary mb-8 leading-[1.1]">
              Intelligent Pharmaceutical Advice, <span className="text-secondary italic">Tailored</span> for Your Pharmacy.
            </h1>
            <p className="text-lg text-on-surface-variant mb-10 max-w-2xl leading-relaxed">
              Leverage proprietary machine learning to transform massive clinical databases into actionable insights. Accuracy at the speed of thought.
            </p>
            <div className="flex flex-wrap gap-4">
              <button className="px-8 py-4 bg-primary-container text-white rounded-2xl font-bold text-lg flex items-center gap-2 shadow-lg shadow-primary-container/20 hover:scale-[0.98] transition-all" type="button">
                Request a Demo
                <span className="material-symbols-outlined">arrow_forward</span>
              </button>
              <a
                className="px-8 py-4 bg-surface-container-low text-primary rounded-2xl font-bold text-lg hover:bg-surface-container-high transition-colors"
                href="/admin"
              >
                Manage Users
              </a>
            </div>
          </div>
          <div className="lg:col-span-5 relative">
            <div className="aspect-square rounded-3xl bg-surface-container-lowest shadow-2xl overflow-hidden relative border border-outline-variant/10">
              <img
                alt="Laboratory technology"
                className="object-cover w-full h-full opacity-90"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuDZJHRgEl-J6hcTFzy6K9mwe1LFwdfgWP-k_YG2DLx36F1VuPsMuVx7zhOSkDwAJB5PxwjMww_0Qh2SL0WzLmFcu0e2fKk7l-z7Z6XG6UAhnmp59TkvKEmkDGGtrTB-cNaFLincythus-B-uPCdbO7YjRMJ6w2Ky447eIp6h8q-KDmHzZRVBq-GR6AIQja_8lnpBJCFzxIj5xs1QI2bh8gQnBVOwTn_z1ADRWrWFR4O_LlBOziOvKRgPiGnGwNyKsHNlBgqY9aquE8"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-primary/20 to-transparent"></div>
              <div className="absolute bottom-6 left-6 right-6 bg-surface-container-lowest/80 backdrop-blur-xl p-4 rounded-2xl border-l-4 border-secondary flex items-start gap-3 shadow-xl">
                <span className="material-symbols-outlined text-secondary">verified_user</span>
                <div>
                  <p className="text-xs font-bold text-primary uppercase tracking-tighter">AI Verification Success</p>
                  <p className="text-sm text-on-surface-variant">Drug interaction database updated 2m ago.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="absolute top-0 right-0 -z-10 w-1/3 h-full bg-gradient-to-l from-secondary-container/10 to-transparent blur-3xl"></div>
      </section>

      <section className="py-24 px-8 bg-surface-container-low">
        <div className="max-w-7xl mx-auto">
          <div className="mb-16">
            <h2 className="text-4xl font-bold text-primary mb-4">The Clinical Edge</h2>
            <p className="text-on-surface-variant max-w-xl">
              Precision-engineered tools designed to automate complex pharmaceutical workflows.
            </p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2 bg-surface-container-lowest p-10 rounded-3xl shadow-sm border-t-4 border-secondary flex flex-col justify-between group">
              <div>
                <div className="w-12 h-12 bg-surface-container-low rounded-xl flex items-center justify-center mb-6 group-hover:bg-secondary-container transition-colors">
                  <span className="material-symbols-outlined text-secondary">database</span>
                </div>
                <h3 className="text-3xl font-bold text-primary mb-4">Automated Clinical Intelligence</h3>
                <p className="text-on-surface-variant text-lg leading-relaxed max-w-lg">
                  Our autonomous agents continuously scrape globally recognized public databases and academic journals, extracting critical drug information with near-zero latency.
                </p>
              </div>
              <div className="mt-12 flex gap-4">
                <div className="px-4 py-2 bg-surface-container-low rounded-lg text-xs font-bold text-on-surface-variant">Live Scraping</div>
                <div className="px-4 py-2 bg-surface-container-low rounded-lg text-xs font-bold text-on-surface-variant">NLP Extraction</div>
                <div className="px-4 py-2 bg-surface-container-low rounded-lg text-xs font-bold text-on-surface-variant">Validation Engine</div>
              </div>
            </div>
            <div className="bg-primary text-on-primary p-10 rounded-3xl shadow-sm flex flex-col justify-center relative overflow-hidden">
              <div className="relative z-10">
                <span className="material-symbols-outlined text-secondary-fixed mb-6 text-4xl">psychology</span>
                <h3 className="text-2xl font-bold mb-4">Reasoning Engine</h3>
                <p className="text-primary-fixed-dim text-sm leading-relaxed">
                  Beyond simple search, our AI reasons through contraindications and dosage efficacy in real-time.
                </p>
              </div>
              <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-secondary/20 rounded-full blur-3xl"></div>
            </div>
            <div className="bg-surface-container-lowest p-10 rounded-3xl shadow-sm flex flex-col justify-between group">
              <div>
                <div className="w-12 h-12 bg-surface-container-low rounded-xl flex items-center justify-center mb-6 group-hover:bg-secondary-container transition-colors">
                  <span className="material-symbols-outlined text-secondary">medication</span>
                </div>
                <h3 className="text-2xl font-bold text-primary mb-4">Tailored Recommendations</h3>
                <p className="text-on-surface-variant text-sm leading-relaxed">
                  Personalized drug suggestions based on specific patient demographics, history, and real-time biometric inputs.
                </p>
              </div>
              <a className="mt-8 text-secondary font-bold text-sm flex items-center gap-2" href="#">
                Learn more
                <span className="material-symbols-outlined text-xs">open_in_new</span>
              </a>
            </div>
            <div className="md:col-span-2 bg-surface-container-lowest p-10 rounded-3xl shadow-sm flex flex-col md:flex-row gap-10 items-center overflow-hidden">
              <div className="flex-1">
                <h3 className="text-2xl font-bold text-primary mb-4">Interoperable API Design</h3>
                <p className="text-on-surface-variant text-sm leading-relaxed mb-6">
                  Integrate our intelligence into your existing EHR or pharmacy management system with ease. Our drug database API is built for high-performance enterprise applications.
                </p>
                <button className="text-primary font-bold text-sm underline underline-offset-4 decoration-secondary decoration-2" type="button">
                  View API Documentation
                </button>
              </div>
              <div className="flex-1 w-full bg-surface-container-low rounded-2xl p-6 font-mono text-xs text-on-surface-variant relative">
                <div className="flex gap-1.5 mb-4">
                  <div className="w-2 h-2 rounded-full bg-error/40"></div>
                  <div className="w-2 h-2 rounded-full bg-tertiary-fixed-dim"></div>
                  <div className="w-2 h-2 rounded-full bg-secondary-fixed-dim"></div>
                </div>
                <code className="block">GET /v1/recommendations</code>
                <code className="block text-secondary">{'{'}</code>
                <code className="block ml-4">&quot;patient_id&quot;: &quot;PX-902&quot;,</code>
                <code className="block ml-4">&quot;analysis&quot;: &quot;active&quot;,</code>
                <code className="block ml-4 text-primary-fixed-dim italic">// clinical inference...</code>
                <code className="block text-secondary">{'}'}</code>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-8">
        <div className="max-w-7xl mx-auto grid md:grid-cols-2 gap-20 items-center">
          <div className="relative">
            <div className="rounded-3xl overflow-hidden aspect-[4/5] shadow-2xl">
              <img
                alt="Professional analyzing data"
                className="w-full h-full object-cover"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuDqzn7b5rH3BXVKDtI0HPGwkyY7o-nPxiUnTTOA3XDh3HJBmC7x9PPCpc-VCH7oK0XuBEn9SiRPq7vYDa_I0psOjwevXYA2fZiEoFZZ7MD8mmv3Apkaic33lhl8WnCtIAEwFEBzwn8pTemKXiOUUzVCA1cDkaaxF4erdzJhvUewTGi1VFvDVfWkwdnPyi1MiXEgBkQgQHfbPl0Z716b_ga-8dRQ7vORqOs_H4x0sQSFy2W7lCE0k6kjT856C2Jwc2qiPx9UgmJGj4g"
              />
            </div>
            <div className="absolute -bottom-8 -right-8 bg-surface-container-lowest p-8 rounded-3xl shadow-xl max-w-xs border border-outline-variant/10">
              <p className="font-headline italic text-primary text-xl mb-4 leading-tight">
                &quot;The accuracy is unprecedented in the B2B space.&quot;
              </p>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-secondary-container"></div>
                <div>
                  <p className="text-sm font-bold">Dr. Sarah Chen</p>
                  <p className="text-xs text-on-surface-variant">Director of Innovation</p>
                </div>
              </div>
            </div>
          </div>
          <div>
            <h2 className="text-4xl font-bold text-primary mb-6 leading-tight">
              From Raw Data to <span className="text-secondary italic">Patient Success</span>.
            </h2>
            <p className="text-on-surface-variant text-lg leading-relaxed mb-8">
              The pharmaceutical landscape shifts daily. New trials, drug recalls, and dosage guidelines emerge faster than any human can track. PharmacoAI provides the intellectual infrastructure to keep your practice ahead of the curve.
            </p>
            <ul className="space-y-6">
              <li className="flex items-start gap-4">
                <div className="w-6 h-6 rounded-full bg-secondary/10 flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="material-symbols-outlined text-secondary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                    check_circle
                  </span>
                </div>
                <div>
                  <h4 className="font-bold text-primary">Contextual Awareness</h4>
                  <p className="text-sm text-on-surface-variant">Our models understand the clinical context, not just keywords.</p>
                </div>
              </li>
              <li className="flex items-start gap-4">
                <div className="w-6 h-6 rounded-full bg-secondary/10 flex items-center justify-center flex-shrink-0 mt-1">
                  <span className="material-symbols-outlined text-secondary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                    check_circle
                  </span>
                </div>
                <div>
                  <h4 className="font-bold text-primary">Regulatory Alignment</h4>
                  <p className="text-sm text-on-surface-variant">Built-in compliance monitoring for FDA and EMA updates.</p>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section className="py-20 px-8">
        <div className="max-w-7xl mx-auto bg-primary-container rounded-[2.5rem] p-8 md:p-14 relative overflow-hidden">
          <div className="relative z-10">
            <h2 className="text-4xl md:text-5xl font-bold text-white mb-4">Ready to upgrade your pharmacy&apos;s intelligence?</h2>
            <p className="text-on-primary-container text-lg mb-10 max-w-3xl">
              Choose a plan and provide your billing details. You will be redirected to Stripe checkout.
            </p>

            {checkoutStatus === 'success' && (
              <p className="mb-6 rounded-xl bg-emerald-500/20 border border-emerald-300/40 text-white px-4 py-3 text-sm font-semibold">
                Subscription flow completed successfully.
              </p>
            )}

            <div className="grid md:grid-cols-3 gap-5 mb-6">
              {SUBSCRIPTION_PLANS.map((plan) => (
                <article key={plan.tier} className={`rounded-3xl border p-6 shadow-sm ${plan.cardClass}`}>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-slate-700 font-bold">{plan.name}</p>
                  <p className="text-4xl text-slate-900 font-bold mt-3">
                    {plan.priceLabel}
                    <span className="text-sm text-slate-600">{plan.cadence}</span>
                  </p>
                  <p className="text-sm text-slate-700 mt-3 mb-4">{plan.tagline}</p>
                  <ul className="space-y-2 mb-6">
                    <li className="text-sm text-slate-700">{plan.userLimit}</li>
                    <li className="text-sm text-slate-700">{plan.messageLimit}</li>
                    <li className="text-sm text-slate-700">{plan.agents.length} included agent(s)</li>
                  </ul>
                  <button
                    className={`w-full rounded-xl py-2.5 text-sm font-bold transition-colors ${plan.buttonClass}`}
                    type="button"
                    onClick={() => goToSignup(plan.tier)}
                    disabled={currentTier === plan.tier}
                  >
                    {currentTier === plan.tier ? 'Current plan' : `Choose ${plan.name}`}
                  </button>
                </article>
              ))}
            </div>

            <p className="text-sm text-on-primary-container mb-1">
              Every user can buy a custom number of extra messages at any time, regardless of subscription plan.
            </p>
            <p className="text-xs text-on-primary-container/80">Top-ups are handled as add-ons to your active subscription.</p>
          </div>

          <div className="absolute inset-0 -z-0 opacity-10">
            <div className="absolute top-0 left-0 w-64 h-64 bg-secondary rounded-full blur-[100px]"></div>
            <div className="absolute bottom-0 right-0 w-64 h-64 bg-primary-fixed rounded-full blur-[100px]"></div>
          </div>
        </div>
      </section>
    </main>
  );
}

function SubscriptionSignupPage({ checkoutSession, onBillingLogin, onBillingLogout, showSwitchAccount }) {
  const selectedPlan = resolveSelectedPlan();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [accountProfile, setAccountProfile] = useState(null);

  useEffect(() => {
    let mounted = true;
    async function loadProfile() {
      if (!checkoutSession?.userId) {
        setAccountProfile(null);
        return;
      }

      try {
        const profile = await getMyUser(checkoutSession.userId);
        if (mounted) {
          setAccountProfile(profile);
        }
      } catch {
        if (mounted) {
          setAccountProfile(null);
        }
      }
    }

    loadProfile();
    return () => {
      mounted = false;
    };
  }, [checkoutSession?.userId]);

  async function handleBillingLogin(event) {
    event.preventDefault();
    setLoginError('');
    setLoginBusy(true);

    try {
      await onBillingLogin({ email: loginEmail.trim(), password: loginPassword });
      setLoginPassword('');
    } catch (loginFailure) {
      if (loginFailure instanceof Error) {
        setLoginError(loginFailure.message);
      } else {
        setLoginError('Login failed');
      }
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleStartCheckout(event) {
    event.preventDefault();
    setSubscriptionError('');

    if (!checkoutSession?.userId) {
      setSubscriptionError('Please log in to continue with payment.');
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await createSubscriptionCheckout(checkoutSession.userId, {
        tier: selectedPlan.tier,
      });

      if (typeof window !== 'undefined') {
        window.location.href = response.checkout_url;
      }
    } catch (checkoutError) {
      if (checkoutError instanceof Error) {
        setSubscriptionError(checkoutError.message);
      } else {
        setSubscriptionError('Could not start checkout');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function goBackToPlans() {
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  }

  return (
    <main>
      <section className="px-8 py-16 bg-surface-container-low min-h-[70vh]">
        <div className="max-w-5xl mx-auto grid lg:grid-cols-5 gap-6">
          <div className="lg:col-span-2 rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-6 shadow-sm h-fit">
            <p className="text-xs uppercase tracking-[0.18em] text-secondary font-bold">Selected plan</p>
            <h2 className="text-3xl text-primary font-bold mt-2">{selectedPlan.name}</h2>
            <p className="text-lg font-semibold text-on-surface mt-1">
              {selectedPlan.priceLabel}
              <span className="text-sm font-normal text-on-surface-variant">{selectedPlan.cadence}</span>
            </p>
            <p className="text-sm text-on-surface-variant mt-4">{selectedPlan.tagline}</p>

            <div className="mt-5 space-y-2">
              <p className="text-sm text-on-surface">{selectedPlan.userLimit}</p>
              <p className="text-sm text-on-surface">{selectedPlan.messageLimit}</p>
            </div>

            <button
              className="mt-6 px-4 py-2 rounded-xl text-sm font-bold bg-surface-container-low hover:bg-surface-container-high transition-colors"
              type="button"
              onClick={goBackToPlans}
            >
              Back to plans
            </button>
          </div>
          <div className="lg:col-span-3 rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-8 shadow-sm">
            {checkoutSession ? (
              <>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary font-bold mb-2">Authenticated checkout</p>
                <h3 className="text-3xl text-primary font-bold mb-4">Continue to payment</h3>
                <p className="text-sm text-on-surface-variant mb-6">
                  You are signed in as {checkoutSession.email}. Your account will be used for this subscription checkout.
                </p>

                {accountProfile && (
                  <div className="mb-6 rounded-2xl border border-outline-variant/40 bg-surface-container-low p-4 text-sm text-on-surface-variant">
                    Current account: {accountProfile.full_name} · {accountProfile.role.toUpperCase()} · Tier {accountProfile.tier.toUpperCase()}
                  </div>
                )}

                <form onSubmit={handleStartCheckout}>
                  {subscriptionError && <p className="mt-4 text-sm font-semibold text-error">{subscriptionError}</p>}

                  <button
                    className="mt-2 bg-primary-container text-white px-8 py-3 rounded-2xl font-bold text-base hover:opacity-90 transition-opacity shadow-lg shadow-primary-container/20 disabled:opacity-60"
                    type="submit"
                    disabled={isSubmitting || accountProfile?.tier === selectedPlan.tier}
                  >
                    {accountProfile?.tier === selectedPlan.tier
                      ? `${selectedPlan.name} is already active`
                      : isSubmitting
                        ? 'Preparing checkout...'
                        : `Continue with ${selectedPlan.name} plan`}
                  </button>

                  <p className="mt-4 text-xs text-on-surface-variant">
                    Every user can buy a custom number of extra messages at any time, regardless of subscription plan.
                  </p>
                </form>

                {showSwitchAccount && (
                  <button
                    className="mt-4 text-xs font-semibold text-on-surface-variant hover:text-primary transition-colors"
                    type="button"
                    onClick={onBillingLogout}
                  >
                    Use a different account
                  </button>
                )}
              </>
            ) : (
              <>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary font-bold mb-2">Sign in to continue</p>
                <h3 className="text-3xl text-primary font-bold mb-4">Log in for billing</h3>
                <p className="text-sm text-on-surface-variant mb-6">
                  Log in with any existing account to start checkout. You can become the organization admin after payment completes.
                </p>
                <form className="space-y-4" onSubmit={handleBillingLogin}>
                  <label className="block">
                    <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Email</span>
                    <input
                      className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                      value={loginEmail}
                      onChange={(event) => setLoginEmail(event.target.value)}
                      autoComplete="username"
                      required
                    />
                  </label>

                  <label className="block">
                    <span className="text-xs font-bold text-on-surface-variant uppercase tracking-widest">Password</span>
                    <input
                      className="mt-2 block w-full rounded-xl border-outline-variant/60 bg-surface px-3 py-2 text-sm"
                      type="password"
                      value={loginPassword}
                      onChange={(event) => setLoginPassword(event.target.value)}
                      autoComplete="current-password"
                      required
                    />
                  </label>

                  {loginError && <p className="text-sm font-semibold text-error">{loginError}</p>}

                  <button
                    className="w-full bg-primary-container text-white rounded-2xl py-3 text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-[0.99] transition-transform disabled:opacity-70"
                    type="submit"
                    disabled={loginBusy}
                  >
                    {loginBusy ? 'Signing In...' : 'Log In'}
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function SubscriptionSuccessPage({ checkoutSession }) {
  const isAdmin = checkoutSession?.role === 'admin';
  const accountPath = isAdmin ? '/admin' : '/pharmacist/account';
  const [status, setStatus] = useState('pending');
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    async function finalize() {
      if (typeof window === 'undefined') {
        return;
      }

      const params = new URLSearchParams(window.location.search);
      const sessionId = params.get('session_id');
      if (!sessionId) {
        if (mounted) {
          setStatus('confirmed');
        }
        return;
      }

      try {
        await confirmSubscription(sessionId);
        if (mounted) {
          setStatus('confirmed');
        }
      } catch (confirmError) {
        if (mounted) {
          setStatus('failed');
          if (confirmError instanceof Error) {
            setError(confirmError.message);
          } else {
            setError('Could not confirm subscription');
          }
        }
      }
    }

    finalize();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <main>
      <section className="px-8 py-20 bg-surface-container-low min-h-[70vh]">
        <div className="max-w-2xl mx-auto rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-10 shadow-sm text-center">
          <p className="text-xs uppercase tracking-[0.18em] text-secondary font-bold mb-3">Payment complete</p>
          <h2 className="text-4xl text-primary font-bold mb-4">Success! Your plan payment was completed.</h2>
          <p className="text-sm text-on-surface-variant mb-8">
            You can now continue to your account and manage your subscription.
          </p>
          {status === 'pending' && (
            <p className="mb-6 rounded-xl bg-surface-container-low border border-outline-variant/40 text-on-surface-variant px-4 py-3 text-sm font-semibold">
              Confirming your subscription...
            </p>
          )}
          {status === 'failed' && (
            <p className="mb-6 rounded-xl bg-error/10 border border-error/30 text-error px-4 py-3 text-sm font-semibold">
              {error || 'Could not confirm subscription.'}
            </p>
          )}
          <a
            className="inline-flex items-center justify-center bg-primary-container text-white px-8 py-3 rounded-2xl font-bold text-sm hover:opacity-90 transition-opacity"
            href={accountPath}
          >
            Go to Account
          </a>
        </div>
      </section>
    </main>
  );
}

export default function App() {
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '/';
  const isAdminRoute = pathname.startsWith('/admin');
  const isPharmacistRoute = pathname.startsWith('/pharmacist');
  const isSubscribeSuccessRoute = pathname === '/subscribe/success';
  const isSubscribeRoute = pathname.startsWith('/subscribe');
  const isPharmacistAccountRoute = pathname.startsWith('/pharmacist/account');
  const isPharmacistChatRoute = pathname.startsWith('/pharmacist/chat') || pathname.startsWith('/pharmacist/agent');
  const isPharmacistRootRoute = pathname === '/pharmacist';
  const currentRoute = isAdminRoute ? 'admin' : isPharmacistRoute ? 'pharmacist' : 'landing';

  const [adminSession, setAdminSession] = useState(() => readAdminSession());
  const [pharmacistSession, setPharmacistSession] = useState(() => readPharmacistSession());
  const [billingSession, setBillingSession] = useState(() => readBillingSession());

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

    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const redirectPath = params.get('redirect');
      if (redirectPath) {
        window.location.href = redirectPath;
      }
    }
  }

  function handleLogout() {
    clearAdminSession();
    setAdminSession(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  }

  async function handleBillingLogin({ email, password }) {
    const user = await loginUser(email, password);

    const session = {
      userId: user.user_id,
      email: user.email,
      fullName: user.full_name,
      role: user.role,
      tier: user.tier,
    };

    persistBillingSession(session);
    setBillingSession(session);
  }

  function handleBillingLogout() {
    clearBillingSession();
    setBillingSession(null);
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
      {(() => {
        const checkoutSession = adminSession ?? pharmacistSession ?? billingSession;
        return isSubscribeSuccessRoute ? (
          <SubscriptionSuccessPage checkoutSession={checkoutSession} />
        ) : isSubscribeRoute ? (
          <SubscriptionSignupPage
            checkoutSession={checkoutSession}
            onBillingLogin={handleBillingLogin}
            onBillingLogout={handleBillingLogout}
            showSwitchAccount={Boolean(billingSession) && !adminSession && !pharmacistSession}
          />
        ) : isAdminRoute ? (
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
            ) : (
              <PharmacistChatPage pharmacistSession={pharmacistSession} />
            )
          ) : (
            <PharmacistLoginPage onLogin={handlePharmacistLogin} />
          )
        ) : (
          <LandingPageContent checkoutSession={checkoutSession} />
        );
      })()}
      <SiteFooter />
    </div>
  );
}
