import React, { useEffect, useMemo, useState } from 'react';
import { useSelector } from 'react-redux';
import axios from 'axios';
import {
  PlusIcon,
  CircleStackIcon,
  StopIcon,
  TrashIcon,
  ServerIcon,
  PlayIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const statusClass = (status) => {
  if (status === 'running') return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
  if (status === 'stopped') return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400';
  if (status === 'creating') return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
  return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400';
};

const Resources = () => {
  const { token } = useSelector((state) => state.auth);
  const { currentOrganization } = useSelector((state) => state.organization);

  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createMode, setCreateMode] = useState('vm');
  const [selectedVM, setSelectedVM] = useState(null);
  const [newVM, setNewVM] = useState({
    name: '',
    engine: 'PostgreSQL',
    instance_type: 't2.micro',
  });

  const authHeaders = useMemo(() => (
    token ? { Authorization: `Bearer ${token}` } : {}
  ), [token]);

  const loadResources = async () => {
    if (!token) {
      setResources([]);
      return;
    }

    setLoading(true);
    try {
      const query = currentOrganization?.id ? `?organization_id=${currentOrganization.id}` : '';
      const response = await axios.get(`${API_URL}/resources${query}`, { headers: authHeaders });
      const payload = response?.data?.data;
      setResources(Array.isArray(payload) ? payload : []);
    } catch (error) {
      setResources([]);
      toast.error(error?.response?.data?.error?.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResources();

    if (!token) return undefined;

    const refreshTimer = setInterval(() => {
      loadResources();
    }, 5000);

    return () => clearInterval(refreshTimer);
  }, [token, currentOrganization, authHeaders]);

  const handleCreateResource = async (e) => {
    e.preventDefault();

    try {
      const payload = {
        name: newVM?.name,
        type: createMode,
        organization_id: currentOrganization?.id,
      };

      if (createMode === 'database') {
        payload.engine = newVM?.engine;
      } else {
        payload.instance_type = newVM?.instance_type;
      }

      const response = await axios.post(
        `${API_URL}/resources/create?type=${createMode}`,
        payload,
        { headers: authHeaders }
      );

      const created = response?.data?.data || {};
      setResources((prev) => [...prev, created]);
      setSelectedVM(created);
      setShowCreateModal(false);
      setNewVM({ name: '', engine: 'PostgreSQL', instance_type: 't2.micro' });
      toast.success(createMode === 'database' ? 'Database created successfully' : 'VM created successfully');
    } catch (error) {
      toast.error(error?.response?.data?.error?.message || "Something went wrong");
    }
  };

  const handleDeleteVM = async (resource) => {
    const resourceId = selectedVM?.id || resource?.id;
    if (!resourceId) return;

    try {
      await axios.delete(`${API_URL}/resources/${resourceId}`, { headers: authHeaders });
      setResources((prev) => prev.filter((item) => item?.id !== resourceId));
      if (selectedVM?.id === resourceId) {
        setSelectedVM(null);
      }
      toast.success('VM deleted');
    } catch (error) {
      toast.error(error?.response?.data?.error?.message || "Something went wrong");
    }
  };

  const handleStopVM = async (resource) => {
    const resourceId = selectedVM?.id || resource?.id;
    if (!resourceId) return;

    try {
      const response = await axios.post(
        `${API_URL}/resources/${resourceId}/stop`,
        {},
        { headers: authHeaders }
      );

      const updated = response?.data?.data || {};
      setResources((prev) => prev.map((item) => (item?.id === resourceId ? updated : item)));
      if (selectedVM?.id === resourceId) {
        setSelectedVM(updated);
      }
      toast.success('VM stopped');
    } catch (error) {
      toast.error(error?.response?.data?.error?.message || "Something went wrong");
    }
  };

  const handleStartVM = async (resource) => {
    const resourceId = resource?.id;
    if (!resourceId) return;

    try {
      const response = await axios.post(
        `${API_URL}/resources/${resourceId}/start`,
        {},
        { headers: authHeaders }
      );

      const updated = response?.data?.data || {};
      setResources((prev) => prev.map((item) => (item?.id === resourceId ? updated : item)));
      if (selectedVM?.id === resourceId) {
        setSelectedVM(updated);
      }
      toast.success('Resource started');
    } catch (error) {
      toast.error(error?.response?.data?.error?.message || "Something went wrong");
    }
  };

  const handleRestartVM = async (resource) => {
    const resourceId = resource?.id;
    if (!resourceId) return;

    try {
      const response = await axios.post(
        `${API_URL}/resources/${resourceId}/restart`,
        {},
        { headers: authHeaders }
      );

      const updated = response?.data?.data || {};
      setResources((prev) => prev.map((item) => (item?.id === resourceId ? updated : item)));
      if (selectedVM?.id === resourceId) {
        setSelectedVM(updated);
      }
      toast.success('Resource restarting...');
    } catch (error) {
      toast.error(error?.response?.data?.error?.message || "Something went wrong");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Resources</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Selected VM: {selectedVM?.name || 'None'} ({selectedVM?.id || 'n/a'})
          </p>
        </div>
        {currentOrganization?.my_role !== 'viewer' && (
          <>
            <button
              onClick={() => {
                setCreateMode('database');
                setShowCreateModal(true);
              }}
              className="btn-secondary flex items-center space-x-2"
            >
              <CircleStackIcon className="w-5 h-5" />
              <span>Create DB</span>
            </button>
            <button
              onClick={() => {
                setCreateMode('vm');
                setShowCreateModal(true);
              }}
              className="btn-primary flex items-center space-x-2"
            >
              <PlusIcon className="w-5 h-5" />
              <span>Create VM</span>
            </button>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {resources?.map((resource) => {
          const safeId = resource?.id || 'fallback-id';
          const cpuPercent = Math.round(Number(resource?.cpu || 0) * 100);
          const memoryPercent = Math.round(Number(resource?.memory || 0) * 100);

          return (
            <div
              key={safeId}
              className="card p-6 flex flex-col hover:border-primary-500 transition-colors border border-transparent cursor-pointer"
              onClick={() => setSelectedVM(resource || null)}
            >
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center">
                  <ServerIcon className="w-6 h-6 text-gray-400 mr-3" />
                  <div>
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                      {resource?.name || 'Unnamed resource'}
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {resource?.type === 'database' ? `Database (${resource?.engine || 'DB'})` : 'Virtual Machine'}
                    </p>
                  </div>
                </div>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${statusClass(resource?.status)}`}>
                  {resource?.status || 'unknown'}
                </span>
              </div>

              <div className="space-y-4 mb-6 flex-1 mt-2">
                <div>
                  <div className="flex justify-between text-sm mb-1 text-gray-700 dark:text-gray-300">
                    <span>CPU Usage</span>
                    <span className="font-medium">{cpuPercent}%</span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full"
                      style={{ width: `${cpuPercent}%` }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1 text-gray-700 dark:text-gray-300">
                    <span>Memory Usage</span>
                    <span className="font-medium">{memoryPercent}%</span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full"
                      style={{ width: `${memoryPercent}%` }}
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t border-gray-100 dark:border-gray-700 mt-auto">
                {currentOrganization?.my_role !== 'viewer' && resource?.status === 'stopped' && (
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      handleStartVM(resource);
                    }}
                    className="p-2 text-success-600 hover:bg-success-50 dark:hover:bg-success-900/20 rounded-lg transition-colors text-green-600"
                    title="Start Resource"
                  >
                    <PlayIcon className="w-5 h-5" />
                  </button>
                )}
                {currentOrganization?.my_role !== 'viewer' && resource?.status === 'running' && (
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      handleRestartVM(resource);
                    }}
                    className="p-2 text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors"
                    title="Restart Resource"
                  >
                    <ArrowPathIcon className="w-5 h-5" />
                  </button>
                )}
                {currentOrganization?.my_role !== 'viewer' && resource?.status === 'running' && (
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      handleStopVM(resource);
                    }}
                    className="p-2 text-warning-600 hover:bg-warning-50 dark:hover:bg-warning-900/20 rounded-lg transition-colors"
                    title="Stop Resource"
                  >
                    <StopIcon className="w-5 h-5" />
                  </button>
                )}
                {(currentOrganization?.my_role === 'admin' || currentOrganization?.my_role === 'owner') && (
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      handleDeleteVM(resource);
                    }}
                    className="p-2 text-danger-600 hover:bg-danger-50 dark:hover:bg-danger-900/20 rounded-lg transition-colors"
                    title="Delete Resource"
                  >
                    <TrashIcon className="w-5 h-5" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {resources?.length === 0 && !loading && (
          <div className="col-span-full py-16 text-center bg-white dark:bg-gray-800 rounded-xl border border-dashed border-gray-300 dark:border-gray-700 shadow-sm">
            <ServerIcon className="mx-auto h-12 w-12 text-gray-400 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-1">No resources yet</h3>
            <p className="text-gray-500 dark:text-gray-400">Create your first VM or Database to get started.</p>
          </div>
        )}
        {loading && (
          <div className="col-span-full py-16 text-center text-gray-500 dark:text-gray-400">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto mb-4"></div>
            Loading resources...
          </div>
        )}
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-md mx-4">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              {createMode === 'database' ? 'Create Database' : 'Create Virtual Machine'}
            </h2>
            <form onSubmit={handleCreateResource} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {createMode === 'database' ? 'Database Name' : 'VM Name'}
                </label>
                <input
                  type="text"
                  className="input-field"
                  value={newVM?.name || ''}
                  onChange={(event) => setNewVM({ ...newVM, name: event.target.value })}
                  placeholder={createMode === 'database' ? 'e.g., analytics-db' : 'e.g., web-server-01'}
                />
              </div>
              {createMode === 'database' ? (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Engine
                  </label>
                  <select
                    className="input-field"
                    value={newVM?.engine || 'PostgreSQL'}
                    onChange={(event) => setNewVM({ ...newVM, engine: event.target.value })}
                  >
                    <option value="PostgreSQL">PostgreSQL</option>
                    <option value="MySQL">MySQL</option>
                    <option value="MongoDB">MongoDB</option>
                  </select>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      VM Size
                    </label>
                    <select
                      className="input-field"
                      value={newVM?.instance_type || 't2.micro'}
                      onChange={(event) => setNewVM({ ...newVM, instance_type: event.target.value })}
                    >
                      <option value="t2.micro">t2.micro (1 CPU, 1 GB)</option>
                      <option value="t2.small">t2.small (1 CPU, 2 GB)</option>
                      <option value="t2.medium">t2.medium (2 CPU, 4 GB)</option>
                    </select>
                  </div>
                  <div className="flex space-x-4">
                    <div className="flex-1">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">CPU</label>
                      <input 
                        type="text" 
                        className="input-field bg-gray-100 dark:bg-gray-700 text-gray-500 cursor-not-allowed" 
                        disabled 
                        value={newVM?.instance_type === 't2.medium' ? '2 Core' : '1 Core'} 
                      />
                    </div>
                    <div className="flex-1">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Memory</label>
                      <input 
                        type="text" 
                        className="input-field bg-gray-100 dark:bg-gray-700 text-gray-500 cursor-not-allowed" 
                        disabled 
                        value={newVM?.instance_type === 't2.medium' ? '4 GB' : newVM?.instance_type === 't2.small' ? '2 GB' : '1 GB'} 
                      />
                    </div>
                  </div>
                </>
              )}
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  {createMode === 'database' ? 'Create Database' : 'Create VM'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Resources;
