import { NavLink } from 'react-router-dom';
import { MeProvider, useMe } from '../me';

function LeftRail() {
  const me = useMe();

  return (
    <aside className="rail rail-left">
      <div className="brand-block">
        <span className="brand-mark">ARGUS</span>
        <span className="brand-tag">textbook social</span>
      </div>
      <nav className="rail-nav">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'rail-link active' : 'rail-link')}>
          Home
        </NavLink>
        <NavLink to="/library" className={({ isActive }) => (isActive ? 'rail-link active' : 'rail-link')}>
          Library
        </NavLink>
        <NavLink to="/study" className={({ isActive }) => (isActive ? 'rail-link active' : 'rail-link')}>
          Study
        </NavLink>
        {me?.is_admin && (
          <NavLink to="/admin" className={({ isActive }) => (isActive ? 'rail-link active' : 'rail-link')}>
            Database
          </NavLink>
        )}
      </nav>
      <div className="rail-foot">
        {me && (
          <p className="rail-user" title={me.email}>
            {me.is_admin ? me.email : 'Guest'}
          </p>
        )}
        <a href="/logout" className="rail-link subtle">
          Log out
        </a>
      </div>
    </aside>
  );
}

export default function Layout({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <MeProvider>
      <div className="shell">
        <LeftRail />
        <main className="center-col">{children}</main>
        <aside className="rail rail-right">{right}</aside>
      </div>
    </MeProvider>
  );
}
