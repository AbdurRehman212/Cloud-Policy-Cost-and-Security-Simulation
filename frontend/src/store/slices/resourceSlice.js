import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
const API_URL = 'http://localhost:5000/api';

export const fetchVMs = createAsyncThunk(
  'resources/fetchVMs',
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const query = orgId ? `?organization_id=${orgId}` : '';
      const response = await axios.get(`${API_URL}/resources/vm${query}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = response?.data?.data || {};
      return Array.isArray(payload?.vms) ? payload.vms : [];
    } catch (error) {
      return rejectWithValue(error?.response?.data?.error?.message || 'Failed to load resources');
    }
  }
);
export const fetchDatabases = createAsyncThunk(
  'resources/fetchDatabases',
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const query = orgId ? `?organization_id=${orgId}` : '';
      const response = await axios.get(`${API_URL}/resources/db${query}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = response?.data?.data || {};
      return Array.isArray(payload?.databases) ? payload.databases : [];
    } catch (error) {
      return rejectWithValue(error?.response?.data?.error?.message || 'Failed to load databases');
    }
  }
);
export const createVM = createAsyncThunk(
  'resources/createVM',
  async (data, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.post(`${API_URL}/resources/vm`, data, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response?.data?.data || {};
    } catch (error) {
      return rejectWithValue(error?.response?.data?.error?.message || 'Failed to create VM');
    }
  }
);
export const createDatabase = createAsyncThunk(
  'resources/createDatabase',
  async (data, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.post(`${API_URL}/resources/db`, data, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response?.data?.data || {};
    } catch (error) {
      return rejectWithValue(error?.response?.data?.error?.message || 'Failed to create database');
    }
  }
);
export const vmAction = createAsyncThunk(
  'resources/vmAction',
  async ({ instanceId, action }, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.post(
        `${API_URL}/resources/vm/${instanceId}/action`,
        { action },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response?.data?.data || {};
    } catch (error) {
      return rejectWithValue(error?.response?.data?.error?.message || 'Failed VM action');
    }
  }
);
export const dbAction = createAsyncThunk(
  'resources/dbAction',
  async ({ instanceId, action }, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.post(
        `${API_URL}/resources/db/${instanceId}/action`,
        { action },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response?.data?.data || {};
    } catch (error) {
      return rejectWithValue(error?.response?.data?.error?.message || 'Failed DB action');
    }
  }
);
const resourceSlice = createSlice({
  name: 'resources',
  initialState: {
    vms: [],
    databases: [],
    metrics: null,
    loading: false,
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchVMs.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchVMs.fulfilled, (state, action) => {
        state.loading = false;
        state.vms = action.payload;
      })
      .addCase(fetchVMs.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
        state.vms = [];
      })
      .addCase(fetchDatabases.fulfilled, (state, action) => {
        state.loading = false;
        state.databases = action.payload;
      })
      .addCase(fetchDatabases.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
        state.databases = [];
      })
      .addCase(createVM.fulfilled, (state, action) => {
        state.vms.push(action.payload.vm);
      })
      .addCase(createDatabase.fulfilled, (state, action) => {
        state.databases.push(action.payload.database);
      });
  },
});
export default resourceSlice.reducer;
