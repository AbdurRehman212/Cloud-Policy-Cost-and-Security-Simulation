import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
const API_URL = 'http://localhost:5000/api';
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
    currentCosts: null,
    forecast: null,
    budgets: [],
    recommendations: [],
    loading: false,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchCurrentCosts.fulfilled, (state, action) => {
        state.currentCosts = action.payload;
      })
      .addCase(fetchForecast.fulfilled, (state, action) => {
        state.forecast = action.payload;
      })
      .addCase(fetchOptimization.fulfilled, (state, action) => {
        state.recommendations = action.payload.recommendations || [];
      });
  },
});
export default costSlice.reducer;
