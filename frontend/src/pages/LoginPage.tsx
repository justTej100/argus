import { useSearchParams } from 'react-router-dom';

const ERRORS: Record<string, string> = {
  unauthorized: 'Your Google account is not authorized.',
  oauth_failed: 'Google sign-in failed. Please try again.',
};

export default function LoginPage() {
  const [params] = useSearchParams();
  const error = params.get('error');

  return (
    <div className="login-page">
      <div className="panel login-card">
        <h1>ARGUS</h1>
        <p>Personal study buddy for your textbooks.</p>
        {error && ERRORS[error] && <p className="login-error">{ERRORS[error]}</p>}
        <a href="/auth/google" className="btn btn-primary" style={{ width: '100%' }}>
          Sign in with Google
        </a>
      </div>
    </div>
  );
}
