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
export const fetchDashboardSummary = createAsyncThunk(
  "dashboard/fetchSummary",
  async (orgId, { getState, rejectWithValue }) => {
    try {
      const token = getState().auth.token;
      const response = await axios.get(
        `${API_URL}/dashboard/summary?organization_id=${orgId}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data?.error);
    }
  },
);
const dashboardSlice = createSlice({
  name: "dashboard",
  initialState: {
    activeOrgId: null,
    summary: null,
    loading: false,
    error: null,
  },
  reducers: {
    updateDashboardState: (state, action) => {
      const p = action.payload || {};
      if (!state.summary) {
        state.summary = {};
      }
      
      const prevTrend = state.summary.utilization_trend || [];
      const newTrendPoint = {
        timestamp: p.timestamp ? new Date(p.timestamp * 1000).toISOString() : new Date().toISOString(),
        cpu_avg: p.cpu_avg ?? state.summary.cpu_avg ?? 0,
        memory_avg: p.memory_avg ?? state.summary.memory_avg ?? 0,
      };

      // Keep last 20 points for smooth charts without bloat
      const updatedTrend = [...prevTrend, newTrendPoint].slice(-20);

      state.summary = {
        ...state.summary,
        ...p,
        utilization_trend: updatedTrend,
        security_score: p.security_score ?? state.summary.security_score,
        compliance_score: p.compliance_score ?? state.summary.compliance_score,
        health_score: p.health_score_calculated ?? p.health_score ?? state.summary.health_score,
        total_vms: p.total_vms ?? state.summary.total_vms,
        running_vms: p.running_vms ?? state.summary.running_vms,
        running: p.running_vms ?? state.summary.running,
        cpu_avg: p.cpu_avg ?? state.summary.cpu_avg,
        memory_avg: p.memory_avg ?? state.summary.memory_avg,
        bpi: p.bpi ?? state.summary.bpi,
        target_bpi: p.target_bpi ?? state.summary.target_bpi,
        capacity: p.capacity ?? state.summary.capacity,
        desired_capacity: p.desired_capacity ?? state.summary.desired_capacity,
        running_capacity: p.running_capacity ?? state.summary.running_capacity,
      };
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(setCurrentOrganization, (state, action) => {
        state.activeOrgId = action.payload?.id ?? null;
        state.summary = null;
        state.loading = false;
        state.error = null;
      })
      .addCase(switchOrganization, (state, action) => {
        state.activeOrgId = action.payload?.id ?? null;
        state.summary = null;
        state.loading = false;
        state.error = null;
      })
      .addCase(fetchDashboardSummary.pending, (state, action) => {
        state.loading = true;
        state.error = null;
        state.activeOrgId = getOrgId(action.meta.arg);
      })
      .addCase(fetchDashboardSummary.fulfilled, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.loading = false;
        const p = action.payload || {};
        state.summary = {
          ...p,
          security_score: p.security_score ?? p.security?.score ?? 0,
          compliance_score: p.compliance_score ?? p.compliance?.score ?? 0,
          health_score: p.health_score_calculated ?? p.health_score ?? 0,
          monthly_spend: p.costs?.total ?? p.monthly_spend ?? 0,
          total_vms:
            p.total_vms ?? p.resources?.vms?.total ?? p.resources?.total ?? 0,
          running_vms:
            p.running_vms ??
            p.resources?.vms?.running ??
            p.resources?.running ??
            p.running ??
            0,
          running:
            p.running_vms ??
            p.resources?.vms?.running ??
            p.resources?.running ??
            p.running ??
            0,
        };
      })
      .addCase(fetchDashboardSummary.rejected, (state, action) => {
        if (state.activeOrgId !== getOrgId(action.meta.arg)) {
          return;
        }
        state.loading = false;
        state.error = action.payload || "Failed to fetch dashboard summary";
      });
  },
});
export const { updateDashboardState } = dashboardSlice.actions;
export default dashboardSlice.reducer;
