export default function SiteFooter() {
  return (
    <footer className="bg-slate-100 dark:bg-slate-900 border-t-0">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 w-full px-8 py-12 max-w-7xl mx-auto">
        <div className="lg:col-span-1">
          <div className="font-serif text-lg font-bold text-slate-800 dark:text-slate-200 mb-6">PharmacoAI</div>
          <p className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 leading-relaxed">
            Elevating the standard of care through rigorous clinical machine learning and data extraction.
          </p>
        </div>
        <div>
          <h4 className="text-teal-700 dark:text-teal-400 font-bold text-xs uppercase tracking-widest mb-6">Product</h4>
          <div className="flex flex-col gap-4">
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Drug Database API
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Solutions
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Pricing
            </a>
          </div>
        </div>
        <div>
          <h4 className="text-teal-700 dark:text-teal-400 font-bold text-xs uppercase tracking-widest mb-6">Legal</h4>
          <div className="flex flex-col gap-4">
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Compliance
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Privacy Policy
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Terms of Service
            </a>
          </div>
        </div>
        <div>
          <h4 className="text-teal-700 dark:text-teal-400 font-bold text-xs uppercase tracking-widest mb-6">Support</h4>
          <div className="flex flex-col gap-4">
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Contact Support
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Help Center
            </a>
            <a className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors" href="#">
              Documentation
            </a>
          </div>
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-8 py-8 border-t border-slate-200 dark:border-slate-800 flex flex-col md:flex-row justify-between items-center gap-4">
        <p className="manrope text-xs tracking-wide text-slate-500 dark:text-slate-400">
          &copy; 2026 PharmacoAI. All clinical insights powered by proprietary machine learning.
        </p>
        <div className="flex gap-6">
          <span className="material-symbols-outlined text-slate-400 cursor-pointer hover:text-teal-700 transition-colors">share</span>
          <span className="material-symbols-outlined text-slate-400 cursor-pointer hover:text-teal-700 transition-colors">podcasts</span>
        </div>
      </div>
    </footer>
  );
}
