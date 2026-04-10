/**
 * cognitive_drift_monitor/static/js/dashboard.js
 * Phase 1 - AJAX auto-refresh framework for dashboard
 * Auto-refreshes dashboard data every 5 seconds
 */

const DashboardAutoRefresh = {
    refreshInterval: 5000, // 5 seconds
    intervalId: null,
    isEnabled: true,
    
    init: function() {
        this.startAutoRefresh();
        this.setupManualRefresh();
        this.updateTimestamp();
    },
    
    startAutoRefresh: function() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
        }
        
        this.intervalId = setInterval(() => {
            if (this.isEnabled && !document.hidden) {
                this.refreshDashboardData();
            }
        }, this.refreshInterval);
        
        console.log('Dashboard auto-refresh started (every ' + (this.refreshInterval / 1000) + ' seconds)');
    },
    
    stopAutoRefresh: function() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log('Dashboard auto-refresh stopped');
        }
    },
    
    refreshDashboardData: function() {
        Promise.all([
            this.fetchSummaryData(),
            this.fetchChartData()
        ]).then(results => {
            this.updateCards(results[0]);
            this.updateCharts(results[1]);
            this.updateTimestamp();
        }).catch(error => {
            console.error('Error refreshing dashboard:', error);
        });
    },
    
    fetchSummaryData: function() {
        return fetch('/api/dashboard-summary/', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        });
    },
    
    fetchChartData: function() {
        return fetch('/api/chart-data/?days=7', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        });
    },
    
    updateCards: function(data) {
        if (!data || !data.latest_scores) return;
        
        // Update reaction score
        const reactionScore = data.latest_scores.reaction_score;
        if (reactionScore !== null) {
            this.updateScoreDisplay('reaction-score', reactionScore);
        }
        
        // Update eye score
        const eyeScore = data.latest_scores.eye_score;
        if (eyeScore !== null) {
            this.updateScoreDisplay('eye-score', eyeScore);
        }
        
        // Update HRV score
        const hrvScore = data.latest_scores.hrv_score;
        if (hrvScore !== null) {
            this.updateScoreDisplay('hrv-score', hrvScore);
        }
        
        // Update final score
        const finalScore = data.latest_scores.final_score;
        if (finalScore !== null) {
            this.updateScoreDisplay('final-score', finalScore);
        }
        
        // Update warning count
        const warningCount = data.unacknowledged_warnings;
        this.updateWarningBadge(warningCount);
    },
    
    updateScoreDisplay: function(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            const formattedValue = value !== null ? value.toFixed(1) : '--';
            element.textContent = formattedValue;
            
            // Update color class
            element.classList.remove('score-good', 'score-warning', 'score-danger');
            if (value < 30) {
                element.classList.add('score-good');
            } else if (value < 60) {
                element.classList.add('score-warning');
            } else {
                element.classList.add('score-danger');
            }
        }
    },
    
    updateWarningBadge: function(count) {
        const badge = document.querySelector('.warning-badge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count + ' Warning' + (count !== 1 ? 's' : '');
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    },
    
    updateCharts: function(data) {
        if (!window.driftChart) return;
        
        // Update chart labels and data
        if (data.labels && data.labels.length > 0) {
            window.driftChart.data.labels = data.labels;
            window.driftChart.data.datasets[0].data = data.final_scores;
            window.driftChart.data.datasets[1].data = data.reaction_scores;
            window.driftChart.data.datasets[2].data = data.eye_scores;
            window.driftChart.data.datasets[3].data = data.hrv_scores;
            window.driftChart.update('none'); // No animation for smoother updates
        }
    },
    
    updateTimestamp: function() {
        const timestamp = document.getElementById('last-updated');
        if (timestamp) {
            const now = new Date();
            timestamp.textContent = 'Last updated: ' + now.toLocaleTimeString();
        }
    },
    
    setupManualRefresh: function() {
        const refreshBtn = document.getElementById('manual-refresh');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                refreshBtn.disabled = true;
                refreshBtn.innerHTML = '<span class="loading"></span> Refreshing...';
                
                this.refreshDashboardData();
                
                setTimeout(() => {
                    refreshBtn.disabled = false;
                    refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
                }, 1000);
            });
        }
    },
    
    // API helper methods for future sensor integration
    saveReactionData: function(data) {
        return fetch('/api/save-reaction/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json());
    },
    
    saveEyeData: function(data) {
        return fetch('/api/save-eye/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json());
    },
    
    saveHRVData: function(data) {
        return fetch('/api/save-hrv/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json());
    },
    
    getCSRFToken: function() {
        const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfInput) {
            return csrfInput.value;
        }
        return '';
    },
    
    // Fetch helpers for individual data types
    fetchDriftRecords: function(limit = 20) {
        return fetch(`/api/drift-records/?limit=${limit}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => response.json());
    },
    
    fetchWarnings: function(unacknowledgedOnly = false) {
        const url = unacknowledgedOnly 
            ? '/api/warnings/?unacknowledged=true' 
            : '/api/warnings/';
        return fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => response.json());
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize on dashboard page
    if (document.getElementById('driftChart') || document.querySelector('.dashboard-container')) {
        DashboardAutoRefresh.init();
    }
});

// Pause auto-refresh when tab is hidden
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        DashboardAutoRefresh.isEnabled = false;
    } else {
        DashboardAutoRefresh.isEnabled = true;
    }
});
