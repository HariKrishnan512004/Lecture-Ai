// Display key points section.
function displayKeyPoints(keyPoints) {
    const container = document.getElementById('keyPointsContainer');

    if (!container) {
        return;
    }

    if (!keyPoints || keyPoints.length === 0) {
        container.innerHTML = '<p>No key points extracted</p>';
        return;
    }

    let html = '<div class="key-points">';
    html += `<h3>Key Points (${keyPoints.length})</h3>`;
    html += '<ul class="bullet-list">';

    keyPoints.forEach((point, index) => {
        html += `<li class="animate-point" style="animation-delay: ${index * 0.1}s">${point}</li>`;
    });

    html += '</ul></div>';
    container.innerHTML = html;
}
