import { useSearchParams } from 'react-router-dom';

const ERRORS: Record<string, string> = {
  unauthorized: 'Your Google account is not authorized.',
  oauth_failed: 'Google sign-in failed. Please try again.',
};

const REPO_URL = 'https://github.com/justTej100/argus';

export default function LoginPage() {
  const [params] = useSearchParams();
  const error = params.get('error');

  return (
    <div className="login-page">
      <div className="panel login-card">
        <h1>ARGUS</h1>
        <p>Sign in with Google to try the textbook study demo.</p>
        <p className="login-hint">Guests can view and chat (rate limited). Admin accounts get full access.</p>
        {error && ERRORS[error] && <p className="login-error">{ERRORS[error]}</p>}
        <a href="/auth/google" className="btn btn-primary" style={{ width: '100%' }}>
          Sign in with Google
        </a>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="login-repo">
          View source on GitHub
        </a>
      </div>
    </div>
  );
}
