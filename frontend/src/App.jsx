import React, { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { fetchProfile } from './store/slices/authSlice';
import { fetchOrganizations } from './store/slices/organizationSlice';
import Layout from './components/Layout/Layout';
import Login from './pages/Auth/Login';
import Register from './pages/Auth/Register';
import Dashboard from './pages/Dashboard/Dashboard';
import Resources from './pages/Resources/Resources';
import Security from './pages/Security/Security';
import CostManagement from './pages/Cost/CostManagement';
import Governance from './pages/Governance/Governance';
import Membership from './pages/Membership/Membership';
import Settings from './pages/Settings/Settings';
const PrivateRoute = ({ children }) => {
  const { isAuthenticated } = useSelector((state) => state.auth);
  return isAuthenticated ? children : <Navigate to="/login" />;
};
function App() {
  const dispatch = useDispatch();
  const { isAuthenticated } = useSelector((state) => state.auth);
  useEffect(() => {
    if (isAuthenticated) {
      dispatch(fetchProfile());
      dispatch(fetchOrganizations());
    }
  }, [dispatch, isAuthenticated]);
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/"
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="resources" element={<Resources />} />
        <Route path="security" element={<Security />} />
        <Route path="cost" element={<CostManagement />} />
        <Route path="governance" element={<Governance />} />
        <Route path="membership" element={<Membership />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
export default App;
