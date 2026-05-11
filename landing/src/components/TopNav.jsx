function navLinkClass(isActive) {
  if (isActive) {
    return 'text-teal-700 dark:text-teal-400 border-b-2 border-teal-700 dark:border-teal-400 pb-1 manrope text-sm font-semibold';
  }
  return 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors manrope text-sm font-semibold';
}

export default function TopNav() {
  return (
    <nav className="bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-md shadow-sm dark:shadow-none docked full-width top-0 sticky z-50">
      <div className="flex justify-between items-center w-full px-8 py-4 max-w-7xl mx-auto">
        <a className="text-2xl font-bold font-serif text-slate-900 dark:text-slate-50" href="/">
          PharmacoAI
        </a>

        <div className="hidden md:flex gap-8 items-center">
          <a className={navLinkClass(true)} href="/">
            Landing
          </a>
          <a className={navLinkClass(false)} href="#">
            Admin
          </a>
          <a className={navLinkClass(false)} href="#">
            Pharmacist
          </a>
        </div>

        <a
          className="bg-primary-container text-white px-6 py-2.5 rounded-lg font-semibold manrope text-sm hover:scale-95 transition-transform duration-150 active:scale-90"
          href="#"
        >
          Pharmacist Login
        </a>
      </div>
    </nav>
  );
}
