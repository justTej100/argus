import { NavLink } from 'react-router-dom';
import { MeProvider, useMe } from '../me';

function NavBar() {
  const me = useMe();

  return (
    <nav className="nav">
      <span className="nav-brand">ARGUS</span>
      <div className="nav-links">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
          Library
        </NavLink>
        <NavLink to="/study" className={({ isActive }) => (isActive ? 'active' : '')}>
          Study
        </NavLink>
        {me?.is_admin && (
          <NavLink to="/admin" className={({ isActive }) => (isActive ? 'active' : '')}>
            Database
          </NavLink>
        )}
        {me && (
          <span className="nav-user" title={me.email}>
            {me.is_admin ? me.email : 'Guest (rate limited)'}
          </span>
        )}
        <a href="/logout">Logout</a>
      </div>
    </nav>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <MeProvider>
      <div className="app-shell">
        <NavBar />
        <main className="main">{children}</main>
      </div>
    </MeProvider>
  );
}
