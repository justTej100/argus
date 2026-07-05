import { NavLink } from 'react-router-dom';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <nav className="nav">
        <span className="nav-brand">ARGUS</span>
        <div className="nav-links">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Library
          </NavLink>
          <NavLink to="/study" className={({ isActive }) => (isActive ? 'active' : '')}>
            Study
          </NavLink>
          <a href="/logout">Logout</a>
        </div>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}
