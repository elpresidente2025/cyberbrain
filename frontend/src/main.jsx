import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth.jsx';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import createCustomTheme from './theme';
import { ThemeModeProvider, useThemeMode } from './contexts/ThemeContext.jsx';
import { HelmetProvider } from 'react-helmet-async';
import App from './App.jsx';
import ErrorPage from './pages/ErrorPage.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';
import AdminRoute from './components/AdminRoute.jsx';
import OnboardingGuard from './components/OnboardingGuard.jsx';
import './index.css';
import './design-system/tokens.css';
import HomePage from './pages/HomePage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import RegisterPage from './pages/RegisterPage.jsx';
import AboutPage from './pages/AboutPage.jsx';

const OnboardingPage = lazy(() => import('./pages/onboarding/OnboardingPage.jsx'));
const Dashboard = lazy(() => import('./pages/Dashboard.jsx'));
const GeneratePage = lazy(() => import('./pages/GeneratePage.jsx'));
const ProfilePage = lazy(() => import('./pages/ProfilePage.jsx'));
const AdminPage = lazy(() => import('./pages/AdminPage.jsx'));
const CleanupLegacyFieldsPage = lazy(() => import('./pages/CleanupLegacyFieldsPage.jsx'));
const PostDetailPage = lazy(() => import('./pages/PostDetailPage.jsx'));
const PostsListPage = lazy(() => import('./pages/PostsListPage.jsx'));
const Billing = lazy(() => import('./pages/Billing.jsx'));
const GuidelinesPage = lazy(() => import('./pages/GuidelinesPage.jsx'));
const PaymentSuccess = lazy(() => import('./pages/PaymentSuccess.jsx'));
const PaymentFail = lazy(() => import('./pages/PaymentFail.jsx'));
const NaverCallback = lazy(() => import('./pages/auth/NaverCallback.jsx'));
const RestoreAdminPage = lazy(() => import('./pages/RestoreAdminPage.jsx'));
const TermsPage = lazy(() => import('./pages/TermsPage.jsx'));

// Vite 는 lazy import 로 불러오는 청크 fetch 가 실패하면 preload 에러를 던진다.
// 원인 패턴:
//   (1) 배포로 청크 파일명이 바뀌었는데 구 index.html 을 쥐고 있는 경우 → 새로고침 1회로 해결
//   (2) 브라우저 HTTP 캐시에 잘못된 응답(예: text/html 로 된 index.html 본문)이
//       `Cache-Control: immutable` 과 함께 저장돼 있어서, 일반 새로고침·하드 리프레시로도
//       재검증 없이 같은 잘못된 캐시를 계속 쓰는 경우.
//       → `fetch(url, { cache: 'reload' })` 로 강제 재요청해 캐시 엔트리를 덮어쓴 뒤 reload.
//   (3) 사용자 네트워크/프록시 단에서 실제로 청크를 받아오지 못하는 경우
//       → 재시도해도 실패하므로 복구 UI 를 띄우고 사용자가 직접 다시 시도하도록 한다.
// 같은 세션 안에서 reload 직후 10 초 이내에 또 실패하면 무한 새로고침을 피하기 위해 (3) 경로로 간주한다.
const VITE_PRELOAD_KEY = 'vitePreloadReloadAt';
const VITE_PRELOAD_COOLDOWN_MS = 10_000;

const extractFailedChunkUrl = (event) => {
  const payload = event?.payload;
  if (payload && typeof payload === 'object') {
    if (typeof payload.request === 'string') return payload.request;
    if (typeof payload.url === 'string') return payload.url;
  }
  const message = payload?.message || String(payload || '');
  const match = message.match(/https?:\/\/[^\s'"]+\.js/);
  return match ? match[0] : null;
};

const showPreloadRecoveryUI = () => {
  if (document.getElementById('preload-error-recovery')) return;
  const overlay = document.createElement('div');
  overlay.id = 'preload-error-recovery';
  Object.assign(overlay.style, {
    position: 'fixed',
    inset: '0',
    background: '#ffffff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: '2147483647',
    fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif',
    padding: '24px',
  });
  overlay.innerHTML = `
    <div style="max-width:480px;text-align:center;color:#1f2937;">
      <h2 style="font-size:1.375rem;margin:0 0 12px;font-weight:600;">페이지를 불러오지 못했습니다</h2>
      <p style="color:#4b5563;line-height:1.6;margin:0 0 24px;font-size:0.9375rem;">
        네트워크 또는 브라우저 캐시 문제로 일부 리소스를 받아오지 못했습니다. 아래 버튼으로 다시 시도해주세요.
      </p>
      <button id="preload-error-retry" type="button" style="padding:12px 28px;background:#007AFF;color:#fff;border:none;border-radius:10px;font-size:1rem;font-weight:600;cursor:pointer;">
        다시 시도
      </button>
      <p style="color:#9ca3af;font-size:0.8125rem;margin-top:20px;line-height:1.6;">
        계속 실패한다면 브라우저 캐시를 삭제(Ctrl+Shift+Delete)한 뒤 다시 접속해주세요.
      </p>
    </div>
  `;
  document.body.appendChild(overlay);
  document.getElementById('preload-error-retry')?.addEventListener('click', () => {
    sessionStorage.removeItem(VITE_PRELOAD_KEY);
    const url = new URL(window.location.href);
    url.searchParams.set('_r', String(Date.now()));
    window.location.replace(url.toString());
  });
};

window.addEventListener('vite:preloadError', async (event) => {
  const now = Date.now();
  const lastReloadAt = Number(sessionStorage.getItem(VITE_PRELOAD_KEY) || 0);

  if (lastReloadAt && now - lastReloadAt < VITE_PRELOAD_COOLDOWN_MS) {
    console.error(
      'Vite preload error persists after recent reload — surfacing recovery UI.',
      event,
    );
    showPreloadRecoveryUI();
    return;
  }

  sessionStorage.setItem(VITE_PRELOAD_KEY, String(now));
  const failedUrl = extractFailedChunkUrl(event);
  console.warn('Vite preload error caught. Forcing cache refresh + reload.', { failedUrl, event });

  // 잘못된 immutable 캐시 엔트리를 덮어쓰기 위해 강제 재요청.
  if (failedUrl) {
    try {
      await fetch(failedUrl, { cache: 'reload', credentials: 'same-origin' });
    } catch (fetchErr) {
      console.warn('Forced cache-reload fetch failed, proceeding to page reload.', fetchErr);
    }
  }

  window.location.reload();
});

const RouteFallback = () => (
  <div
    style={{
      minHeight: '40vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#4b5563',
      fontSize: '0.95rem',
      fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif',
    }}
  >
    페이지를 불러오는 중입니다.
  </div>
);

const withSuspense = (element) => (
  <Suspense fallback={<RouteFallback />}>
    {element}
  </Suspense>
);

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
      {
        path: 'onboarding',
        element: withSuspense(
          <ProtectedRoute><OnboardingPage /></ProtectedRoute>
        ),
      },
      {
        path: 'dashboard',
        element: withSuspense(
          <ProtectedRoute><OnboardingGuard><Dashboard /></OnboardingGuard></ProtectedRoute>
        ),
      },
      {
        path: 'generate',
        element: withSuspense(
          <ProtectedRoute><OnboardingGuard><GeneratePage /></OnboardingGuard></ProtectedRoute>
        ),
      },
      {
        path: 'profile',
        element: withSuspense(
          <ProtectedRoute><OnboardingGuard><ProfilePage /></OnboardingGuard></ProtectedRoute>
        ),
      },
      {
        path: 'billing',
        element: withSuspense(
          <ProtectedRoute><Billing /></ProtectedRoute>
        ),
      },
      {
        path: 'admin',
        element: withSuspense(
          <AdminRoute><AdminPage /></AdminRoute>
        ),
      },
      {
        path: 'admin/cleanup',
        element: withSuspense(
          <AdminRoute><CleanupLegacyFieldsPage /></AdminRoute>
        ),
      },
      {
        path: 'posts',
        element: withSuspense(
          <ProtectedRoute><OnboardingGuard><PostsListPage /></OnboardingGuard></ProtectedRoute>
        ),
      },
      {
        path: 'posts/:id',
        element: withSuspense(
          <ProtectedRoute><OnboardingGuard><PostDetailPage /></OnboardingGuard></ProtectedRoute>
        ),
      },
      {
        path: 'guidelines',
        element: withSuspense(
          <ProtectedRoute><OnboardingGuard><GuidelinesPage /></OnboardingGuard></ProtectedRoute>
        ),
      },
      {
        path: 'about',
        element: <AboutPage />,
      },
      {
        path: 'terms',
        element: withSuspense(<TermsPage />),
      },
      {
        path: 'payment/success',
        element: withSuspense(
          <ProtectedRoute><PaymentSuccess /></ProtectedRoute>
        ),
      },
      {
        path: 'payment/fail',
        element: withSuspense(
          <ProtectedRoute><PaymentFail /></ProtectedRoute>
        ),
      },
      {
        path: 'auth/naver/callback',
        element: withSuspense(<NaverCallback />),
      },
      {
        path: 'restore-admin',
        element: withSuspense(<RestoreAdminPage />),
      },
    ],
  },
]);

const ThemedApp = () => {
  const { isDarkMode } = useThemeMode();
  const theme = createCustomTheme(isDarkMode);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <HelmetProvider>
      <ThemeModeProvider>
        <ThemedApp />
      </ThemeModeProvider>
    </HelmetProvider>
  </React.StrictMode>
);

const loadingContainer = document.getElementById('loading-container');
if (loadingContainer) {
  loadingContainer.classList.add('hidden');
}
