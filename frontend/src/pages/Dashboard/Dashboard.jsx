import React, { useEffect, useState, useRef } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  ArrowPathIcon,
  BoltIcon,
  BuildingOfficeIcon,
  ChartBarIcon,
  CheckCircleIcon,
  ClockIcon,
  CpuChipIcon,
  CurrencyDollarIcon,
  ServerStackIcon,
  ShieldCheckIcon,
  TrophyIcon,
} from "@heroicons/react/24/outline";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchDashboardSummary, updateDashboardState } from "../../store/slices/dashboardSlice";
import { fetchVMs, upsertVM, removeVM } from "../../store/slices/resourceSlice";
import { createSocket } from "../../services/api";

const formatPercent = (value, digits = 2) =>
  `${Number(value || 0).toFixed(digits)}%`;

const formatChartTime = (value) => {
  if (!value) return "";
  // Check if value is HH:MM string (backend returns this)
  if (typeof value === "string" && value.includes(":")) return value;
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

const formatCost = (value) => `$${Number(value || 0).toFixed(4)}`;

const StatCard = ({ title, value, subtitle, icon: Icon, accentClass }) => (
  <div className="card">
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
          {title}
        </p>
        <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
          {value}
        </p>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {subtitle}
        </p>
      </div>
      <div className={`shrink-0 rounded-lg p-3 ${accentClass}`}>
        <Icon className="h-6 w-6 text-white" />
      </div>
    </div>
  </div>
);

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <p className="font-medium text-gray-900 dark:text-white">
        {formatChartTime(label)}
      </p>
      {payload.map((item) => (
        <p key={item.dataKey} style={{ color: item.color }}>
          {item.name}: {Number(item.value || 0).toFixed(2)}%
        </p>
      ))}
    </div>
  );
};

const RESOURCE_TYPE_COLORS = {
  vm: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  database:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  storage:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  network: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
};

const resourceTypeBadge = (type) =>
  RESOURCE_TYPE_COLORS[type?.toLowerCase()] ||
  "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300";

const activityIcon = (action) => {
  if (!action) return null;
  const lower = action.toLowerCase();
  if (lower.includes("creat") || lower.includes("provision")) {
    return <CheckCircleIcon className="h-4 w-4 text-success-500 shrink-0" />;
  }
  if (lower.includes("delet") || lower.includes("terminat")) {
    return <BoltIcon className="h-4 w-4 text-danger-500 shrink-0" />;
  }
  return <ClockIcon className="h-4 w-4 text-gray-400 shrink-0" />;
};

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5000/api";

const Dashboard = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const activeOrgId = useSelector(
    (state) => state.organization?.currentOrganization?.id ?? null,
  );
  const { token } = useSelector((state) => state.auth);
  const { summary: reduxSummary, loading } = useSelector((state) => state.dashboard || { summary: {}, loading: false });
  const reduxVms = useSelector((state) => state.resources?.vms ?? []);
  const [costByResource, setCostByResource] = useState([]);

  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [realtimeStatus, setRealtimeStatus] = useState("connecting");
  const [liveResources, setLiveResources] = useState([]);
  const [socket, setSocket] = useState(null);
  const [progress, setProgress] = useState(null);
  const [learningProfile, setLearningProfile] = useState(null);
  const [scalingEvents, setScalingEvents] = useState([]);
  const previousQueueRef = useRef(0);
  const [queueTrend, setQueueTrend] = useState("stable");
  const previousCapacityRef = useRef(0);
  const [lastInstanceIncreaseTime, setLastInstanceIncreaseTime] = useState(null);

  useEffect(() => {
    if (!activeOrgId || !token) return;
    dispatch(fetchDashboardSummary(activeOrgId));
    dispatch(fetchVMs(activeOrgId));
    axios
      .get(`${API_URL}/dashboard/cost-by-resource`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { org_id: activeOrgId },
      })
      .then((res) => setCostByResource(res.data?.data || []))
      .catch(() => setCostByResource([]));
  }, [activeOrgId, token, dispatch]);

  useEffect(() => {
    if (!token || !activeOrgId) return;
    const loadProgress = async () => {
      try {
        const response = await axios.get(`${API_URL}/progress`, {
          headers: { Authorization: `Bearer ${token}` },
          params: { organization_id: activeOrgId },
        });
        setProgress(response?.data?.data || null);
      } catch (error) {
        setProgress(null);
      }
    };
    loadProgress();
  }, [token, activeOrgId]);

  useEffect(() => {
    if (!token || !activeOrgId) return;
    const loadLearningProfile = async () => {
      try {
        const response = await axios.get(`${API_URL}/learning/experience`, {
          headers: { Authorization: `Bearer ${token}` },
          params: { organization_id: activeOrgId },
        });
        setLearningProfile(response?.data?.data || null);
      } catch (error) {
        setLearningProfile(null);
      }
    };
    loadLearningProfile();
  }, [token, activeOrgId]);

  useEffect(() => {
    if (reduxVms) {
      setLiveResources(reduxVms);
    }
  }, [reduxVms]);

  useEffect(() => {
    if (!activeOrgId) return;

    const newSocket = createSocket("/metrics");
    if (!newSocket) return;

    setSocket(newSocket);

    const onConnect = () => {
      setRealtimeStatus("connected");
      newSocket.emit("join_room", { room: `org_${activeOrgId}` });
      console.log("[SOCKET] Connected to /metrics and joined room:", `org_${activeOrgId}`);
    };

    const onDashboardUpdate = (data) => {
      console.log("[SOCKET] Received dashboard_update:", data);
      dispatch(updateDashboardState(data));
      setLastUpdated(new Date(data.timestamp ? data.timestamp * 1000 : Date.now()));
    };

    const onVmCreated = (resource) => {
      console.log("[SOCKET] Received vm_created:", resource);
      if (!resource?.id) return;
      dispatch(upsertVM(resource));
      setLiveResources((prev) => {
        const exists = prev.some((r) => r.id === resource.id || r.instance_id === resource.instance_id);
        return exists ? prev.map(r => (r.id === resource.id || r.instance_id === resource.instance_id) ? resource : r) : [...prev, resource];
      });
    };

    const onVmUpdated = (resource) => {
      console.log("[SOCKET] Received vm_updated:", resource);
      if (!resource?.id) return;
      dispatch(upsertVM(resource));
      setLiveResources((prev) => 
        prev.map(r => (r.id === resource.id || r.instance_id === resource.instance_id) ? resource : r)
      );
    };

    const onVmDeleted = (data) => {
      console.log("[SOCKET] Received vm_deleted:", data);
      const id = data.id || data.instance_id;
      if (!id) return;
      dispatch(removeVM(id));
      setLiveResources((prev) => prev.filter(r => r.id !== id && r.instance_id !== id));
    };

    const onRefresh = (data) => {
      if (data) {
        dispatch(updateDashboardState(data));
      }
    };

    const onError = (message) => {
      setError(
        message?.error?.message ||
          "Live metrics stream is temporarily unavailable.",
      );
    };

    newSocket.on("connect", onConnect);
    newSocket.on("dashboard_update", onDashboardUpdate);
    newSocket.on("dashboard:refresh", onRefresh);
    newSocket.on("vm_created", onVmCreated);
    newSocket.on("vm_updated", onVmUpdated);
    newSocket.on("vm_deleted", onVmDeleted);
    newSocket.on("metrics:error", onError);
    newSocket.on("disconnect", () => setRealtimeStatus("disconnected"));
    newSocket.on("connect_error", () => setRealtimeStatus("disconnected"));

    if (newSocket.connected) onConnect();

    return () => {
      newSocket.off("connect", onConnect);
      newSocket.off("dashboard_update", onDashboardUpdate);
      newSocket.off("dashboard:refresh", onRefresh);
      newSocket.off("vm_created", onVmCreated);
      newSocket.off("vm_updated", onVmUpdated);
      newSocket.off("vm_deleted", onVmDeleted);
      newSocket.off("metrics:error", onError);
      newSocket.off("disconnect");
      newSocket.off("connect_error");
    };
  }, [activeOrgId, dispatch]);

  useEffect(() => {
    if (socket && activeOrgId) {
      socket.emit("join_room", { room: `org_${activeOrgId}` });
    }
  }, [socket, activeOrgId]);

  const summary = reduxSummary || {};
  const chartData = summary.utilization_trend || [];
  
  const [capacityTrend, setCapacityTrend] = useState("stable");

  useEffect(() => {
    const currentQueue = summary.workload?.queue_total_ms || 0;
    if (currentQueue > previousQueueRef.current + 10) {
      setQueueTrend("increasing");
    } else if (currentQueue < previousQueueRef.current - 10) {
      setQueueTrend("decreasing");
    } else if (currentQueue < 10) {
      setQueueTrend("stable");
    }
    previousQueueRef.current = currentQueue;
  }, [summary.workload?.queue_total_ms]);

  useEffect(() => {
    const currentCapacity = summary.running_capacity || summary.workload?.vm_count || 0;
    if (currentCapacity > previousCapacityRef.current && previousCapacityRef.current > 0) {
      setLastInstanceIncreaseTime(Date.now());
      setCapacityTrend("increasing");
    } else if (currentCapacity < previousCapacityRef.current) {
      setCapacityTrend("decreasing");
    } else {
      setCapacityTrend("stable");
    }
    previousCapacityRef.current = currentCapacity;
  }, [summary.running_capacity, summary.workload?.vm_count]);

  let systemStatus = "System Stable";
  let statusColor = "bg-success-50 text-success-600 dark:bg-success-900/20 dark:text-success-400";
  const currentQueueMs = summary.workload?.queue_total_ms || 0;

  if (currentQueueMs > 1800) {
    systemStatus = "Approaching Saturation";
    statusColor = "bg-danger-50 text-danger-600 dark:bg-danger-900/20 dark:text-danger-400";
  } else if ((summary.bpi || 0) > (summary.target_bpi || 0) && (summary.bpi || 0) > 0) {
    systemStatus = "Scaling Triggered";
    statusColor = "bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400";
  } else if (currentQueueMs > 50) {
    if (queueTrend === "decreasing") {
      if (capacityTrend === "increasing" || capacityTrend === "stable") {
        if (capacityTrend === "increasing") {
          systemStatus = "Recovering";
          statusColor = "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400";
        } else {
          systemStatus = "Load Reduced";
          statusColor = "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400";
        }
      } else {
        systemStatus = "Recovering";
        statusColor = "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400";
      }
    } else {
      systemStatus = "System Under Load";
      statusColor = "bg-warning-50 text-warning-600 dark:bg-warning-900/20 dark:text-warning-400";
    }
  }
  
  useEffect(() => {
    if (summary.actions && summary.actions.length > 0) {
      setScalingEvents(prev => {
        // filter out duplicates by checking if the action and reason match the last one exactly
        const lastAction = prev[prev.length - 1];
        const isDuplicate = lastAction && summary.actions.some(a => a.reason === lastAction.reason);
        if (isDuplicate) return prev;

        const newEvents = summary.actions.map(a => ({
          ...a,
          timestamp: Date.now()
        }));
        return [...prev, ...newEvents].slice(-50);
      });
    }
  }, [summary.actions]);

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center">
          <ArrowPathIcon className="mx-auto h-8 w-8 animate-spin text-primary-600" />
          <p className="mt-2 text-sm text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Organization Workspace Banner ── */}
      <div
        style={{
          background:
            "linear-gradient(135deg, #1e40af 0%, #4f46e5 50%, #7c3aed 100%)",
          borderRadius: "12px",
          padding: "20px 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
          boxShadow: "0 4px 24px 0 rgba(79,70,229,0.18)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <div
            style={{
              background: "rgba(255,255,255,0.15)",
              borderRadius: "10px",
              padding: "10px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <BuildingOfficeIcon
              style={{ width: 28, height: 28, color: "#fff" }}
            />
          </div>
          <div>
            <p
              style={{
                color: "rgba(255,255,255,0.75)",
                fontSize: "0.78rem",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                margin: 0,
              }}
            >
              Organization Workspace
            </p>
            <p
              style={{
                color: "#fff",
                fontSize: "1.15rem",
                fontWeight: 700,
                margin: "2px 0 0",
              }}
            >
              Cloud Organization — Unified Tenant
            </p>
          </div>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            flexWrap: "wrap",
          }}
        >
          <span
            style={{
              background: "rgba(255,255,255,0.18)",
              color: "#fff",
              fontSize: "0.75rem",
              fontWeight: 600,
              borderRadius: "20px",
              padding: "4px 12px",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            <ClockIcon style={{ width: 14, height: 14 }} />
            Control Loop: 2s
          </span>
          <span
            style={{
              background: "rgba(255,255,255,0.18)",
              color: "#fff",
              fontSize: "0.75rem",
              fontWeight: 600,
              borderRadius: "20px",
              padding: "4px 12px",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            <ShieldCheckIcon style={{ width: 14, height: 14 }} />
            Multi-Tenant Architecture
          </span>
          <span
            style={{
              background:
                realtimeStatus === "connected"
                  ? "rgba(34,197,94,0.25)"
                  : "rgba(251,191,36,0.25)",
              color: realtimeStatus === "connected" ? "#86efac" : "#fde68a",
              fontSize: "0.75rem",
              fontWeight: 600,
              borderRadius: "20px",
              padding: "4px 12px",
            }}
          >
            {realtimeStatus === "connected" ? "● Live" : "○ Reconnecting"}
          </span>
        </div>
      </div>

      {/* ── Org Scope Note ── */}
      <div
        style={{
          background: "linear-gradient(90deg, #eff6ff 0%, #f5f3ff 100%)",
          border: "1px solid #c7d2fe",
          borderRadius: "8px",
          padding: "10px 16px",
          fontSize: "0.82rem",
          color: "#3730a3",
          fontWeight: 500,
        }}
        className="dark:bg-indigo-900/20 dark:border-indigo-800 dark:text-indigo-300"
      >
        📊 This dashboard represents the{" "}
        <strong>organization-wide control plane</strong> of our Digital Twin
        cloud environment. All resources, security monitoring, and cost tracking
        are centralized under one unified tenant.
      </div>

      {learningProfile?.learning_loop && (
        <div className="overflow-hidden rounded-3xl border border-primary-200 bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 p-6 text-white shadow-xl dark:border-primary-900/40">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-sky-200/80">
                Learning command center
              </p>
              <h2 className="mt-3 text-2xl font-bold text-white">
                {learningProfile.recommended_scenario?.title || "Pick a scenario to start learning"}
              </h2>
              <p className="mt-2 text-sm text-slate-200">
                {learningProfile.role_info?.title || "Student"} • {learningProfile.level?.title || "Beginner"} • {learningProfile.level?.focus || "single-service basics"}
              </p>
              <p className="mt-4 max-w-2xl text-sm text-slate-300">
                {learningProfile.learning_loop.explanation?.why_this_changes_metrics || learningProfile.learning_loop.explanation?.why}
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl bg-white/10 p-3 backdrop-blur">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-200/80">Track</p>
                  <p className="mt-1 text-sm font-medium">{learningProfile.selected_level || learningProfile.learning_track || "beginner"}</p>
                </div>
                <div className="rounded-2xl bg-white/10 p-3 backdrop-blur">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-200/80">Next action</p>
                  <p className="mt-1 text-sm font-medium">{learningProfile.learning_loop.explanation?.what_you_changed || learningProfile.learning_loop.action}</p>
                </div>
                <div className="rounded-2xl bg-white/10 p-3 backdrop-blur">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-200/80">Progress</p>
                  <p className="mt-1 text-sm font-medium">{learningProfile.level?.points ?? 0} pts · {learningProfile.level?.points_to_next ?? 0} to next</p>
                </div>
              </div>
            </div>
            <div className="grid gap-2 text-sm text-slate-200 lg:min-w-[22rem]">
              {[
                ["User", learningProfile.learning_loop.user],
                ["Scenario", learningProfile.learning_loop.scenario],
                ["Action", learningProfile.learning_loop.action],
                ["Simulation", learningProfile.learning_loop.simulation],
                ["Result", learningProfile.learning_loop.result],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl bg-white/10 px-3 py-2 backdrop-blur">
                  <strong>{label}:</strong> {value}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {learningProfile.progression_path?.map((item) => (
              <span
                key={item.level}
                className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-white/90"
              >
                {item.title}
              </span>
            ))}
          </div>
          {learningProfile.progress_timeline?.length > 0 && (
            <div className="mt-5 rounded-2xl bg-white/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-200/80">
                Score trend
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {learningProfile.progress_timeline.slice(-3).map((entry) => (
                  <div key={`${entry.scenario_id}-${entry.updated_at || entry.completed_at}`} className="rounded-xl bg-white/10 px-3 py-2">
                    <p className="text-sm font-medium text-white">{entry.scenario_title}</p>
                    <p className="text-xs text-slate-300">{entry.points_earned} pts · {entry.completed ? "completed" : `step ${entry.current_step}`}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Cloud Simulation Dashboard
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
            <span>
              {lastUpdated
                ? `Updated ${lastUpdated.toLocaleTimeString()}`
                : "Waiting for live metrics"}
            </span>
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                realtimeStatus === "connected"
                  ? "bg-success-50 text-success-600 dark:bg-success-900/20 dark:text-success-400"
                  : "bg-warning-50 text-warning-600 dark:bg-warning-900/20 dark:text-warning-400"
              }`}
            >
              {realtimeStatus === "connected"
                ? "Live stream connected"
                : "Socket reconnecting"}
            </span>
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${statusColor}`}
            >
              {systemStatus}
            </span>

          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            if (activeOrgId) {
              dispatch(fetchDashboardSummary(activeOrgId));
            }
          }}
          className="btn-secondary inline-flex items-center justify-center gap-2"
        >
          <ArrowPathIcon
            className="h-5 w-5"
          />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-danger-100 bg-danger-50 px-4 py-3 text-sm text-danger-700 dark:border-danger-800 dark:bg-danger-900/20 dark:text-danger-100">
          {error}
        </div>
      )}

      {/* ── Security Alert Banner ── */}
      {(reduxSummary?.security?.total_unresolved ?? 0) > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-800 dark:bg-red-900/20">
          <p className="text-sm font-medium text-red-700 dark:text-red-300">
            ⚠ {reduxSummary.security.total_unresolved} unresolved security threat(s)
          </p>
          <button
            type="button"
            onClick={() => navigate("/security")}
            className="shrink-0 text-sm font-semibold text-red-700 underline hover:text-red-900 dark:text-red-300 dark:hover:text-red-100"
          >
            Go to Security →
          </button>
        </div>
      )}

      {/* ── 6 KPI Cards ── */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Total VMs */}
        <div className="card border-l-4 border-primary-500">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Total VMs
              </p>
              <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
                {summary.total_vms ?? 0}
              </p>
            </div>
            <ServerStackIcon className="h-8 w-8 shrink-0 text-primary-500" />
          </div>
        </div>

        {/* Running VMs */}
        <div className="card border-l-4 border-success-500">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Running VMs
              </p>
              <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
                {summary.running_vms ?? 0}
              </p>
            </div>
            <CheckCircleIcon className="h-8 w-8 shrink-0 text-success-500" />
          </div>
        </div>

        {/* Monthly Spend */}
        <div className="card border-l-4 border-purple-500">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Monthly Spend
              </p>
              <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">
                {formatCost(summary.monthly_spend ?? 0)}
              </p>
            </div>
            <CurrencyDollarIcon className="h-8 w-8 shrink-0 text-purple-500" />
          </div>
        </div>

        {/* Security Score */}
        <div
          className={`card border-l-4 ${(summary.security_score ?? 0) >= 80 ? "border-success-500" : "border-danger-500"}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Security Score
              </p>
              <p
                className={`mt-2 text-3xl font-bold ${(summary.security_score ?? 0) >= 80 ? "text-success-600 dark:text-success-400" : "text-danger-600 dark:text-danger-400"}`}
              >
                {summary.security_score ?? 0}/100
              </p>
            </div>
            <ShieldCheckIcon
              className={`h-8 w-8 shrink-0 ${(summary.security_score ?? 0) >= 80 ? "text-success-500" : "text-danger-500"}`}
            />
          </div>
        </div>

        {/* Compliance Score */}
        <div
          className={`card border-l-4 ${(summary.compliance_score ?? 0) >= 80 ? "border-success-500" : "border-warning-500"}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Compliance Score
              </p>
              <p
                className={`mt-2 text-3xl font-bold ${(summary.compliance_score ?? 0) >= 80 ? "text-success-600 dark:text-success-400" : "text-warning-600 dark:text-warning-400"}`}
              >
                {summary.compliance_score ?? 0}/100
              </p>
            </div>
            <CheckCircleIcon
              className={`h-8 w-8 shrink-0 ${(summary.compliance_score ?? 0) >= 80 ? "text-success-500" : "text-warning-500"}`}
            />
          </div>
        </div>

        {/* Health Score */}
        <div
          className={`card border-l-4 ${(summary.health_score ?? 0) >= 80 ? "border-success-500" : "border-danger-500"}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Health Score
              </p>
              <p
                className={`mt-2 text-3xl font-bold ${(summary.health_score ?? 0) >= 80 ? "text-success-600 dark:text-success-400" : "text-danger-600 dark:text-danger-400"}`}
              >
                {summary.health_score ?? 0}/100
              </p>
            </div>
            <BoltIcon
              className={`h-8 w-8 shrink-0 ${(summary.health_score ?? 0) >= 80 ? "text-success-500" : "text-danger-500"}`}
            />
          </div>
        </div>
      </div>

      {/* ── User Progress Card ── */}
      {progress && (
        <div className="card border-l-4 border-amber-500">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <TrophyIcon className="h-8 w-8 shrink-0 text-amber-500" />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Your Progress
                  </p>
                  <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                    Level {progress.level} — {progress.level_title}
                  </p>
                </div>
              </div>
              <div className="mt-3">
                <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
                  <span>XP Progress</span>
                  <span>
                    {progress.xp_for_current_level || 0}/{progress.xp_to_next_level || 100} XP
                  </span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-gray-200 dark:bg-gray-700">
                  <div
                    className="h-2 rounded-full bg-amber-500 transition-all"
                    style={{
                      width: `${Math.min(100, ((progress.xp_for_current_level || 0) / (progress.xp_to_next_level || 100)) * 100)}%`,
                    }}
                  />
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
                <span>
                  <strong>{progress.vms_created}</strong> VMs created
                </span>
                <span>
                  <strong>{progress.scenarios_completed?.length || 0}</strong> scenarios completed
                </span>
                <span>
                  <strong>{progress.attacks_simulated}</strong> attacks simulated
                </span>
              </div>
              {progress.badges && progress.badges.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {progress.badges.map((badge) => (
                    <span
                      key={badge}
                      className="inline-flex items-center rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
                    >
                      🏆 {badge}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-5">
        <StatCard
          title="Queue Depth"
          value={`${Number(summary.workload?.queue_total_ms || 0).toFixed(0)} ms`}
          subtitle="Pending work backlog"
          icon={ServerStackIcon}
          accentClass="bg-warning-500"
        />
        <StatCard
          title="P95 Latency"
          value={`${Number(summary.workload?.p95_latency_ms || 0).toFixed(0)} ms`}
          subtitle="95th percentile response time"
          icon={BoltIcon}
          accentClass="bg-primary-500"
        />
        <StatCard
          title="Backlog Per Instance (BPI)"
          value={`${Number(summary.bpi || 0).toFixed(1)} ms per instance`}
          subtitle={`Target BPI: ${Number(summary.target_bpi || 0).toFixed(1)}`}
          icon={ChartBarIcon}
          accentClass="bg-purple-500"
        />
        <StatCard
          title="Dropped Requests"
          value={`${summary.workload?.dropped_requests_total || 0}`}
          subtitle="Dropped due to queue capacity limit"
          icon={ArrowPathIcon}
          accentClass="bg-danger-500"
        />
        <StatCard
          title="Auto-Scaling Capacity"
          value={`${summary.capacity || 1} Desired VMs`}
          subtitle={
            <span className="flex flex-col gap-0.5">
              <span>Running Instances: {summary.running_capacity || summary.workload?.vm_count || 0}</span>
              {scalingEvents.length > 0 && (
                <span className="text-[11px] text-gray-400 dark:text-gray-500">
                  Last trigger: {new Date(scalingEvents[scalingEvents.length - 1].timestamp).toLocaleTimeString()}
                </span>
              )}
              {lastInstanceIncreaseTime && (
                <span className="text-[11px] text-gray-400 dark:text-gray-500">
                  Instances active: {new Date(lastInstanceIncreaseTime).toLocaleTimeString()}
                </span>
              )}
            </span>
          }
          icon={CpuChipIcon}
          accentClass="bg-success-500"
        />
      </div>



      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="card xl:col-span-2">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Organization-Wide Resource Trends
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Live CPU &amp; memory across the entire cloud organization
                tenant
              </p>
            </div>
            <ChartBarIcon className="h-6 w-6 text-gray-400" />
          </div>
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="time"
                tickFormatter={formatChartTime}
                minTickGap={32}
              />
              <YAxis tickFormatter={(value) => `${value}%`} width={48} />
              <Tooltip content={<ChartTooltip />} />
              <Line
                type="monotone"
                dataKey="cpu"
                name="CPU"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="memory"
                name="Memory"
                stroke="#16a34a"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
            Memory Pressure
          </h2>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="memoryFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#16a34a" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#16a34a" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="time" tickFormatter={formatChartTime} hide />
              <YAxis tickFormatter={(value) => `${value}%`} width={44} />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="memory"
                name="Memory"
                stroke="#16a34a"
                fill="url(#memoryFill)"
              />
            </AreaChart>
          </ResponsiveContainer>
          <div className="mt-4 space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-gray-500 dark:text-gray-400">
                CPU cost base
              </span>
              <span className="font-medium text-gray-900 dark:text-white">
                {formatPercent(summary.cpu_avg)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-500 dark:text-gray-400">
                Memory cost base
              </span>
              <span className="font-medium text-gray-900 dark:text-white">
                {formatPercent(summary.memory_avg)}
              </span>
            </div>
            <div className="rounded-lg bg-gray-50 p-3 text-gray-600 dark:bg-gray-700/50 dark:text-gray-300">
              Usage is within the expected simulated range.
            </div>
          </div>
        </div>
      </div>

      {Array.isArray(summary.cost_trend) && summary.cost_trend.length > 0 && (
        <div className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Cost Trend
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Cumulative spend over the current simulation window
              </p>
            </div>
            <CurrencyDollarIcon className="h-6 w-6 text-gray-400" />
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={summary.cost_trend}>
              <defs>
                <linearGradient id="costFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#7c3aed" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              {/* dataKey="name" — backend sends {name: "HH:MM", cost: float} */}
              <XAxis dataKey="name" minTickGap={40} />
              <YAxis
                tickFormatter={(v) => `$${Number(v || 0).toFixed(3)}`}
                width={64}
              />
              <Tooltip
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm dark:border-gray-700 dark:bg-gray-800">
                      <p className="font-medium text-gray-900 dark:text-white">
                        {label}
                      </p>
                      {payload.map((item) => (
                        <p key={item.dataKey} style={{ color: item.color }}>
                          {item.name}: {formatCost(item.value)}
                        </p>
                      ))}
                    </div>
                  ) : null
                }
              />
              <Area
                type="monotone"
                dataKey="cost"
                name="Cost"
                stroke="#7c3aed"
                fill="url(#costFill)"
                strokeWidth={2}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {Array.isArray(summary.utilization_trend) &&
        summary.utilization_trend.length > 0 && (
          <div className="card">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Utilization Trend
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  CPU &amp; memory utilization streamed from the resource
                  simulator
                </p>
              </div>
              <ChartBarIcon className="h-6 w-6 text-gray-400" />
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={summary.utilization_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                {/* dataKey="timestamp" */}
                <XAxis dataKey="timestamp" tickFormatter={formatChartTime} minTickGap={40} />
                <YAxis
                  tickFormatter={(v) => `${Number(v || 0).toFixed(1)}%`}
                  width={52}
                />
                <Tooltip
                  content={({ active, payload, label }) =>
                    active && payload?.length ? (
                      <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm dark:border-gray-700 dark:bg-gray-800">
                        <p className="font-medium text-gray-900 dark:text-white">
                          {label}
                        </p>
                        {payload.map((item) => (
                          <p key={item.dataKey} style={{ color: item.color }}>
                            {item.name}: {Number(item.value || 0).toFixed(2)}%
                          </p>
                        ))}
                      </div>
                    ) : null
                  }
                />
                <Line
                  type="monotone"
                  dataKey="cpu_avg"
                  name="CPU"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="memory_avg"
                  name="Memory"
                  stroke="#16a34a"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

      {/* ── Bottom row: Recent Activity + Live Resources ── */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Recent Activity */}
        <div className="card">
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
            Scaling Events & Recent Activity
          </h2>
          {scalingEvents.length > 0 ? (
            <ul className="space-y-3">
              {[...scalingEvents].reverse().map((event, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-3 rounded-lg bg-purple-50 px-3 py-2 dark:bg-purple-900/20"
                >
                  <BoltIcon className="h-4 w-4 text-purple-600 shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-purple-900 dark:text-purple-300">
                      {event.type === 'scale_up' ? 'Scale Out (Up)' : event.type === 'scale_down' ? 'Scale In (Down)' : 'Scaling Action'}
                    </p>
                    <p className="mt-0.5 text-xs text-purple-700 dark:text-purple-400">
                      {event.reason || event.message}
                    </p>
                    {event.timestamp && (
                      <p className="mt-1 text-[10px] text-purple-500/70 dark:text-purple-400/50 uppercase tracking-wider">
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : Array.isArray(summary.recent_activity) && summary.recent_activity.length > 0 ? (
            <ul className="space-y-3">
              {summary.recent_activity.map((event, idx) => (
                <li
                  key={event.id ?? idx}
                  className="flex items-start gap-3 rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/40"
                >
                  {activityIcon(event.action)}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                      {event.action || event.title || "Resource event"}
                      {event.resource_name && (
                        <span className="ml-1 font-normal text-gray-500 dark:text-gray-400">
                          — {event.resource_name}
                        </span>
                      )}
                    </p>
                    {(event.details) && (
                      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                        {event.details}
                      </p>
                    )}
                    {event.timestamp && (
                      <p className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </p>
                    )}
                  </div>
                  {event.resource_type && (
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${resourceTypeBadge(event.resource_type)}`}
                    >
                      {event.resource_type}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500">
              No recent scaling events or activity.
            </p>
          )}

        </div>

        {/* Live Resources */}
        <div className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Live Resources
            </h2>
            <span className="rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-semibold text-primary-700 dark:bg-primary-900/20 dark:text-primary-300">
              {liveResources.length} provisioned
            </span>
          </div>
          {liveResources.length > 0 ? (
            <ul className="space-y-2">
              {liveResources.map((resource) => (
                <li
                  key={resource.id}
                  className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-700/40"
                >
                  <ServerStackIcon className="h-5 w-5 shrink-0 text-primary-500" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                      {resource.name || resource.id}
                    </p>
                    {resource.region && (
                      <p className="text-xs text-gray-400 dark:text-gray-500">
                        {resource.region}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${resourceTypeBadge(resource.type || resource.resource_type)}`}
                    >
                      {resource.type || resource.resource_type || "resource"}
                    </span>
                    <span
                      className={`text-xs font-medium ${
                        resource.status === "running"
                          ? "text-success-600 dark:text-success-400"
                          : "text-gray-400"
                      }`}
                    >
                      {resource.status || "unknown"}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500">
              No live resources yet — provision a VM or database to see it here
              in real time.
            </p>
          )}
        </div>
      </div>
      {/* ── Cost by Resource ── */}
      <div className="card">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Cost by Resource
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Accumulated cost per VM / database
            </p>
          </div>
          <CurrencyDollarIcon className="h-6 w-6 text-gray-400" />
        </div>
        {costByResource.length > 0 ? (
          <ResponsiveContainer width="100%" height={Math.max(120, costByResource.length * 36)}>
            <BarChart
              layout="vertical"
              data={costByResource}
              margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis
                type="number"
                tickFormatter={(v) => `$${Number(v).toFixed(3)}`}
                tick={{ fontSize: 11 }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={140}
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload || {};
                  return (
                    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm dark:border-gray-700 dark:bg-gray-800">
                      <p className="font-semibold text-gray-900 dark:text-white">{d.name}</p>
                      <p className="text-gray-500 dark:text-gray-400 capitalize">{d.type}</p>
                      <p className="text-gray-500 dark:text-gray-400">{d.instance_type}</p>
                      <p className="mt-1 font-medium text-gray-900 dark:text-white">
                        ${Number(d.cost).toFixed(4)}
                      </p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
                {costByResource.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.type === "database" ? "#f59e0b" : "#6366f1"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-gray-400 dark:text-gray-500">
            No cost data yet. Create resources to see breakdown.
          </p>
        )}
      </div>

      {/* ── Running Resources mini-table ── */}
      <div className="card">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Running Resources
          </h2>
          <button
            type="button"
            onClick={() => navigate("/resources")}
            className="text-sm font-medium text-primary-600 hover:text-primary-800 dark:text-primary-400 dark:hover:text-primary-200"
          >
            View all →
          </button>
        </div>
        {reduxVms.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-700">
              <thead>
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  <th className="pb-2 pr-4">Name</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4 min-w-[120px]">CPU %</th>
                  <th className="pb-2">Cost/hr</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {reduxVms.slice(0, 5).map((vm) => {
                  const cpu = Number(vm.cpu_utilization ?? vm.cpu ?? 0);
                  return (
                    <tr
                      key={vm.id}
                      onClick={() => navigate("/resources")}
                      className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40"
                    >
                      <td className="py-2 pr-4 font-medium text-gray-900 dark:text-white">
                        {vm.name}
                      </td>
                      <td className="py-2 pr-4 text-gray-500 dark:text-gray-400">
                        {vm.instance_type || "vm"}
                      </td>
                      <td className="py-2 pr-4">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${
                            vm.status === "running"
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : vm.status === "stopped"
                              ? "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                              : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                          }`}
                        >
                          {vm.status || "unknown"}
                        </span>
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                            <div
                              className={`h-2 rounded-full ${
                                cpu > 80 ? "bg-red-500" : "bg-blue-500"
                              }`}
                              style={{ width: `${Math.min(cpu, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {cpu.toFixed(1)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-2 text-gray-700 dark:text-gray-300">
                        ${Number(vm.hourly_rate ?? 0).toFixed(4)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-400 dark:text-gray-500">
            No VMs found — create a resource to see it here.
          </p>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
