import React, { useState, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { MapContainer, TileLayer, Polygon, Popup, Tooltip, useMap } from 'react-leaflet';
import * as h3 from 'h3-js';
import 'leaflet/dist/leaflet.css';
import './ReportStyles.css';

// Helper to recenter map
const ChangeView = ({ center, zoom }) => {
    const map = useMap();
    map.setView(center, zoom);
    return null;
};

const Stage4Report = () => {
    const { jobId } = useParams();
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchReport = async () => {
            try {
                const response = await fetch(`/api/v1/jobs/${jobId}/results/stage4_h3_anomaly.json`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const result = await response.json();
                setData(result);
            } catch (err) {
                setError(err.message);
            }
        };
        fetchReport();
    }, [jobId]);

    const {
        P_VALUE_ANOMALY, P_VALUE_TREND, h3Col, secondaryCol,
        allFindings, anomalyFindings, trendFindings, mapCenter,
        groupedAnomalyFindings, groupedTrendFindings, uniqueSecondaryGroups, uniqueTrendPeriods
    } = useMemo(() => {
        if (!data) return { allFindings: [], anomalyFindings: [], trendFindings: [], groupedAnomalyFindings: {}, groupedTrendFindings: {}, uniqueSecondaryGroups: [], uniqueTrendPeriods: [] };

        const params = data.parameters;
        const P_VALUE_ANOMALY = params.p_value_anomaly || 0.05;
        const P_VALUE_TREND = params.p_value_trend || 0.05;
        const h3Col = `h3_index_${params.h3_resolution}`;
        const secondaryCol = params.secondary_group_col;

        const allFindings = [];
        const anomalyFindings = [];
        const trendFindings = [];
        const groupedAnomalyFindings = {};
        const groupedTrendFindings = {};
        const uniqueSecondaryGroups = new Set();
        const uniqueTrendPeriods = new Set();


        data.results.forEach(row => {
            const secGroup = row.secondary_group;
            uniqueSecondaryGroups.add(secGroup);

            if (row.trend_analysis) {
                for (const [period, trend] of Object.entries(row.trend_analysis)) {
                    if (trend.p_value !== null && trend.p_value < P_VALUE_TREND) {
                        const finding = { type: 'Trend', details: row, trend_details: trend, period: period };
                        allFindings.push(finding);
                        trendFindings.push(finding);

                        if (!groupedTrendFindings[secGroup]) groupedTrendFindings[secGroup] = {};
                        if (!groupedTrendFindings[secGroup][period]) groupedTrendFindings[secGroup][period] = [];
                        groupedTrendFindings[secGroup][period].push(finding);
                        uniqueTrendPeriods.add(period);
                    }
                }
            }
            if (row.anomaly_analysis) {
                row.anomaly_analysis.forEach(week => {
                    if (week.anomaly_p_value !== null && week.anomaly_p_value < P_VALUE_ANOMALY) {
                        if (row.historical_weekly_avg < 1 && week.count === 1) return;
                        const finding = { type: 'Anomaly', details: row, week_details: week };
                        allFindings.push(finding);
                        anomalyFindings.push(finding);

                        if (!groupedAnomalyFindings[secGroup]) groupedAnomalyFindings[secGroup] = [];
                        groupedAnomalyFindings[secGroup].push(finding);
                    }
                });
            }
        });

        let mapCenter = [42.3601, -71.0589]; // Default to Boston
        if (allFindings.length > 0) {
            const allLats = allFindings.map(f => f.details.lat);
            const allLons = allFindings.map(f => f.details.lon);
            const avgLat = allLats.reduce((a, b) => a + b, 0) / allLats.length;
            const avgLon = allLons.reduce((a, b) => a + b, 0) / allLons.length;
            mapCenter = [avgLat, avgLon];
        }

        return { 
            P_VALUE_ANOMALY, P_VALUE_TREND, h3Col, secondaryCol, allFindings, anomalyFindings, trendFindings, mapCenter,
            groupedAnomalyFindings, groupedTrendFindings, 
            uniqueSecondaryGroups: Array.from(uniqueSecondaryGroups).sort(), 
            uniqueTrendPeriods: Array.from(uniqueTrendPeriods).sort()
        };
    }, [data]);

    const getAnomalyColor = (count) => {
        const scale = ['#FFFFE5', '#FFF7BC', '#FEE391', '#FEC44F', '#FE9929', '#EC7014', '#CC4C02', '#993404', '#662506', '#E31A1C'];
        if (count >= 1 && count <= 10) return scale[count - 1];
        if (count > 10) return '#800080';
        return '#cccccc';
    };

    const getTrendColor = (slope) => (slope > 0 ? '#d73027' : '#4575b4');

    const renderMap = (findings, type) => {
        if (findings.length === 0) return <p>No significant {type}s found.</p>;

        const h3Summary = {};
        findings.forEach(finding => {
            const h3Index = finding.details[h3Col];
            if (!h3Summary[h3Index]) {
                h3Summary[h3Index] = { items: [], lat: finding.details.lat, lon: finding.details.lon, total_slope: 0 };
            }
            h3Summary[h3Index].items.push(finding);
            if (type === 'trend') {
                h3Summary[h3Index].total_slope += finding.trend_details.slope;
            }
        });

        return (
            <MapContainer center={mapCenter} zoom={12} style={{ height: '500px', width: '100%' }}>
                <ChangeView center={mapCenter} zoom={12} />
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                />
                {Object.entries(h3Summary).map(([h3Index, summary]) => {
                    const boundary = h3.cellToBoundary(h3Index, true).map(p => [p[1], p[0]]);
                    const count = summary.items.length;
                    const color = type === 'anomaly' ? getAnomalyColor(count) : getTrendColor(summary.total_slope / count);

                    return (
                        <Polygon key={h3Index} positions={boundary} pathOptions={{ color: 'black', weight: 1, fillColor: color, fillOpacity: 0.7 }}>
                            <Tooltip>{h3Index}: {count} {type}(s)</Tooltip>
                            <Popup><b>Hexagon:</b> {h3Index}<br/><b>{type === 'anomaly' ? 'Anomalies' : 'Trends'}:</b> {count}</Popup>
                        </Polygon>
                    );
                })}
            </MapContainer>
        );
    };
    
    const sanitizeForFilename = (name) => String(name).replace(/[\\/*?:"<>|]/g, "");

    if (error) return <div className="report-container card error">Error: {error}</div>;
    if (!data) return <div className="report-container card">Loading report data...</div>;

    return (
        <main className="report-container">
            <h2>Scholarly Report on H3-Based Spatial Time Series Analysis</h2>
            <p className="info">Job ID: {jobId}</p>

            <h2>Spatial Overview of Anomalies</h2>
            <p>The maps display H3 cells with significant anomalies, separated by the secondary grouping column '{secondaryCol}'. Color corresponds to the number of anomaly types.</p>
            {uniqueSecondaryGroups.map(group => (
                <div key={group} className="map-group">
                    <h3>Anomalies for: {group}</h3>
                    <div className="map-container">{renderMap(groupedAnomalyFindings[group] || [], 'anomaly')}</div>
                </div>
            ))}

            <h2>Spatial Overview of Trends</h2>
            <p>The maps display H3 cells with significant trends, separated by grouping and trend period. Red for upward, blue for downward.</p>
            {uniqueSecondaryGroups.map(group => (
                <div key={group} className="map-group">
                    {uniqueTrendPeriods.map(period => {
                        const findings = (groupedTrendFindings[group] && groupedTrendFindings[group][period]) || [];
                        if (findings.length === 0) return null;
                        return (
                            <div key={`${group}-${period}`}>
                                <h3>Trends for: {group} ({period.replace(/_/g, ' ')})</h3>
                                <div className="map-container">{renderMap(findings, 'trend')}</div>
                            </div>
                        );
                    })}
                </div>
            ))}

            <h2>Summary of All Significant Findings</h2>
            <div className="card" style={{overflowX: 'auto'}}>
                <table>
                    <thead><tr><th>H3 Cell</th><th>{secondaryCol || 'Secondary Group'}</th><th>Finding Type</th><th>Date/Period</th><th>Details</th><th>P-Value</th><th>Z-Score / Slope</th></tr></thead>
                    <tbody>
                        {allFindings.map((finding, i) => {
                            const details = finding.details;
                            return (
                                <tr key={i}>
                                    <td><a href={`#${details[h3Col]}`}>{details[h3Col]}</a></td>
                                    <td>{details.secondary_group}</td>
                                    {finding.type === 'Trend' ? (
                                        <>
                                            <td>Trend</td>
                                            <td>{finding.period.replace('_', ' ')}</td>
                                            <td>{finding.trend_details.description}</td>
                                            <td>{finding.trend_details.p_value.toPrecision(4)}</td>
                                            <td>{finding.trend_details.slope.toFixed(2)}</td>
                                        </>
                                    ) : (
                                        <>
                                            <td>Anomaly</td>
                                            <td>{finding.week_details.week}</td>
                                            <td>Count: {finding.week_details.count} (vs avg {details.historical_weekly_avg.toFixed(2)})</td>
                                            <td>{finding.week_details.anomaly_p_value.toPrecision(4)}</td>
                                            <td>{finding.week_details.z_score.toFixed(2)}</td>
                                        </>
                                    )}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            <h2>Detailed Analysis by H3 Cell</h2>
            {Object.entries(allFindings.reduce((acc, f) => {
                const h3Index = f.details[h3Col];
                if (!acc[h3Index]) acc[h3Index] = [];
                acc[h3Index].push(f);
                return acc;
            }, {})).map(([h3Index, findingsInH3]) => (
                <div key={h3Index} id={h3Index} className="finding-group">
                    <h4>Hexagon: {h3Index}</h4>
                    {Object.entries(findingsInH3.reduce((acc, f) => {
                        const secGroup = f.details.secondary_group;
                        if (!acc[secGroup]) acc[secGroup] = [];
                        acc[secGroup].push(f);
                        return acc;
                    }, {})).map(([secGroup, findingsInGroup]) => (
                        <div key={secGroup} className="finding-card">
                            <h5>Findings for '{secGroup}'</h5>
                            <ul>
                                {findingsInGroup.map((f, i) => <li key={i}><strong>{f.type}</strong>: {f.type === 'Trend' ? `${f.trend_details.description} (p=${f.trend_details.p_value.toPrecision(4)})` : `Count ${f.week_details.count} on ${f.week_details.week} (p=${f.week_details.anomaly_p_value.toPrecision(4)})`}</li>)}
                            </ul>
                            <img 
                                src={`/api/v1/jobs/${jobId}/results/plot_${h3Index}_${sanitizeForFilename(secGroup)}.png`} 
                                alt={`Time series plot for ${secGroup} in ${h3Index}`} 
                                style={{width:'100%', maxWidth:'600px'}} 
                                onError={(e) => { e.target.style.display = 'none'; }}
                            />
                        </div>
                    ))}
                </div>
            ))}
        </main>
    );
};

export default Stage4Report;
