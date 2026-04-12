import React, { useState, useEffect } from 'react';
import { useSelector } from 'react-redux';
import { MoonIcon, SunIcon, BellIcon, ShieldCheckIcon, UserCircleIcon } from '@heroicons/react/24/outline';
import axios from 'axios';
import toast from 'react-hot-toast';
const API_URL = 'http://localhost:5000/api';
const Settings = () => {
  const { user, token } = useSelector((state) => state.auth);
  const [settings, setSettings] = useState(null);
  const [activeTab, setActiveTab] = useState('profile');
  const [darkMode, setDarkMode] = useState(false);
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const response = await axios.get(`${API_URL}/settings/`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setSettings(response.data);
      } catch (error) {
        toast.error('Failed to load settings');
      }
    };

    loadSettings();
    // Check system preference for dark mode
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setDarkMode(true);
      document.documentElement.classList.add('dark');
    }
  }, [token]);
  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle('dark');
  };
  const tabs = [
    { id: 'profile', name: 'Profile', icon: UserCircleIcon },
    { id: 'notifications', name: 'Notifications', icon: BellIcon },
    { id: 'security', name: 'Security', icon: ShieldCheckIcon },
  ];
  if (!settings) return <div className="p-6">Loading...</div>;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar */}
        <div className="lg:w-64 space-y-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center px-4 py-3 rounded-lg text-left transition-colors ${
                activeTab === tab.id
                  ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400'
                  : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800'
              }`}
            >
              <tab.icon className="w-5 h-5 mr-3" />
              {tab.name}
            </button>
          ))}
          <div className="pt-4 mt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={toggleDarkMode}
              className="w-full flex items-center px-4 py-3 rounded-lg text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800"
            >
              {darkMode ? (
                <>
                  <SunIcon className="w-5 h-5 mr-3" />
                  Light Mode
                </>
              ) : (
                <>
                  <MoonIcon className="w-5 h-5 mr-3" />
                  Dark Mode
                </>
              )}
            </button>
          </div>
        </div>
        {/* Content */}
        <div className="flex-1">
          {activeTab === 'profile' && (
            <div className="card space-y-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Profile Settings</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    First Name
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    defaultValue={user?.first_name}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Last Name
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    defaultValue={user?.last_name}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    className="input-field"
                    defaultValue={user?.email}
                    disabled
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Timezone
                  </label>
                  <select className="input-field" defaultValue={settings.appearance?.timezone}>
                    <option value="UTC">UTC</option>
                    <option value="America/New_York">Eastern Time</option>
                    <option value="America/Los_Angeles">Pacific Time</option>
                    <option value="Europe/London">London</option>
                    <option value="Asia/Karachi">Karachi</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end">
                <button className="btn-primary">Save Changes</button>
              </div>
            </div>
          )}
          {activeTab === 'notifications' && (
            <div className="card space-y-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Notification Preferences</h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Email Notifications</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Receive updates via email</p>
                  </div>
                  <input
                    type="checkbox"
                    className="w-5 h-5 text-primary-600 rounded"
                    defaultChecked={settings.notifications?.email}
                  />
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Cost Alerts</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Notify when spending exceeds threshold</p>
                  </div>
                  <input
                    type="checkbox"
                    className="w-5 h-5 text-primary-600 rounded"
                    defaultChecked={settings.notifications?.preferences?.cost_alerts}
                  />
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Security Alerts</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Notify on security threats</p>
                  </div>
                  <input
                    type="checkbox"
                    className="w-5 h-5 text-primary-600 rounded"
                    defaultChecked={settings.notifications?.preferences?.security_alerts}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Cost Alert Threshold (%)
                  </label>
                  <input
                    type="range"
                    min="50"
                    max="100"
                    className="w-full"
                    defaultValue={settings.notifications?.preferences?.cost_threshold || 80}
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>50%</span>
                    <span>100%</span>
                  </div>
                </div>
              </div>
              <div className="flex justify-end">
                <button className="btn-primary">Save Preferences</button>
              </div>
            </div>
          )}
          {activeTab === 'security' && (
            <div className="card space-y-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Security Settings</h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Two-Factor Authentication</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Add extra security to your account</p>
                  </div>
                  <button className="btn-secondary text-sm">Enable</button>
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Login Notifications</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Get notified of new logins</p>
                  </div>
                  <input
                    type="checkbox"
                    className="w-5 h-5 text-primary-600 rounded"
                    defaultChecked={settings.security?.login_notifications}
                  />
                </div>
                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Session Timeout</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Automatically log out after inactivity</p>
                  </div>
                  <select className="input-field w-32" defaultValue={settings.security?.session_timeout}>
                    <option value="15">15 min</option>
                    <option value="30">30 min</option>
                    <option value="60">1 hour</option>
                    <option value="120">2 hours</option>
                  </select>
                </div>
                <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                  <h3 className="text-md font-medium text-gray-900 dark:text-white mb-3">Change Password</h3>
                  <div className="space-y-3">
                    <input
                      type="password"
                      placeholder="Current Password"
                      className="input-field"
                    />
                    <input
                      type="password"
                      placeholder="New Password"
                      className="input-field"
                    />
                    <input
                      type="password"
                      placeholder="Confirm New Password"
                      className="input-field"
                    />
                  </div>
                </div>
              </div>
              <div className="flex justify-end space-x-3">
                <button className="btn-secondary">Cancel</button>
                <button className="btn-primary">Update Security</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default Settings;
