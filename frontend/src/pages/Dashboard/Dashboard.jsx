import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchDashboardSummary } from '../../store/slices/dashboardSlice';
import {
  ServerIcon,
  ShieldCheckIcon,
  CurrencyDollarIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts';
const StatCard = ({ title, value, subtitle, icon: Icon, trend, color }) => (
  <div className="card">
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">{title}</p>
        <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{value}</p>
        {subtitle && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{subtitle}</p>
        )}
        {trend && (
          <p className={`text-sm mt-2 ${trend >= 0 ? 'text-success-600' : 'text-danger-600'}`}>
            {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}% from last month
          </p>
        )}
      </div>
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
    </div>
  </div>
);
const Dashboard = () => {
  const dispatch = useDispatch();
  const { currentOrganization } = useSelector((state) => state.organization);
  const { summary } = useSelector((state) => state.dashboard);
  useEffect(() => {
    if (currentOrganization) {
      dispatch(fetchDashboardSummary(currentOrganization.id));
    }
  }, [dispatch, currentOrganization]);
  // Sample data for charts
  const costData = [
    { name: 'Week 1', cost: 4000 },
    { name: 'Week 2', cost: 3000 },
    { name: 'Week 3', cost: 5000 },
    { name: 'Week 4', cost: 2780 },
  ];
  const utilizationData = [
    { name: '00:00', cpu: 20, memory: 40 },
    { name: '04:00', cpu: 15, memory: 35 },
    { name: '08:00', cpu: 45, memory: 60 },
    { name: '12:00', cpu: 65, memory: 70 },
    { name: '16:00', cpu: 55, memory: 65 },
    { name: '20:00', cpu: 35, memory: 50 },
  ];
  if (!currentOrganization) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <p className="text-gray-500 dark:text-gray-400">Please select or create an organization</p>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <div className="flex items-center space-x-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">Health Score:</span>
          <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
            summary?.health_score >= 80 ? 'bg-success-100 text-success-800' :
            summary?.health_score >= 60 ? 'bg-warning-100 text-warning-800' :
            'bg-danger-100 text-danger-800'
          }`}>
            {summary?.health_score || 0}/100
          </span>
        </div>
      </div>
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Resources"
          value={`${summary?.resources?.vms?.total || 0} VMs, ${summary?.resources?.databases?.total || 0} DBs`}
          subtitle={`${summary?.resources?.vms?.running || 0} running`}
          icon={ServerIcon}
          color="bg-primary-500"
          trend={12}
        />
        <StatCard
          title="Security Status"
          value={summary?.security?.active_threats > 0 ? `${summary.security.active_threats} Threats` : 'Secure'}
          subtitle={summary?.security?.active_threats > 0 ? 'Action required' : 'All systems protected'}
          icon={ShieldCheckIcon}
          color={summary?.security?.active_threats > 0 ? 'bg-danger-500' : 'bg-success-500'}
        />
        <StatCard
          title="Monthly Cost"
          value={`$${summary?.costs?.current_month_spend?.toFixed(2) || '0.00'}`}
          subtitle="Current spend"
          icon={CurrencyDollarIcon}
          color="bg-warning-500"
          trend={-5}
        />
        <StatCard
          title="Optimization"
          value="3 Recommendations"
          subtitle="Potential savings: $450/mo"
          icon={ChartBarIcon}
          color="bg-purple-500"
        />
      </div>
      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Cost Trend
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={costData}>
              <defs>
                <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Area type="monotone" dataKey="cost" stroke="#3b82f6" fillOpacity={1} fill="url(#colorCost)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Resource Utilization
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={utilizationData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="cpu" stroke="#3b82f6" name="CPU %" />
              <Line type="monotone" dataKey="memory" stroke="#10b981" name="Memory %" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      {/* Recent Activity */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Recent Activity
        </h3>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center space-x-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <div className="w-2 h-2 bg-primary-500 rounded-full"></div>
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {i === 1 ? 'New VM instance created' : i === 2 ? 'Security threat detected and blocked' : 'Cost optimization applied'}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {i * 2} hours ago
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
export default Dashboard;
