// Global JS Interactions

document.addEventListener('DOMContentLoaded', () => {
    // Dismiss flash messages automatically
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            setTimeout(() => msg.remove(), 500); // Wait for transition
        }, 4000);
    });
});

// Flash message helper for JS generated messages
function showFlash(message, type = 'success') {
    const container = document.getElementById('flash-container');
    if(!container) return;

    const div = document.createElement('div');
    const isError = type === 'error' || type === 'danger';
    div.className = `flash-message glass flex items-center justify-between p-4 mb-4 rounded-xl border-l-4 ${isError ? 'border-red-500 text-red-700' : 'border-agri-500 text-agri-800'}`;
    
    div.innerHTML = `
        <div class="flex items-center gap-3">
            <svg class="w-5 h-5 ${isError ? 'text-red-500' : 'text-agri-500'}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                ${isError 
                    ? '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />'
                    : '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />'
                }
            </svg>
            <span class="font-medium">${message}</span>
        </div>
        <button onclick="this.parentElement.remove()" class="text-gray-400 hover:text-gray-600 transition-colors">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>
    `;
    container.appendChild(div);
}
