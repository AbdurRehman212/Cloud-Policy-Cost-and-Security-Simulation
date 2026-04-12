import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
const API_URL = 'http://localhost:5000/api';
export const fetchDashboardSummary = createAsyncThunk(
  'dashboard/fetchSummary',
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(
        `${API_URL}/dashboard/summary?organization_id=${orgId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  }
);
const dashboardSlice = createSlice({
  name: 'dashboard',
  initialState: {
    summary: null,
    loading: false,
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchDashboardSummary.fulfilled, (state, action) => {
        state.summary = action.payload;
      });
  },
});
export default dashboardSlice.reducer;
