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

function update() {
    fetch('/state')
        .then(r => r.json())
        .then(data => {
            try {
                if (data.watching) {
                    document.getElementById('watching').innerHTML = 
                        '<span class="watching">Watching:</span> ' + escapeHtml(data.watching);
                    
                    let statsText = Object.keys(data.files).length + ' files tracked, ' + 
                                   data.changes.length + ' changes';
                    
                    // Add state vector preview if available
                    if (data.state_vector && data.state_vector.length > 0) {
                        if (data.state_vector.length <= 10) {
                            // If vector is short, show all elements
                            const vectorStr = data.state_vector.map(v => Number(v).toFixed(2)).join(', ');
                            statsText += `<div class="vector-info">State vector: [${vectorStr}]</div>`;
                        } else {
                            // Show first 5 and last 5 elements
                            const vectorHead = data.state_vector.slice(0, 5).map(v => Number(v).toFixed(2)).join(', ');
                            const vectorTail = data.state_vector.slice(-5).map(v => Number(v).toFixed(2)).join(', ');
                            statsText += `<div class="vector-info">State vector: [${vectorHead} ... ${vectorTail}]</div>`;
                        }
                    }
                    
                    document.getElementById('stats').innerHTML = statsText;
                }
                
                const changesDiv = document.getElementById('changes');
                changesDiv.innerHTML = data.changes.map((c, i) => {
                    let html = '<div>';
                    html += '<div class="change" onclick="toggleDiff(' + i + ')">';
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