import React, { useEffect, useMemo, useState } from 'react';
import { useSelector } from 'react-redux';
import axios from 'axios';
import {
  PlusIcon,
  CircleStackIcon,
  StopIcon,
  TrashIcon,
  ServerIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const statusClass = (status) => {
  if (status === 'running') return 'status-running';
  if (status === 'stopped') return 'status-stopped';
  return 'status-warning';
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
      toast.error(error?.response?.data?.error?.message || 'Failed to load resources');
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
      const response = await axios.post(
        `${API_URL}/resources/create?type=${createMode}`,
        {
          name: newVM?.name,
          engine: newVM?.engine,
          org_id: currentOrganization?.id,
        },
        { headers: authHeaders }
      );

      const created = response?.data?.data || {};
      setResources((prev) => [...prev, created]);
      setSelectedVM(created);
      setShowCreateModal(false);
      setNewVM({ name: '', engine: 'PostgreSQL' });
      toast.success(createMode === 'database' ? 'Database created successfully' : 'VM created successfully');
    } catch (error) {
      toast.error(error?.response?.data?.error?.message || 'Unable to create resource');
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
      toast.error(error?.response?.data?.error?.message || 'Unable to delete VM');
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
      toast.error(error?.response?.data?.error?.message || 'Unable to stop VM');
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
      </div>

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Resource ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  CPU / Memory
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {resources?.map((resource, index) => {
                const safeId = resource?.id || 'fallback-id';
                const cpuPercent = Math.round(Number(resource?.cpu || 0) * 100);
                const memoryPercent = Math.round(Number(resource?.memory || 0) * 100);

                return (
                  <tr
                    key={safeId}
                    className="hover:bg-gray-50 dark:hover:bg-gray-700/50"
                    onClick={() => setSelectedVM(resource || null)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <ServerIcon className="w-5 h-5 text-gray-400 mr-3" />
                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                          {resource?.name || 'Unnamed resource'}
                          {resource?.type === 'database' ? (
                            <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">({resource?.engine || 'Database'})</span>
                          ) : null}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {safeId}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`status-badge ${statusClass(resource?.status)}`}>
                        {resource?.status || 'unknown'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="w-36">
                        <div className="flex justify-between text-xs mb-1">
                          <span>CPU</span>
                          <span>{cpuPercent}%</span>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-2">
                          <div
                            className="bg-primary-600 h-2 rounded-full"
                            style={{ width: `${cpuPercent}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs">
                          <span>Memory</span>
                          <span>{memoryPercent}%</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <div className="flex items-center justify-end space-x-2">
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            handleStopVM(resource);
                          }}
                          className="text-warning-600 hover:text-warning-900"
                        >
                          <StopIcon className="w-5 h-5" />
                        </button>
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            handleDeleteVM(resource);
                          }}
                          className="text-danger-600 hover:text-danger-900"
                        >
                          <TrashIcon className="w-5 h-5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {resources?.length === 0 && !loading && (
                <tr>
                  <td colSpan="5" className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                    No resources created yet.
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td colSpan="5" className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                    Loading resources...
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
              ) : null}
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
