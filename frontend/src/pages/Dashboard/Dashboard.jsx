import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowPathIcon,
  BoltIcon,
  ChartBarIcon,
  CpuChipIcon,
  CurrencyDollarIcon,
  ServerStackIcon,
} from '@heroicons/react/24/outline';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  createMetricsSocket,
  fetchSimulationDashboard,
  fetchSimulationStats,
} from '../../services/simulationApi';

const REFRESH_INTERVAL_MS = 5000;
const METRIC_POINTS = 30;

const toPercent = (value) => Number(value || 0) * 100;

const formatPercent = (value, digits = 2) => `${toPercent(value).toFixed(digits)}%`;

const formatChartTime = (value) =>
  new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

const formatCost = (value) => `$${Number(value || 0).toFixed(4)}`;

const getErrorMessage = (requestError) =>
  requestError.response?.data?.error?.message ||
  requestError.response?.data?.error ||
  'Unable to load simulation dashboard.';

const keepRecentMetrics = (metrics) => metrics.slice(-METRIC_POINTS);

const smoothMetricSeries = (metrics) =>
  metrics.reduce((series, point, index) => {
    const rawCpu = toPercent(point.cpu);
    const rawMemory = toPercent(point.memory);
    const previous = series[index - 1];
    const cpu = previous ? rawCpu * 0.5 + previous.cpu * 0.5 : rawCpu;
    const memory = previous ? rawMemory * 0.5 + previous.memory * 0.5 : rawMemory;

    series.push({
      ...point,
      cpu,
      memory,
      rawCpu,
      rawMemory,
    });
    return series;
  }, []);

const StatCard = ({ title, value, subtitle, icon: Icon, accentClass }) => (
  <div className="card">
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
        <p className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
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
      <p className="font-medium text-gray-900 dark:text-white">{formatChartTime(label)}</p>
      {payload.map((item) => (
        <p key={item.dataKey} style={{ color: item.color }}>
          {item.name}: {Number(item.value || 0).toFixed(2)}%
        </p>
      ))}
      {payload[0]?.payload?.anomaly && (
        <p className="mt-1 font-medium text-warning-600 dark:text-warning-400">
          CPU anomaly detected
        </p>
      )}
    </div>
  );
};

const Dashboard = () => {
  const [dashboard, setDashboard] = useState({
    metrics: [],
    summary: null,
    peaks: null,
    cost: null,
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [realtimeStatus, setRealtimeStatus] = useState('connecting');

  const loadDashboard = useCallback(async ({ silent = false } = {}) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const data = await fetchSimulationDashboard(METRIC_POINTS);
      setDashboard({
        ...data,
        metrics: keepRecentMetrics(data.metrics || []),
      });
      setLastUpdated(new Date());
      setError(null);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const refreshStats = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await fetchSimulationStats(METRIC_POINTS);
      setDashboard((previous) => ({
        ...previous,
        ...data,
      }));
      setLastUpdated(new Date());
      setError(null);
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
    const refreshTimer = setInterval(() => {
      refreshStats();
    }, REFRESH_INTERVAL_MS);

    return () => clearInterval(refreshTimer);
  }, [loadDashboard, refreshStats]);

  useEffect(() => {
    const socket = createMetricsSocket();

    socket.on('connect', () => {
      setRealtimeStatus('connected');
    });

    socket.on('disconnect', () => {
      setRealtimeStatus('disconnected');
    });

    socket.on('connect_error', () => {
      setRealtimeStatus('disconnected');
    });

    socket.on('metrics:update', (message) => {
      const metric = message?.data;
      if (!metric) {
        return;
      }

      setDashboard((previous) => ({
        ...previous,
        metrics: keepRecentMetrics([...(previous.metrics || []), metric]),
      }));
      setLastUpdated(new Date());
      setError(null);
    });

    socket.on('metrics:error', (message) => {
      setError(message?.error?.message || 'Live metrics stream is temporarily unavailable.');
    });

    return () => socket.disconnect();
  }, []);

  const chartData = useMemo(() => smoothMetricSeries(dashboard.metrics), [dashboard.metrics]);

  const latestMetric = dashboard.metrics[dashboard.metrics.length - 1] || { cpu: 0, memory: 0 };
  const currentMetric = {
    cpu: toPercent(latestMetric.cpu),
    memory: toPercent(latestMetric.memory),
    anomaly: Boolean(latestMetric.anomaly),
  };
  const summary = dashboard.summary || {};
  const peaks = dashboard.peaks || {};
  const cost = dashboard.cost || {};

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center">
          <ArrowPathIcon className="mx-auto h-8 w-8 animate-spin text-primary-600" />
          <p className="mt-3 text-sm font-medium text-gray-600 dark:text-gray-300">
            Loading simulation dashboard...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Cloud Simulation Dashboard
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
            <span>
              {lastUpdated
                ? `Updated ${lastUpdated.toLocaleTimeString()}`
                : 'Waiting for live metrics'}
            </span>
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                realtimeStatus === 'connected'
                  ? 'bg-success-50 text-success-600 dark:bg-success-900/20 dark:text-success-400'
                  : 'bg-warning-50 text-warning-600 dark:bg-warning-900/20 dark:text-warning-400'
              }`}
            >
              {realtimeStatus === 'connected' ? 'Live stream connected' : 'Socket reconnecting'}
            </span>
            {refreshing && <span className="text-xs text-primary-600">Refreshing stats...</span>}
          </div>
        </div>
        <button
          type="button"
          onClick={() => loadDashboard()}
          className="btn-secondary inline-flex items-center justify-center gap-2"
        >
          <ArrowPathIcon className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-danger-100 bg-danger-50 px-4 py-3 text-sm text-danger-700 dark:border-danger-800 dark:bg-danger-900/20 dark:text-danger-100">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Current CPU"
          value={`${currentMetric.cpu.toFixed(2)}%`}
          subtitle={currentMetric.anomaly ? 'CPU anomaly detected' : `Average ${formatPercent(summary.cpu_avg)}`}
          icon={CpuChipIcon}
          accentClass={currentMetric.anomaly ? 'bg-warning-500' : 'bg-primary-500'}
        />
        <StatCard
          title="Current Memory"
          value={`${currentMetric.memory.toFixed(2)}%`}
          subtitle={`Average ${formatPercent(summary.mem_avg)}`}
          icon={ServerStackIcon}
          accentClass="bg-success-500"
        />
        <StatCard
          title="Peak Usage"
          value={formatPercent(peaks.cpu_peak)}
          subtitle={`Memory peak ${formatPercent(peaks.memory_peak)}`}
          icon={BoltIcon}
          accentClass="bg-warning-500"
        />
        <StatCard
          title="Estimated Cost"
          value={formatCost(cost.cost)}
          subtitle={`Priority factor ${Number(cost.priority_factor || 0).toFixed(2)}`}
          icon={CurrencyDollarIcon}
          accentClass="bg-purple-500"
        />
      </div>

      {currentMetric.anomaly && (
        <div className="rounded-lg border border-warning-100 bg-warning-50 px-4 py-3 text-sm text-warning-800 dark:border-warning-800 dark:bg-warning-900/20 dark:text-warning-100">
          Live anomaly detected in the latest CPU point. The simulator is flagging a short spike pattern.
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="card xl:col-span-2">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                CPU and Memory Usage
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Socket updates live; summary stats refresh every 5 seconds
              </p>
            </div>
            <ChartBarIcon className="h-6 w-6 text-gray-400" />
          </div>
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="time" tickFormatter={formatChartTime} minTickGap={32} />
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
              <span className="text-gray-500 dark:text-gray-400">CPU cost base</span>
              <span className="font-medium text-gray-900 dark:text-white">
                {formatPercent(cost.cpu_avg)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-500 dark:text-gray-400">Memory cost base</span>
              <span className="font-medium text-gray-900 dark:text-white">
                {formatPercent(cost.mem_avg)}
              </span>
            </div>
            <div className="rounded-lg bg-gray-50 p-3 text-gray-600 dark:bg-gray-700/50 dark:text-gray-300">
              {cost.recommendation || 'Usage is within the expected simulated range.'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
