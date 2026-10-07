import React, { useState, useEffect, useCallback } from 'react';
import {
  Phone,
  Search,
  RefreshCw,
  Trash2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function App() {
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState({ total: 0, english: 0, hindi: 0, mixed: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState('');
  const [languageFilter, setLanguageFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/phone/stats`);
      if (res.ok) {
        setStats(await res.json());
      }
    } catch (e) {
      console.warn('Failed to load stats:', e);
    }
  }, []);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.append('search', search.trim());
      if (languageFilter) params.append('language', languageFilter);
      if (startDate) params.append('start_date', startDate);
      if (endDate) params.append('end_date', endDate);

      const qs = params.toString();
      const res = await fetch(`${API_BASE_URL}/api/phone${qs ? `?${qs}` : ''}`);
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

  const handleDelete = async (id, phone) => {
    if (!window.confirm(`Delete record for ${phone}?`)) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/phone/${id}`, { method: 'DELETE' });
      if (res.ok) {
        if (expandedId === id) setExpandedId(null);
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
    if (!dateStr) return '-';
    try {
      return new Date(dateStr).toLocaleString('en-IN', {
        dateStyle: 'medium',
        timeStyle: 'short',
      });
    } catch {
      return dateStr;
    }
  };

  const toggleExpand = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const hasFilters = search || languageFilter || startDate || endDate;

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="brand">
          <div className="brand-row">
            <Phone className="brand-mark" />
            <h1>Phone Collection Dashboard</h1>
          </div>
          <p>Numbers collected by the LiveKit voice agent</p>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={loadData}
          title="Refresh"
        >
          <RefreshCw className={`icon ${loading ? 'spin' : ''}`} />
          Refresh
        </button>
      </header>

      <section className="stats">
        <div className="stat">
          <div className="stat-label"><span>Total</span></div>
          <div className="stat-value">{stats.total}</div>
          <div className="stat-hint">Validated 10-digit numbers</div>
        </div>
        <div className="stat">
          <div className="stat-label"><span>English</span></div>
          <div className="stat-value">{stats.english}</div>
          <div className="stat-hint">language = en</div>
        </div>
        <div className="stat">
          <div className="stat-label"><span>Hindi</span></div>
          <div className="stat-value">{stats.hindi}</div>
          <div className="stat-hint">language = hi</div>
        </div>
        <div className="stat">
          <div className="stat-label"><span>Mixed</span></div>
          <div className="stat-value">{stats.mixed}</div>
          <div className="stat-hint">language = mixed</div>
        </div>
      </section>

      <div className="filters">
        <div className="search-wrap">
          <Search className="search-icon" />
          <input
            type="text"
            placeholder="Search by phone number..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="filter-row">
          <select
            className="filter-select"
            value={languageFilter}
            onChange={(e) => setLanguageFilter(e.target.value)}
          >
            <option value="">All languages</option>
            <option value="en">English</option>
            <option value="hi">Hindi</option>
            <option value="mixed">Mixed</option>
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
          {hasFilters && (
            <button type="button" className="btn btn-ghost" onClick={clearFilters}>
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="panel">
        {loading && records.length === 0 ? (
          <div className="state-box">
            <div className="spinner" />
            <p>Loading records...</p>
          </div>
        ) : error ? (
          <div className="state-box error">
            <AlertCircle className="icon-xl" />
            <p>{error}</p>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={loadData}
              style={{ marginTop: '0.75rem' }}
            >
              Retry
            </button>
          </div>
        ) : records.length === 0 ? (
          <div className="state-box">
            <Phone className="icon-xl" />
            <p>No phone numbers yet.</p>
            <span className="hint">
              Run the voice agent and confirm a number to see it here.
            </span>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Phone</th>
                  <th>Language</th>
                  <th>Collected at</th>
                  <th>Transcript</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {records.map((row) => {
                  const open = expandedId === row.id;
                  return (
                    <React.Fragment key={row.id}>
                      <tr>
                        <td>
                          <span className="phone">+91 {row.parsedNumber}</span>
                        </td>
                        <td>
                          <span className={`badge badge-${row.language}`}>
                            {row.language}
                          </span>
                        </td>
                        <td className="time">{formatCollectedAt(row.collectedAt)}</td>
                        <td>
                          <div
                            className="transcript-preview"
                            onClick={() => toggleExpand(row.id)}
                            title="Click to expand transcript"
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                toggleExpand(row.id);
                              }
                            }}
                          >
                            {open ? (
                              <ChevronDown className="icon" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                            ) : (
                              <ChevronRight className="icon" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                            )}
                            {row.rawTranscript}
                          </div>
                          {open && (
                            <div className="transcript-expanded">
                              {row.rawTranscript}
                            </div>
                          )}
                        </td>
                        <td className="actions">
                          <button
                            type="button"
                            className="btn btn-danger"
                            onClick={() => handleDelete(row.id, row.parsedNumber)}
                            title="Delete record"
                          >
                            <Trash2 className="icon" />
                            Delete
                          </button>
                        </td>
                      </tr>
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
