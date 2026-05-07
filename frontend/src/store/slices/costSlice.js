import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
import { setCurrentOrganization, switchOrganization } from './organizationSlice';
const API_URL = 'http://localhost:5000/api';

const getOrgId = (value) => {
  if (value && typeof value === 'object') {
    return value.orgId ?? value.organization_id ?? value.org_id ?? null;
  }
  return value ?? null;
};
export const fetchCurrentCosts = createAsyncThunk(
  'cost/fetchCurrent',
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(`${API_URL}/cost/current?organization_id=${orgId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  }
);
export const fetchForecast = createAsyncThunk(
  'cost/fetchForecast',
  async ({ orgId, days }, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(
        `${API_URL}/cost/forecast?organization_id=${orgId}&days=${days}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  }
);
export const fetchOptimization = createAsyncThunk(
  'cost/fetchOptimization',
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(
        `${API_URL}/cost/optimization?organization_id=${orgId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  }
);
const costSlice = createSlice({
  name: 'cost',
  initialState: {
    activeOrgId: null,
    currentCosts: null,
    forecast: null,
    budgets: [],
    recommendations: [],
    loading: false,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(setCurrentOrganization, (state, action) => {
        state.activeOrgId = action.payload?.id ?? null;
        state.currentCosts = null;
        state.forecast = null;
        state.budgets = [];
        state.recommendations = [];
        state.loading = false;
      })
      .addCase(switchOrganization, (state, action) => {
        state.activeOrgId = action.payload?.id ?? null;
        state.currentCosts = null;
        state.forecast = null;
        state.budgets = [];
        state.recommendations = [];
        state.loading = false;
      })
      .addCase(fetchCurrentCosts.pending, (state, action) => {
        state.loading = true;
        state.activeOrgId = getOrgId(action.meta.arg);
      })
      .addCase(fetchCurrentCosts.fulfilled, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.currentCosts = action.payload;
        state.loading = false;
      })
      .addCase(fetchCurrentCosts.rejected, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.loading = false;
      })
      .addCase(fetchForecast.pending, (state, action) => {
        state.loading = true;
        state.activeOrgId = getOrgId(action.meta.arg);
      })
      .addCase(fetchForecast.fulfilled, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.forecast = action.payload;
        state.loading = false;
      })
      .addCase(fetchForecast.rejected, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.loading = false;
      })
      .addCase(fetchOptimization.pending, (state, action) => {
        state.loading = true;
        state.activeOrgId = getOrgId(action.meta.arg);
      })
      .addCase(fetchOptimization.fulfilled, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.recommendations = action.payload.recommendations || [];
        state.loading = false;
      })
      .addCase(fetchOptimization.rejected, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.loading = false;
      });
  },
});
export default costSlice.reducer;
