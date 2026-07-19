import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import AdminPage from './pages/AdminPage';
import FeedPage from './pages/FeedPage';
import LibraryPage from './pages/LibraryPage';
import LoginPage from './pages/LoginPage';
import StudyPage from './pages/StudyPage';
import NewsRail from './components/NewsRail';

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <Layout right={<NewsRail />}>{children}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Shell>
            <FeedPage />
          </Shell>
        }
      />
      <Route
        path="/library"
        element={
          <Shell>
            <LibraryPage />
          </Shell>
        }
      />
      <Route
        path="/study"
        element={
          <Shell>
            <StudyPage />
          </Shell>
        }
      />
      <Route
        path="/admin"
        element={
          <Shell>
            <AdminPage />
          </Shell>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
