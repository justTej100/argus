import { useSearchParams } from 'react-router-dom';

const ERRORS: Record<string, string> = {
  unauthorized: 'Your Google account is not authorized.',
  oauth_failed: 'Google sign-in failed. Please try again.',
};

const REPO_URL = 'https://github.com/justTej100/argus';

function GoogleIcon() {
  return (
    <svg className="login-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M12 10.2v3.6h5.1c-.2 1.2-.9 2.3-1.9 3l3.1 2.4c1.8-1.7 2.9-4.1 2.9-7 0-.7-.1-1.3-.2-1.9H12z"
      />
      <path
        fill="#34A853"
        d="M5.3 14.3l-.8.6-2.7 2.1C3.5 20.1 7.4 22.5 12 22.5c2.7 0 5-.9 6.7-2.4l-3.1-2.4c-.9.6-2 1-3.6 1-2.8 0-5.1-1.9-5.9-4.4z"
      />
      <path
        fill="#4A90E2"
        d="M3.2 6.1A10.4 10.4 0 0 0 1.5 12c0 2.1.6 4 1.7 5.6l3.5-2.7C6.1 13.5 5.8 12.8 5.8 12c0-.8.3-1.6.7-2.3z"
      />
      <path
        fill="#FBBC05"
        d="M12 5.3c1.5 0 2.8.5 3.8 1.5l2.8-2.8C16.9 2.3 14.7 1.5 12 1.5 7.4 1.5 3.5 3.9 1.8 7.7l3.5 2.7C6.9 7.2 9.2 5.3 12 5.3z"
      />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg className="login-icon" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
      <path d="M12 1.5C6.2 1.5 1.5 6.3 1.5 12.1c0 4.7 3 8.7 7.2 10.1.5.1.7-.2.7-.5v-1.9c-2.9.6-3.5-1.3-3.5-1.3-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.4 1.1 3 .8.1-.7.4-1.1.6-1.4-2.3-.3-4.8-1.2-4.8-5.2 0-1.1.4-2.1 1.1-2.8-.1-.3-.5-1.4.1-2.9 0 0 .9-.3 2.9 1.1a9.8 9.8 0 0 1 5.3 0c2-1.4 2.9-1.1 2.9-1.1.6 1.5.2 2.6.1 2.9.7.7 1.1 1.7 1.1 2.8 0 4-2.4 4.9-4.8 5.2.4.3.7 1 .7 2v2.9c0 .3.2.6.7.5 4.2-1.4 7.2-5.4 7.2-10.1C22.5 6.3 17.8 1.5 12 1.5z" />
    </svg>
  );
}

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
        <a href="/auth/google" className="btn btn-primary login-google">
          <GoogleIcon />
          Sign in with Google
        </a>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="login-repo">
          <GitHubIcon />
          View source on GitHub
        </a>
      </div>
    </div>
  );
}
