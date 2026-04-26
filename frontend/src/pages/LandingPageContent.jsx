export default function LandingPageContent() {
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
        <div className="max-w-5xl mx-auto bg-primary-container rounded-[2.5rem] p-12 md:p-20 text-center relative overflow-hidden">
          <div className="relative z-10">
            <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">Ready to upgrade your pharmacy&apos;s intelligence?</h2>
            <p className="text-on-primary-container text-lg mb-10 max-w-2xl mx-auto">
              Join the 500+ clinical institutions leveraging PharmacoAI to drive better patient outcomes through automation.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button className="bg-secondary text-white px-10 py-4 rounded-2xl font-bold text-lg hover:bg-on-secondary-container transition-colors shadow-lg shadow-secondary/20" type="button">
                Request Demo
              </button>
              <button className="bg-white/10 text-white backdrop-blur-md px-10 py-4 rounded-2xl font-bold text-lg hover:bg-white/20 transition-colors" type="button">
                Contact Sales
              </button>
            </div>
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
