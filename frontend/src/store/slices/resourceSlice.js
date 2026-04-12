import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
const API_URL = 'http://localhost:5000/api';
export const fetchVMs = createAsyncThunk(
  'resources/fetchVMs',
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(`${API_URL}/resources/vm?organization_id=${orgId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response.data.vms;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  }
);
export const fetchDatabases = createAsyncThunk(
  'resources/fetchDatabases',
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(`${API_URL}/resources/db?organization_id=${orgId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response.data.databases;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
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
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
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
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
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
      .addCase(fetchDatabases.fulfilled, (state, action) => {
        state.loading = false;
        state.databases = action.payload;
      })
      .addCase(createVM.fulfilled, (state, action) => {
        state.vms.push(action.payload.vm);
      });
  },
});
export default resourceSlice.reducer;
