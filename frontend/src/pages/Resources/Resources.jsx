import React, { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  fetchVMs,
  fetchDatabases,
  createVM,
  createDatabase,
  vmAction,
  dbAction,
} from '../../store/slices/resourceSlice';
import {
  PlusIcon,
  PlayIcon,
  StopIcon,
  TrashIcon,
  CircleStackIcon,
  ServerIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
const Resources = () => {
  const dispatch = useDispatch();
  const { currentOrganization } = useSelector((state) => state.organization);
  const { vms, databases } = useSelector((state) => state.resources);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showCreateDatabaseModal, setShowCreateDatabaseModal] = useState(false);
  const [newVM, setNewVM] = useState({
    name: '',
    instance_type: 't2.micro',
    organization_id: currentOrganization?.id,
  });
  const [newDatabase, setNewDatabase] = useState({
    name: '',
    engine: 'postgres',
    instance_class: 'db.t2.small',
    allocated_storage_gb: 20,
    publicly_accessible: false,
    storage_encrypted: true,
    organization_id: currentOrganization?.id,
  });
  useEffect(() => {
    if (currentOrganization) {
      dispatch(fetchVMs(currentOrganization.id));
      dispatch(fetchDatabases(currentOrganization.id));
      const refresh = setInterval(() => {
        dispatch(fetchVMs(currentOrganization.id));
        dispatch(fetchDatabases(currentOrganization.id));
      }, 10000);
      return () => clearInterval(refresh);
    }
  }, [dispatch, currentOrganization]);
  const handleCreateVM = async (e) => {
    e.preventDefault();
    const result = await dispatch(createVM({
      ...newVM,
      organization_id: currentOrganization.id,
    }));
    if (result.meta.requestStatus === 'fulfilled') {
      toast.success('VM created successfully');
      setShowCreateModal(false);
      setNewVM({ name: '', instance_type: 't2.micro', organization_id: currentOrganization?.id });
    }
  };
  const handleCreateDatabase = async (e) => {
    e.preventDefault();
    const result = await dispatch(createDatabase({
      ...newDatabase,
      organization_id: currentOrganization.id,
      allocated_storage_gb: Number(newDatabase.allocated_storage_gb),
    }));
    if (result.meta.requestStatus === 'fulfilled') {
      toast.success('Database created successfully');
      setShowCreateDatabaseModal(false);
      setNewDatabase({
        name: '',
        engine: 'postgres',
        instance_class: 'db.t2.small',
        allocated_storage_gb: 20,
        publicly_accessible: false,
        storage_encrypted: true,
        organization_id: currentOrganization?.id,
      });
      dispatch(fetchDatabases(currentOrganization.id));
    }
  };
  const handleAction = async (instanceId, action) => {
    const result = await dispatch(vmAction({ instanceId, action }));
    if (result.meta.requestStatus === 'fulfilled') {
      toast.success(`VM ${action}d successfully`);
      dispatch(fetchVMs(currentOrganization.id));
      dispatch(fetchDatabases(currentOrganization.id));
    }
  };
  const handleDatabaseAction = async (instanceId, action) => {
    const result = await dispatch(dbAction({ instanceId, action }));
    if (result.meta.requestStatus === 'fulfilled') {
      toast.success(`Database ${action}d successfully`);
      dispatch(fetchVMs(currentOrganization.id));
      dispatch(fetchDatabases(currentOrganization.id));
    }
  };
  const instanceTypes = [
    { value: 't2.micro', label: 't2.micro (1 vCPU, 1 GB) - $0.0116/hr' },
    { value: 't2.small', label: 't2.small (1 vCPU, 2 GB) - $0.023/hr' },
    { value: 't2.medium', label: 't2.medium (2 vCPU, 4 GB) - $0.0464/hr' },
    { value: 't2.large', label: 't2.large (2 vCPU, 8 GB) - $0.0928/hr' },
  ];
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Resources</h1>
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setShowCreateDatabaseModal(true)}
            className="btn-secondary flex items-center space-x-2"
          >
            <CircleStackIcon className="w-5 h-5" />
            <span>Create DB</span>
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary flex items-center space-x-2"
          >
            <PlusIcon className="w-5 h-5" />
            <span>Create VM</span>
          </button>
        </div>
      </div>
      {/* Resources Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Instance ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  CPU / Memory / Disk / Network
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Cost
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {vms.map((vm) => (
                <tr key={vm.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <ServerIcon className="w-5 h-5 text-gray-400 mr-3" />
                      <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                          {vm.name}
                        </div>
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {vm.private_ip}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {vm.instance_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {vm.instance_type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`status-badge ${
                      vm.status === 'running' ? 'status-running' :
                      vm.status === 'stopped' ? 'status-stopped' :
                      'status-warning'
                    }`}>
                      {vm.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="w-32">
                      <div className="flex justify-between text-xs mb-1">
                        <span>CPU</span>
                        <span>{vm.cpu_utilization}%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                        <div
                          className="bg-primary-600 h-2 rounded-full"
                          style={{ width: `${vm.cpu_utilization}%` }}
                        ></div>
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-2 space-y-1">
                        <p>Memory: {vm.memory_utilization}%</p>
                        <p>Disk: {vm.disk_read_iops} / {vm.disk_write_iops} IOPS</p>
                        <p>Net: {vm.network_in_mbps} / {vm.network_out_mbps} Mbps</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                    ${vm.current_cost.toFixed(4)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex items-center justify-end space-x-2">
                      {vm.status === 'stopped' && (
                        <button
                          onClick={() => handleAction(vm.instance_id, 'start')}
                          className="text-success-600 hover:text-success-900"
                        >
                          <PlayIcon className="w-5 h-5" />
                        </button>
                      )}
                      {vm.status === 'running' && (
                        <button
                          onClick={() => handleAction(vm.instance_id, 'stop')}
                          className="text-warning-600 hover:text-warning-900"
                        >
                          <StopIcon className="w-5 h-5" />
                        </button>
                      )}
                      <button
                        onClick={() => handleAction(vm.instance_id, 'terminate')}
                        className="text-danger-600 hover:text-danger-900"
                      >
                        <TrashIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {/* Database Resources */}
      <div className="card overflow-hidden">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Databases</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Instance ID</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Engine</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">CPU / Memory</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Disk / Network</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Cost</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {databases.map((database) => (
                <tr key={database.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900 dark:text-white">{database.name}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">{database.endpoint}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {database.instance_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {database.engine} / {database.instance_class}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`status-badge ${
                      database.status === 'running' ? 'status-running' :
                      database.status === 'stopped' ? 'status-stopped' :
                      'status-warning'
                    }`}>
                      {database.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    CPU {database.cpu_utilization}% / Memory {database.memory_utilization}%
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    Read {database.disk_read_iops} IOPS / Write {database.disk_write_iops} IOPS
                    <div className="text-xs text-gray-400">
                      Net {database.network_in_mbps} / {database.network_out_mbps} Mbps
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                    ${database.current_cost.toFixed(4)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex items-center justify-end space-x-2">
                      {database.status === 'stopped' && (
                        <button
                          onClick={() => handleDatabaseAction(database.instance_id, 'start')}
                          className="text-success-600 hover:text-success-900"
                        >
                          <PlayIcon className="w-5 h-5" />
                        </button>
                      )}
                      {database.status === 'running' && (
                        <button
                          onClick={() => handleDatabaseAction(database.instance_id, 'stop')}
                          className="text-warning-600 hover:text-warning-900"
                        >
                          <StopIcon className="w-5 h-5" />
                        </button>
                      )}
                      <button
                        onClick={() => handleDatabaseAction(database.instance_id, 'terminate')}
                        className="text-danger-600 hover:text-danger-900"
                      >
                        <TrashIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {databases.length === 0 && (
                <tr>
                  <td colSpan="8" className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                    No databases have been created yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {/* Create VM Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-md mx-4">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              Create Virtual Machine
            </h2>
            <form onSubmit={handleCreateVM} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  VM Name
                </label>
                <input
                  type="text"
                  required
                  className="input-field"
                  value={newVM.name}
                  onChange={(e) => setNewVM({ ...newVM, name: e.target.value })}
                  placeholder="e.g., web-server-01"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Instance Type
                </label>
                <select
                  className="input-field"
                  value={newVM.instance_type}
                  onChange={(e) => setNewVM({ ...newVM, instance_type: e.target.value })}
                >
                  {instanceTypes.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create VM
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Create Database Modal */}
      {showCreateDatabaseModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-md mx-4">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              Create Database
            </h2>
            <form onSubmit={handleCreateDatabase} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Database Name
                </label>
                <input
                  type="text"
                  required
                  className="input-field"
                  value={newDatabase.name}
                  onChange={(e) => setNewDatabase({ ...newDatabase, name: e.target.value })}
                  placeholder="e.g., analytics-db"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Engine
                </label>
                <select
                  className="input-field"
                  value={newDatabase.engine}
                  onChange={(e) => setNewDatabase({ ...newDatabase, engine: e.target.value })}
                >
                  <option value="postgres">PostgreSQL</option>
                  <option value="mysql">MySQL</option>
                  <option value="mariadb">MariaDB</option>
                  <option value="mongodb">MongoDB</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Instance Class
                </label>
                <select
                  className="input-field"
                  value={newDatabase.instance_class}
                  onChange={(e) => setNewDatabase({ ...newDatabase, instance_class: e.target.value })}
                >
                  <option value="db.t2.micro">db.t2.micro</option>
                  <option value="db.t2.small">db.t2.small</option>
                  <option value="db.m5.large">db.m5.large</option>
                  <option value="db.r5.large">db.r5.large</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Allocated Storage (GB)
                </label>
                <input
                  type="number"
                  min="20"
                  required
                  className="input-field"
                  value={newDatabase.allocated_storage_gb}
                  onChange={(e) => setNewDatabase({ ...newDatabase, allocated_storage_gb: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="flex items-center space-x-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={newDatabase.publicly_accessible}
                    onChange={(e) => setNewDatabase({ ...newDatabase, publicly_accessible: e.target.checked })}
                  />
                  <span>Public access</span>
                </label>
                <label className="flex items-center space-x-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={newDatabase.storage_encrypted}
                    onChange={(e) => setNewDatabase({ ...newDatabase, storage_encrypted: e.target.checked })}
                  />
                  <span>Encrypted</span>
                </label>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateDatabaseModal(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create Database
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
