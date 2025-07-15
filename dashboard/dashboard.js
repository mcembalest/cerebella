function formatDiff(diff) {
    if (!diff) return '';
    return diff.split('\\n').map(line => {
        if (line.startsWith('+'))
            return '<span class="diff-add">' + escapeHtml(line) + '</span>';
        if (line.startsWith('-'))
            return '<span class="diff-del">' + escapeHtml(line) + '</span>';
        return escapeHtml(line);
    }).join('\\n');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

let openDiffs = new Set();

function toggleDiff(index) {
    const diff = document.getElementById('diff-' + index);
    const currentDisplay = window.getComputedStyle(diff).display;
    if (currentDisplay === 'none') {
        diff.style.display = 'block';
        openDiffs.add(index);
    } else {
        diff.style.display = 'none';
        openDiffs.delete(index);
    }
}

function toggleLock(filepath) {
    fetch('/toggle-lock', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({filepath: filepath})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            update();
        }
    })
    .catch(err => console.error('Error toggling lock:', err));
}

function lockAll() {
    fetch('/lock-all', {method: 'POST'})
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            update();
        }
    })
    .catch(err => console.error('Error locking all:', err));
}

function unlockAll() {
    fetch('/unlock-all', {method: 'POST'})
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            update();
        }
    })
    .catch(err => console.error('Error unlocking all:', err));
}

function update() {
    fetch('/state')
        .then(r => r.json())
        .then(data => {
            try {
                if (data.watching) {
                    document.getElementById('watching').innerHTML = 
                        '<span class="watching">Currently watching:</span> ' + escapeHtml(data.watching);
                } else {
                    document.getElementById('watching').innerHTML = 'Not watching any directory';
                }
                
                let statsText = '<strong>' + Object.keys(data.files).length + '</strong> files tracked';
                statsText += ' | <strong>' + data.changes.length + '</strong> total changes';
                
                let lockedCount = 0;
                if (data.file_locks) {
                    lockedCount = Object.values(data.file_locks).filter(locked => locked).length;
                    statsText += ' | <strong>' + lockedCount + '</strong> files locked';
                }
                document.getElementById('stats').innerHTML = statsText;
                
                if (data.watching && Object.keys(data.files).length > 0) {
                    // Count changes per file
                    const changeCountMap = new Map();
                    data.changes.forEach(change => {
                        const fullPath = data.watching + '/' + change.file;
                        changeCountMap.set(fullPath, (changeCountMap.get(fullPath) || 0) + 1);
                    });
                    
                    const allFiles = [];
                    Object.keys(data.files).forEach(fullPath => {
                        const relativePath = fullPath.replace(data.watching + '/', '');
                        allFiles.push({
                            fullPath: fullPath,
                            file: relativePath,
                            changeCount: changeCountMap.get(fullPath) || 0,
                            locked: data.file_locks && data.file_locks[fullPath]
                        });
                    });
                    
                    allFiles.sort((a, b) => b.changeCount - a.changeCount);
                    
                    let summaryHtml = '<div class="file-summary-grid">';
                    allFiles.forEach(info => {
                        const lockIcon = info.locked ? '🔒' : '🔓';
                        const lockClass = info.locked ? 'locked' : 'unlocked';
                        const changeClass = info.changeCount === 0 ? 'no-changes' : '';
                        summaryHtml += `
                            <div class="file-summary-item ${lockClass} ${changeClass}">
                                <span class="file-name">${escapeHtml(info.file)}</span>
                                <span class="change-count">${info.changeCount} change${info.changeCount !== 1 ? 's' : ''}</span>
                                <button class="lock-toggle-small" onclick="toggleLock('${info.fullPath.replace(/'/g, "\\'")}')" title="${info.locked ? 'Unlock' : 'Lock'} file">
                                    ${lockIcon}
                                </button>
                            </div>
                        `;
                    });
                    summaryHtml += '</div>';
                    document.getElementById('file-summary').innerHTML = summaryHtml;
                } else {
                    document.getElementById('file-summary').innerHTML = '<div class="no-changes">No files tracked yet</div>';
                }
                
                // Update changes list (without lock buttons per your request)
                const changesDiv = document.getElementById('changes');
                changesDiv.innerHTML = data.changes.map((c, i) => {
                    const fullPath = data.watching + '/' + c.file;
                    const isLocked = data.file_locks && data.file_locks[fullPath];
                    
                    let html = '<div>';
                    html += '<div class="change' + (isLocked ? ' locked-file' : '') + '" onclick="toggleDiff(' + i + ')">';
                    html += '<div class="change-info">';
                    html += escapeHtml(c.time) + ' - ' + escapeHtml(c.file);
                    html += ' (change: ' + (c.size_change > 0 ? '+' : '') + c.size_change + ' bytes';
                    if (c.lines_change !== null) {
                        html += ', ' + (c.lines_change > 0 ? '+' : '') + c.lines_change + ' lines';
                    }
                    html += ')</div>';
                    html += '</div>';
                    if (c.diff) {
                        const isOpen = openDiffs.has(i);
                        html += '<div class="diff" id="diff-' + i + '" style="display: ' + (isOpen ? 'block' : 'none') + '">' + formatDiff(c.diff) + '</div>';
                    }
                    html += '</div>';
                    return html;
                }).join('');
            } catch (error) {
                console.error('Error updating UI:', error);
            }
        })
        .catch(error => {
            console.error('Error fetching state:', error);
        });
}

setInterval(update, 1000);
update();