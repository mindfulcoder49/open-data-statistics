import React from 'react';

const generateOptions = (headers) => {
    if (!headers) return null;
    return headers.map(h => <option key={h} value={h}>{h}</option>);
};

export const Stage4Form = ({ file, index, headers, onConfigChange, onGroupingColumnChange }) => (
    <div className="file-config-group" data-path={file.path}>
        <h4>{file.path.split('/').pop()}</h4>
        <div className="form-group">
            <label>Timestamp Column</label>
            <select onChange={e => onConfigChange(index, 'timestamp_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
        <div className="form-group">
            <label>Latitude Column</label>
            <select onChange={e => onConfigChange(index, 'lat_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
        <div className="form-group">
            <label>Longitude Column</label>
            <select onChange={e => onConfigChange(index, 'lon_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
        <div className="form-group">
            <label>Grouping Column</label>
            <select onChange={e => {
                onConfigChange(index, 'secondary_group_col', e.target.value);
                if (onGroupingColumnChange) onGroupingColumnChange(e.target.value);
            }} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
    </div>
);

export const Stage4Options = ({ params, onParamChange, filterOptions, onFilterChange }) => (
    <>
        <h3>Advanced Options (Global)</h3>
        <div className="form-group">
            <label>H3 Resolution (5-10 recommended)</label>
            <input type="number" value={params.h3_resolution} onChange={e => onParamChange('h3_resolution', parseInt(e.target.value, 10))} min="0" max="15" required />
        </div>
        <div className="form-group">
            <label>Analysis Weeks (Trends)</label>
            <input type="text" value={params.analysis_weeks_trend_string} onChange={e => onParamChange('analysis_weeks_trend_string', e.target.value)} required />
            <small>Comma-separated list of recent week counts for trend detection (e.g., 4, 8, 12).</small>
        </div>
        <div className="form-group">
            <label>Analysis Weeks (Anomalies)</label>
            <input type="number" value={params.analysis_weeks_anomaly} onChange={e => onParamChange('analysis_weeks_anomaly', parseInt(e.target.value, 10))} min="1" required />
            <small>Number of recent weeks to use for anomaly detection.</small>
        </div>
        <div className="form-group">
            <label>P-Value for Anomalies</label>
            <input type="number" value={params.p_value_anomaly} onChange={e => onParamChange('p_value_anomaly', parseFloat(e.target.value))} min="0.001" max="1" step="0.001" required />
            <small>Significance level for detecting an anomalous weekly count.</small>
        </div>
        <div className="form-group">
            <label>P-Value for Trends</label>
            <input type="number" value={params.p_value_trend} onChange={e => onParamChange('p_value_trend', parseFloat(e.target.value))} min="0.001" max="1" step="0.001" required />
            <small>Significance level for detecting an upward or downward trend.</small>
        </div>
        <div className="form-group">
            <label>Generate Plots for Significant Findings</label>
            <select value={params.plot_generation} onChange={e => onParamChange('plot_generation', e.target.value)}>
                <option value="both">For Both Trends and Anomalies</option>
                <option value="trends">For Trends Only</option>
                <option value="anomalies">For Anomalies Only</option>
                <option value="none">None</option>
            </select>
            <small>Disabling plot generation can significantly speed up the analysis.</small>
        </div>
        {filterOptions.length > 0 && (
            <div className="form-group filter-group">
                <label>Filter by Grouping Column Values</label>
                <p><small>Select specific values from the grouping column to include in the analysis. Leave empty to include all.</small></p>
                <select multiple onChange={onFilterChange} className="filter-select">
                    {filterOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                </select>
            </div>
        )}
    </>
);

export const Stage3Form = ({ headers, onParamChange }) => (
    <>
        <h3>Column Mapping</h3>
        <div className="form-group">
            <label>Timestamp Column</label>
            <select onChange={e => onParamChange('timestamp_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
        <div className="form-group">
            <label>Primary Grouping Column</label>
            <select onChange={e => onParamChange('primary_group_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
        <div className="form-group">
            <label>Secondary Grouping Column</label>
            <select onChange={e => onParamChange('secondary_group_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
    </>
);

export const Stage2Form = ({ headers, onParamChange }) => (
    <>
        <h3>Column Mapping</h3>
        <div className="form-group">
            <label>Timestamp Column</label>
            <select onChange={e => onParamChange('timestamp_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
        <div className="form-group">
            <label>Grouping Column</label>
            <select onChange={e => onParamChange('group_by_col', e.target.value)} required>
                <option value="" disabled selected>Select a column</option>
                {generateOptions(headers)}
            </select>
        </div>
    </>
);
