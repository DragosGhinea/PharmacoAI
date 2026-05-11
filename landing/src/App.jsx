import LandingPageContent from './pages/LandingPageContent';
import SiteFooter from './components/SiteFooter';
import TopNav from './components/TopNav';

export default function App() {
  return (
    <div className="text-on-surface selection:bg-secondary-container selection:text-on-secondary-container">
      <TopNav />
      <LandingPageContent />
      <SiteFooter />
    </div>
  );
}
