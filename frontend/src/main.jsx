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

window.addEventListener('vite:preloadError', (event) => {
  console.warn('Vite preload error caught. Reloading page to fetch latest chunks...', event);
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
