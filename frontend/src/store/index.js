import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import organizationReducer from './slices/organizationSlice';
import resourceReducer from './slices/resourceSlice';
import securityReducer from './slices/securitySlice';
import costReducer from './slices/costSlice';
import dashboardReducer from './slices/dashboardSlice';
export const store = configureStore({
  reducer: {
    auth: authReducer,
    organization: organizationReducer,
    resources: resourceReducer,
    security: securityReducer,
    cost: costReducer,
    dashboard: dashboardReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: false,
    }),
});
