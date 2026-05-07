import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import axios from "axios";
import { setCurrentOrganization, switchOrganization } from "./organizationSlice";
const API_URL = "http://localhost:5000/api";

const getOrgId = (value) => {
  if (value && typeof value === "object") {
    return value.orgId ?? value.organization_id ?? value.org_id ?? null;
  }
  return value ?? null;
};
export const fetchThreats = createAsyncThunk(
  "security/fetchThreats",
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(
        `${API_URL}/security/threats?organization_id=${orgId}&status=all`,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  },
);
export const simulateAttack = createAsyncThunk(
  "security/simulateAttack",
  async (data, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.post(
        `${API_URL}/security/simulate-attack`,
        data,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  },
);
const securitySlice = createSlice({
  name: "security",
  initialState: {
    activeOrgId: null,
    threats: [],
    logs: [],
    loading: false,
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(setCurrentOrganization, (state, action) => {
        state.activeOrgId = action.payload?.id ?? null;
        state.threats = [];
        state.logs = [];
        state.loading = false;
        state.error = null;
      })
      .addCase(switchOrganization, (state, action) => {
        state.activeOrgId = action.payload?.id ?? null;
        state.threats = [];
        state.logs = [];
        state.loading = false;
        state.error = null;
      })
      .addCase(fetchThreats.pending, (state, action) => {
        state.loading = true;
        state.activeOrgId = getOrgId(action.meta.arg);
      })
      .addCase(fetchThreats.fulfilled, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.loading = false;
        state.threats =
          action.payload?.threats || action.payload?.data?.threats || [];
      })
      .addCase(fetchThreats.rejected, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.loading = false;
        state.error = action.payload || action.error?.message || null;
      });
  },
});
export default securitySlice.reducer;
