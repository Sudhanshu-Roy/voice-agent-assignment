import React, { useState, useEffect, useCallback } from 'react';
import { 
  Phone, 
  Search, 
  RefreshCw, 
  Trash2, 
  Calendar, 
  Globe, 
  CheckCircle2, 
  AlertCircle, 
  X,
  Languages
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function App() {
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState({ total: 0, english: 0, hindi: 0, mixed: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filters
  const [search, setSearch] = useState('');
  const [languageFilter, setLanguageFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Modal for expanding raw transcript
  const [activeTranscript, setActiveTranscript] = useState(null);

  // Fetch stats from backend
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/phone/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.warn('Failed to load stats:', e);
    }
  }, []);

  // Fetch records with active filters
  const fetchRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.append('search', search.trim());
      if (languageFilter) params.append('language', languageFilter);
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);

      const url = `${API_BASE_URL}/api/phone${params.toString() ? `?${params.toString()}` : ''}`;
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`);
      }
      const json = await res.json();
      if (json.success) {
        setRecords(json.data);
      } else {
        throw new Error(json.message || 'Failed to fetch records');
      }
    } catch (err) {
      setError(err.message || 'Unable to connect to backend server');
    } finally {
      setLoading(false);
    }
  }, [search, languageFilter, startDate, endDate]);

  const loadData = useCallback(() => {
    fetchRecords();
    fetchStats();
  }, [fetchRecords, fetchStats]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Delete record handler
  const handleDelete = async (id, phone) => {
    if (!window.confirm(`Are you sure you want to delete phone record ${phone}?`)) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/phone/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        loadData();
      } else {
        alert('Failed to delete record.');
      }
    } catch (e) {
      alert(`Error deleting record: ${e.message}`);
    }
  };

  const clearFilters = () => {
    setSearch('');
    setLanguageFilter('');
    setStartDate('');
    setEndDate('');
  };

  const formatCollectedAt = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const d = new Date(dateStr);
      return d.toLocaleString('en-IN', {
        dateStyle: 'medium',
        timeStyle: 'short',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="dashboard-container">
      {/* Header */}
      <header>
        <div className="header-title">
          <Phone className="w-6 h-6 text-indigo-400" />
          <h1>VAIU AI — Voice Agent Dashboard</h1>
          <span className="header-badge">LiveKit Agent v1.8</span>
        </div>
        <div className="header-actions">
          <button 
            id="refresh-btn"
            className="btn btn-secondary" 
            onClick={loadData}
            title="Refresh records"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-header">
            <span>Total Collected</span>
            <CheckCircle2 className="w-5 h-5 text-indigo-400" />
          </div>
          <div className="stat-value">{stats.total}</div>
          <div className="stat-subtext">Verified 10-digit Indian numbers</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span>English Recitations</span>
            <Globe className="w-5 h-5 text-blue-400" />
          </div>
          <div className="stat-value">{stats.english}</div>
          <div className="stat-subtext">Classified as 'en'</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span>Hindi Recitations</span>
            <Languages className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="stat-value">{stats.hindi}</div>
          <div className="stat-subtext">Classified as 'hi' (shunya, sifar, etc.)</div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span>Mixed / Hinglish</span>
            <Languages className="w-5 h-5 text-amber-400" />
          </div>
          <div className="stat-value">{stats.mixed}</div>
          <div className="stat-subtext">Classified as 'mixed'</div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="filter-bar">
        <div className="search-input-wrapper">
          <Search className="search-icon" />
          <input
            id="search-phone-input"
            type="text"
            placeholder="Search by phone number..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <select 
            id="language-filter-select"
            className="filter-select"
            value={languageFilter}
            onChange={(e) => setLanguageFilter(e.target.value)}
          >
            <option value="">All Languages</option>
            <option value="en">English (en)</option>
            <option value="hi">Hindi (hi)</option>
            <option value="mixed">Mixed (mixed)</option>
          </select>

          <input 
            type="date"
            className="date-input"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            title="Start date"
          />

          <input 
            type="date"
            className="date-input"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            title="End date"
          />

          {(search || languageFilter || startDate || endDate) && (
            <button className="btn btn-secondary" onClick={clearFilters}>
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Main Records Table */}
      <div className="table-card">
        {loading && records.length === 0 ? (
          <div className="state-container">
            <div className="loading-spinner"></div>
            <p>Loading phone records...</p>
          </div>
        ) : error ? (
          <div className="state-container">
            <AlertCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
            <p style={{ color: '#f87171' }}>{error}</p>
            <button className="btn btn-secondary mt-3" onClick={loadData} style={{ marginTop: '0.75rem' }}>
              Retry
            </button>
          </div>
        ) : records.length === 0 ? (
          <div className="state-container">
            <Phone className="w-8 h-8 text-gray-500 mx-auto mb-2" />
            <p>No phone numbers collected yet.</p>
            <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
              Speak to the LiveKit voice agent to collect your first number.
            </span>
          </div>
        ) : (
          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Phone Number</th>
                  <th>Language</th>
                  <th>Collected At</th>
                  <th>Speech Transcript (Click to Expand)</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {records.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <span className="phone-badge">+91 {row.parsedNumber}</span>
                    </td>
                    <td>
                      <span className={`badge badge-${row.language}`}>
                        {row.language}
                      </span>
                    </td>
                    <td style={{ color: '#94a3b8' }}>
                      {formatCollectedAt(row.collectedAt)}
                    </td>
                    <td>
                      <div 
                        className="transcript-cell"
                        onClick={() => setActiveTranscript({
                          phone: row.parsedNumber,
                          transcript: row.rawTranscript,
                          lang: row.language
                        })}
                        title="Click to view full transcript"
                      >
                        "{row.rawTranscript}"
                      </div>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button 
                        className="btn btn-danger"
                        style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
                        onClick={() => handleDelete(row.id, row.parsedNumber)}
                        title="Delete record"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Full Transcript Modal */}
      {activeTranscript && (
        <div className="modal-overlay" onClick={() => setActiveTranscript(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Spoken Transcript — {activeTranscript.phone}</h3>
              <button 
                className="close-btn" 
                onClick={() => setActiveTranscript(null)}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="modal-body">
              <p style={{ marginBottom: '0.5rem', fontSize: '0.8rem', color: '#94a3b8' }}>
                Language: <strong style={{ color: '#f8fafc' }}>{activeTranscript.lang.toUpperCase()}</strong>
              </p>
              <p>"{activeTranscript.transcript}"</p>
            </div>
            <div style={{ marginTop: '1rem', textAlign: 'right' }}>
              <button 
                className="btn btn-secondary" 
                onClick={() => setActiveTranscript(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
