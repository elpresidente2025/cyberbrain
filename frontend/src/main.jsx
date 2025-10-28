// frontend/src/main.jsx
import React from 'react';
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
import ProfileRequiredRoute from './components/ProfileRequiredRoute.jsx';
import './index.css';

// ?�� ?�시: lazy loading ?�거?�고 직접 import
import HomePage from './pages/HomePage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import RegisterPage from './pages/RegisterPage.jsx';
import Dashboard from './pages/Dashboard.jsx';
import GeneratePage from './pages/GeneratePage.jsx';
import ProfilePage from './pages/ProfilePage.jsx';
import AdminPage from './pages/AdminPage.jsx';
import CleanupLegacyFieldsPage from './pages/CleanupLegacyFieldsPage.jsx';
import PostDetailPage from './pages/PostDetailPage.jsx';
import PostsListPage from './pages/PostsListPage.jsx';
import Billing from './pages/Billing.jsx';
import GuidelinesPage from './pages/GuidelinesPage.jsx';
import PaymentSuccess from './pages/PaymentSuccess.jsx';
import PaymentFail from './pages/PaymentFail.jsx';
import NaverCallback from './pages/auth/NaverCallback.jsx';
import AboutPage from './pages/AboutPage.jsx';
import RestoreAdminPage from './pages/RestoreAdminPage.jsx';

// ?�� ?�리로드 ?�수??(?�용???�도 감�? ???�용)
export const preloadGenerate = () => import('./pages/GeneratePage.jsx');
export const preloadPosts = () => import('./pages/PostsListPage.jsx');
export const preloadBilling = () => import('./pages/Billing.jsx');
export const preloadProfile = () => import('./pages/ProfilePage.jsx');

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
        path: 'dashboard',
        element: <ProtectedRoute><Dashboard /></ProtectedRoute>,
      },
      {
        path: 'generate',
        element: <ProtectedRoute><ProfileRequiredRoute><GeneratePage /></ProfileRequiredRoute></ProtectedRoute>,
      },
      {
        path: 'profile',
        element: <ProtectedRoute><ProfilePage /></ProtectedRoute>,
      },
      {
        path: 'billing',
        element: <ProtectedRoute><Billing /></ProtectedRoute>,
      },
      {
        path: 'admin',
        element: <AdminRoute><AdminPage /></AdminRoute>,
      },
      {
        path: 'admin/cleanup',
        element: <AdminRoute><CleanupLegacyFieldsPage /></AdminRoute>,
      },
      {
        path: 'posts',
        element: <ProtectedRoute><ProfileRequiredRoute><PostsListPage /></ProfileRequiredRoute></ProtectedRoute>,
      },
      {
        path: 'guidelines',
        element: <ProtectedRoute><ProfileRequiredRoute><GuidelinesPage /></ProfileRequiredRoute></ProtectedRoute>,
      },
      {
        path: 'about',
        element: <AboutPage />,
      },
      {
        path: 'payment/success',
        element: <ProtectedRoute><PaymentSuccess /></ProtectedRoute>,
      },
      {
        path: 'payment/fail',
        element: <ProtectedRoute><PaymentFail /></ProtectedRoute>,
      },
      {
        path: 'auth/naver/callback',
        element: <NaverCallback />,
      },
      {
        path: 'restore-admin',
        element: <RestoreAdminPage />,
      },
    ],
  },
]);

// ?�마�??�용?�는 ??컴포?�트
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

// React ???�더�?
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

// React 마운???�료 ??즉시 로딩 ?�피???�기�?
const loadingContainer = document.getElementById('loading-container');
if (loadingContainer) {
  loadingContainer.classList.add('hidden');
}
