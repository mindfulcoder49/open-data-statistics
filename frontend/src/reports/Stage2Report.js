import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import './ReportStyles.css';

const Stage2Report = () => {
    const { jobId } = useParams();
    const [reportData, setReportData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchReport = async () => {
            try {
                const response = await fetch(`/api/v1/jobs/${jobId}/results/stage2_yearly_count_comparison.json`);
                if (!response.ok) {
                    throw new Error(`Failed to load report data. Status: ${response.status}`);
                }
                const data = await response.json();
                setReportData(data);
            } catch (err) {
                setError(err.message);
            }
        };
        fetchReport();
    }, [jobId]);

    const formatCell = (data) => {
        if (!data) return '<td>-</td>';
        const count = data.count.toLocaleString();
        let changeHtml = '<span class="no-change">--</span>';
        if (data.change_pct !== null) {
            const change = data.change_pct;
            const sign = change > 0 ? '+' : '';
            const colorClass = change > 0 ? 'change-pos' : (change < 0 ? 'change-neg' : 'no-change');
            changeHtml = `<span class="${colorClass}">${sign}${change}% YoY</span>`;
        }
        return `<td class="change-cell">${count}${changeHtml}</td>`;
    };

    const renderTable = (results, years, dataType, currentYear) => {
        const headers = years.filter(year => !(dataType === 'full_year' && year === currentYear));
        return (
            <div style={{ overflowX: 'auto' }}>
                <table>
                    <thead>
                        <tr>
                            <th>Group</th>
                            {headers.map(year => <th key={year}>{year}</th>)}
                        </tr>
                    </thead>
                    <tbody>
                        {results.map(item => (
                            <tr key={item.group}>
                                <td className="group-name">{item.group}</td>
                                {headers.map(year => {
                                    const yearData = item[dataType][year];
                                    return <td key={year} className="change-cell" dangerouslySetInnerHTML={{ __html: formatCell(yearData).replace(/<td[^>]*>|<\/td>/g, '') }} />;
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    if (error) {
        return <div className="report-container card error">Error: {error}</div>;
    }

    if (!reportData) {
        return <div className="report-container card">Loading report data...</div>;
    }

    const { parameters, results, all_years } = reportData;
    const toDateCutoff = new Date(parameters.analysis_to_date_cutoff);

    return (
        <main className="report-container">
            <h2>Stage 2: Yearly Count Comparison</h2>
            <p className="info">Job ID: {jobId}</p>
            
            <div className="card">
                <h3>Analysis Parameters</h3>
                <p className="info">
                    Grouping by: <strong>{parameters.group_by_col}</strong>. 
                    Timestamp column: <strong>{parameters.timestamp_col}</strong>.
                </p>
            </div>

            <div className="card">
                <h3 id="to-date-title">Year-over-Year Comparison (To {toDateCutoff.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })})</h3>
                <p id="to-date-info" className="info">
                    Comparing data up to <strong>{toDateCutoff.toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}</strong> for each year. 
                    Current year is <strong>{parameters.analysis_current_year}</strong>.
                </p>
                {renderTable(results, all_years, 'to_date', null)}
            </div>

            <div className="card">
                <h3>Year-over-Year Comparison (Full Years)</h3>
                <p className="info">Comparing complete calendar years.</p>
                {renderTable(results, all_years, 'full_year', parameters.analysis_current_year)}
            </div>
        </main>
    );
};

export default Stage2Report;
