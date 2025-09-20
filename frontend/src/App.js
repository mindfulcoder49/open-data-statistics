import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { Stage2Form, Stage3Form, Stage4Form, Stage4Options } from './components/AnalysisForms';
import Stage2Report from './reports/Stage2Report';
import Stage4Report from './reports/Stage4Report';

function MainPage() {
    const [currentStep, setCurrentStep] = useState(1);
    const [existingFiles, setExistingFiles] = useState({ test_data: [], uploads: [] });
    const [selectedFiles, setSelectedFiles] = useState([]); // { path, headers, config }
    const [previewData, setPreviewData] = useState(null);
    const [analysisType, setAnalysisType] = useState('stage4_h3_anomaly');
    const [jobStatus, setJobStatus] = useState(null);
    const [jobResult, setJobResult] = useState(null);
    const [jobHistory, setJobHistory] = useState({});
    const [stage4Params, setStage4Params] = useState({
        h3_resolution: 9,
        analysis_weeks_trend_string: '4, 8',
        analysis_weeks_anomaly: 4,
        p_value_anomaly: 0.05,
        p_value_trend: 0.05,
        plot_generation: "both",
        filter_col: null,
        filter_values: []
    });
    const [filterOptions, setFilterOptions] = useState([]);

    // --- Data Fetching and Initial Load ---
    const fetchExistingFiles = useCallback(async () => {
        try {
            const response = await fetch('/api/v1/data/files');
            const data = await response.json();
            setExistingFiles(data);
        } catch (error) {
            console.error("Could not fetch existing files:", error);
        }
    }, []);

    const loadJobHistory = useCallback(() => {
        const history = JSON.parse(localStorage.getItem('jobHistory') || '{}');
        setJobHistory(history);
    }, []);

    useEffect(() => {
        fetchExistingFiles();
        loadJobHistory();
    }, [fetchExistingFiles, loadJobHistory]);

    // --- UI Navigation ---
    const navigateToStep = (step) => {
        if (step > currentStep && selectedFiles.length === 0) {
            alert('Please select or upload at least one file.');
            return;
        }
        setCurrentStep(step);
    };

    const startNewAnalysis = () => {
        setSelectedFiles([]);
        setPreviewData(null);
        setJobStatus(null);
        setJobResult(null);
        setCurrentStep(1);
    };

    // --- File Handling ---
    const handleFileSelection = async (path, isMultiSelect) => {
        let newSelectedFiles;
        const isSelected = selectedFiles.some(f => f.path === path);

        if (isMultiSelect) {
            newSelectedFiles = isSelected
                ? selectedFiles.filter(f => f.path !== path)
                : [...selectedFiles, { path, headers: [], config: {} }];
        } else {
            newSelectedFiles = isSelected && selectedFiles.length === 1
                ? []
                : [{ path, headers: [], config: {} }];
        }
        
        // For single-file analyses, only allow one selection
        if (analysisType !== 'stage4_h3_anomaly' && newSelectedFiles.length > 1) {
            alert('This analysis type only supports a single file. Please select only one.');
            newSelectedFiles = [newSelectedFiles[newSelectedFiles.length - 1]]; // Keep only the last selected
        }

        setSelectedFiles(newSelectedFiles);

        if (newSelectedFiles.length > 0) {
            const filesToProcess = newSelectedFiles.filter(f => f.headers.length === 0);
            for (const file of filesToProcess) {
                await fetchFilePreview(file.path, true);
            }
        } else {
            setPreviewData(null);
        }
    };

    const fetchFilePreview = async (filePath, isInternal) => {
        try {
            const response = await fetch('/api/v1/data/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            if (!response.ok) throw new Error(`Preview failed with status ${response.status}`);
            const data = await response.json();

            setSelectedFiles(prev => prev.map(f => f.path === filePath ? { ...f, headers: data.headers } : f));

            if (!isInternal || !previewData) {
                setPreviewData(data);
            }
            return data.headers;
        } catch (error) {
            alert(`Error getting file preview: ${error.message}`);
            return [];
        }
    };

    const handleFileUpload = async (event) => {
        const files = event.target.files;
        if (!files.length) return;

        // For single-file analyses, only allow one upload
        if (analysisType !== 'stage4_h3_anomaly' && files.length > 1) {
            alert('This analysis type only supports a single file. Please upload only one.');
            // We'll proceed with just the first file
        }
        const filesToUpload = analysisType !== 'stage4_h3_anomaly' ? [files[0]] : Array.from(files);

        try {
            const newFiles = [];
            for (const file of filesToUpload) {
                const formData = new FormData();
                formData.append('file', file);
                const uploadResponse = await fetch('/api/v1/data/upload', { method: 'POST', body: formData });
                if (!uploadResponse.ok) throw new Error(`File upload failed for ${file.name}`);
                const uploadResult = await uploadResponse.json();
                const headers = await fetchFilePreview(uploadResult.file_path, true);
                newFiles.push({ path: uploadResult.file_path, headers, config: {} });
            }
            setSelectedFiles(newFiles);
            fetchExistingFiles();
        } catch (error) {
            alert(error.message);
        }
    };

    // --- Job Configuration and Submission ---
    const handleAnalysisTypeChange = (e) => {
        const newType = e.target.value;
        setAnalysisType(newType);
        // If switching to a single-file analysis, truncate selected files
        if (newType !== 'stage4_h3_anomaly' && selectedFiles.length > 1) {
            alert('This analysis type only supports a single file. Keeping only the first selected file.');
            setSelectedFiles([selectedFiles[0]]);
        }
        setFilterOptions([]); // Reset filter options on type change
    };

    const handleStage4ConfigChange = (index, key, value) => {
        const newSelectedFiles = [...selectedFiles];
        newSelectedFiles[index].config[key] = value;
        setSelectedFiles(newSelectedFiles);
    };

    const handleAdvancedParamChange = (key, value) => {
        setStage4Params(prev => ({ ...prev, [key]: value }));
    };

    const fetchUniqueValuesForFilter = async (columnName) => {
        if (!columnName || selectedFiles.length === 0) {
            setFilterOptions([]);
            handleAdvancedParamChange('filter_col', null);
            handleAdvancedParamChange('filter_values', []);
            return;
        }

        handleAdvancedParamChange('filter_col', columnName);
        const filePath = selectedFiles[0].path; // Use first file for unique values

        try {
            const response = await fetch('/api/v1/data/unique-values', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath, column_name: columnName })
            });
            if (!response.ok) throw new Error('Failed to fetch unique values.');
            const result = await response.json();
            setFilterOptions(result.unique_values || []);
        } catch (error) {
            alert(`Could not load filter values: ${error.message}`);
            setFilterOptions([]);
        }
    };

    const handleFilterChange = (e) => {
        const values = Array.from(e.target.selectedOptions, option => option.value);
        handleAdvancedParamChange('filter_values', values);
    };

    const handleGenericParamChange = (key, value) => {
        // For stage 2/3, params are not per-file. We store them in the first file's config for convenience.
        if (selectedFiles.length > 0) {
            const newSelectedFiles = [...selectedFiles];
            newSelectedFiles[0].config[key] = value;
            setSelectedFiles(newSelectedFiles);
        }
    };

    const getJobConfigFromState = () => {
        const jobId = `job-${new Date().toISOString().replace(/[^0-9]/g, "")}`;
        let data_sources = [];
        let parameters = {};

        if (analysisType === 'stage4_h3_anomaly') {
            data_sources = selectedFiles.map(file => ({
                data_url: `${window.location.origin}${file.path}`,
                ...file.config
            }));

            const trendWeeks = stage4Params.analysis_weeks_trend_string.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n) && n > 0);
            if (trendWeeks.length === 0) {
                alert('Please provide at least one valid number for Analysis Weeks (Trends).');
                return null;
            }
            
            const { analysis_weeks_trend_string, ...restOfParams } = stage4Params;

            parameters = {
                stage4_h3_anomaly: {
                    ...restOfParams,
                    analysis_weeks_trend: trendWeeks,
                }
            };
        } else {
            // For Stage 2 and 3, we use one data source and global params
            const firstFile = selectedFiles[0];
            data_sources = [{
                data_url: `${window.location.origin}${firstFile.path}`,
                // These are not used by the backend for stage 2/3 but schema requires them
                timestamp_col: firstFile.config.timestamp_col || '',
                lat_col: '', lon_col: '', secondary_group_col: ''
            }];
            parameters = { [analysisType]: { ...firstFile.config } };
        }

        return {
            job_id: jobId,
            data_sources: data_sources,
            config: {
                analysis_stages: [analysisType],
                parameters: parameters
            }
        };
    };

    const handleJobSubmit = async () => {
        const jobConfig = getJobConfigFromState();
        if (!jobConfig) {
            alert('Configuration is incomplete.');
            return;
        }

        navigateToStep(3);
        setJobStatus({ status: 'submitting' });

        try {
            const response = await fetch('/api/v1/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(jobConfig)
            });
            if (!response.ok) throw new Error(`Job submission failed: ${response.statusText}`);
            const result = await response.json();

            const newHistory = { ...jobHistory, [jobConfig.job_id]: { resultsUrl: result.results_url, date: new Date().toISOString(), analysisType: analysisType } };
            localStorage.setItem('jobHistory', JSON.stringify(newHistory));
            setJobHistory(newHistory);

            pollJobStatus(result.status_url);
        } catch (error) {
            setJobStatus({ status: 'failed', error_message: error.message });
        }
    };

    const pollJobStatus = (statusUrl) => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(statusUrl);
                const data = await response.json();
                setJobStatus(data);

                if (data.status === 'completed' || data.status === 'failed') {
                    clearInterval(interval);
                    if (data.status === 'completed') {
                        const resultsResponse = await fetch(statusUrl.replace('/status', '/results'));
                        const resultsData = await resultsResponse.json();
                        setJobResult(resultsData);
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
                setJobStatus({ status: 'failed', error_message: 'Polling failed.' });
                clearInterval(interval);
            }
        }, 3000);
    };

    // --- Render Logic ---
    const renderFileList = (files, title) => (
        <div className="file-list-container">
            <h4>{title}</h4>
            {files.length > 0 ? (
                <ul className="file-list">
                    {files.map(path => (
                        <li
                            key={path}
                            className={selectedFiles.some(f => f.path === path) ? 'selected' : ''}
                            onClick={(e) => handleFileSelection(path, e.ctrlKey || e.metaKey)}
                        >
                            {path.split('/').pop()}
                        </li>
                    ))}
                </ul>
            ) : <p>No files found.</p>}
        </div>
    );

    const renderStepContent = () => {
        switch (currentStep) {
            case 1:
                return (
                    <div id="step-1" className="card">
                        <h2>Step 1: Select Data Source(s)</h2>
                        <div className="form-group">
                            <label>Analysis Type</label>
                            <select value={analysisType} onChange={handleAnalysisTypeChange}>
                                <option value="stage4_h3_anomaly">H3 Spatial Anomaly Detection (Stage 4)</option>
                                <option value="stage3_univariate_anomaly">Univariate Anomaly Detection (Stage 3)</option>
                                <option value="stage2_yearly_count_comparison">Yearly Count Comparison (Stage 2)</option>
                            </select>
                        </div>
                        {renderFileList(existingFiles.test_data, 'Test Datasets')}
                        {renderFileList(existingFiles.uploads, 'Uploaded Files')}
                        <hr style={{ margin: '30px 0' }} />
                        <div className="form-group">
                            <h4>Upload New CSV Files</h4>
                            <input type="file" onChange={handleFileUpload} accept=".csv" multiple={analysisType === 'stage4_h3_anomaly'} />
                        </div>
                        <div className="btn-group">
                            <span></span>
                            <button onClick={() => navigateToStep(2)} className="btn" disabled={selectedFiles.length === 0}>Next</button>
                        </div>
                    </div>
                );
            case 2:
                return (
                    <div id="step-2" className="card">
                        <h2>Step 2: Configure Analysis</h2>
                        {analysisType === 'stage4_h3_anomaly' && selectedFiles.length > 0 && (
                            <>
                                {selectedFiles.map((file, index) => (
                                    <Stage4Form
                                        key={file.path}
                                        file={file}
                                        index={index}
                                        headers={file.headers}
                                        onConfigChange={handleStage4ConfigChange}
                                        onGroupingColumnChange={index === 0 ? fetchUniqueValuesForFilter : null}
                                    />
                                ))}
                                <Stage4Options
                                    params={stage4Params}
                                    onParamChange={handleAdvancedParamChange}
                                    filterOptions={filterOptions}
                                    onFilterChange={handleFilterChange}
                                />
                            </>
                        )}
                        {analysisType === 'stage3_univariate_anomaly' && selectedFiles.length > 0 && (
                            <Stage3Form headers={selectedFiles[0].headers} onParamChange={handleGenericParamChange} />
                        )}
                        {analysisType === 'stage2_yearly_count_comparison' && selectedFiles.length > 0 && (
                            <Stage2Form headers={selectedFiles[0].headers} onParamChange={handleGenericParamChange} />
                        )}
                        <div className="btn-group">
                            <button onClick={() => navigateToStep(1)} className="btn btn-secondary">Previous</button>
                            <button onClick={handleJobSubmit} className="btn">Submit Job</button>
                        </div>
                    </div>
                );
            case 3:
                return (
                    <div id="step-3" className="card">
                        <h2>Step 3: Job Progress</h2>
                        {jobStatus && (
                            <div id="status-container" style={{
                                backgroundColor: jobStatus.status === 'completed' ? '#e4f8e9' : jobStatus.status === 'failed' ? '#f8d7da' : '#f0faff',
                                borderColor: jobStatus.status === 'completed' ? '#c3e6cb' : jobStatus.status === 'failed' ? '#f5c6cb' : '#bce8f1'
                            }}>
                                <p><strong>Job ID:</strong> {jobStatus.job_id}</p>
                                <p><strong>Status:</strong> {jobStatus.status} { (jobStatus.status === 'queued' || jobStatus.status === 'processing' || jobStatus.status === 'submitting') && <div className="loader"></div>}</p>
                                {jobStatus.current_stage && <p><strong>Stage:</strong> {jobStatus.current_stage}</p>}
                                {jobStatus.stage_detail && <p><strong>Details:</strong> {jobStatus.stage_detail}</p>}
                                {jobStatus.progress != null && <p><strong>Progress:</strong> {jobStatus.progress}%</p>}
                                {jobStatus.error_message && <p style={{color: 'var(--danger)'}}><strong>Error:</strong> {jobStatus.error_message}</p>}
                            </div>
                        )}
                        {jobResult && (
                            <div id="results-container">
                                <h3>Results</h3>
                                <ul>
                                    {Object.entries(jobResult.results).map(([key, url]) => (
                                        <li key={key}><a href={url} target="_blank" rel="noopener noreferrer">View {key.replace(/_/g, ' ')}</a></li>
                                    ))}
                                </ul>
                            </div>
                        )}
                        <div className="btn-group">
                            <span></span>
                            <button onClick={startNewAnalysis} className="btn btn-secondary">Start New Analysis</button>
                        </div>
                    </div>
                );
            default:
                return null;
        }
    };

    return (
        <>
            <ul className="stepper">
                {[1, 2, 3].map(step => (
                    <li key={step} className={`step-item ${currentStep === step ? 'active' : ''}`}>
                        <div className="step-circle">{step}</div>
                    </li>
                ))}
            </ul>

            {renderStepContent()}

            {previewData && currentStep === 1 && (
                <div id="data-preview-container">
                    <h3>Data Preview ({selectedFiles.length} file(s) selected)</h3>
                    <div style={{ overflowX: 'auto' }}>
                        <table id="data-preview-table">
                            <thead>
                                <tr>{previewData.headers.map(h => <th key={h}>{h}</th>)}</tr>
                            </thead>
                            <tbody>
                                {previewData.rows.map((row, i) => (
                                    <tr key={i}>{previewData.headers.map(h => <td key={h}>{row[h] || ''}</td>)}</tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {Object.keys(jobHistory).length > 0 && (
                <div id="job-history-container" className="card">
                    <h3>Previous Jobs</h3>
                    <ul id="job-history-list">
                        {Object.entries(jobHistory).sort(([, a], [, b]) => new Date(b.date) - new Date(a.date)).map(([jobId, job]) => {
                             const reportUrlMap = {
                                'stage4_h3_anomaly': `/reports/view/stage4/${jobId}`,
                                'stage2_yearly_count_comparison': `/reports/view/stage2/${jobId}`
                             };
                             const reportUrl = reportUrlMap[job.analysisType];

                             return (
                                <li key={jobId}>
                                    <div>
                                        <Link to={reportUrl || job.resultsUrl} target="_blank" rel="noopener noreferrer">{jobId}</Link>
                                        <br /><small>{new Date(job.date).toLocaleString()}</small>
                                    </div>
                                    {reportUrl && <Link to={reportUrl} target="_blank" rel="noopener noreferrer" className="btn btn-secondary" style={{padding: '5px 10px', fontSize: '14px'}}>View Report</Link>}
                                </li>
                             );
                        })}
                    </ul>
                </div>
            )}
        </>
    );
}

function App() {
    return (
        <Router>
            <header>
                <h1><Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>Ladder Analytics</Link></h1>
                <p>Upload your data and configure an analysis to identify trends and anomalies.</p>
            </header>
            <Routes>
                <Route path="/" element={<MainPage />} />
                <Route path="/reports/view/stage2/:jobId" element={<Stage2Report />} />
                <Route path="/reports/view/stage4/:jobId" element={<Stage4Report />} />
            </Routes>
        </Router>
    );
}

export default App;
