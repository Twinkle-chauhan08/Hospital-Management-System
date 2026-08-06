/* Hospital Management System - JavaScript */

// ==================== NOTIFICATION SYSTEM ====================

function loadNotifications() {
    fetch('/api/notifications')
        .then(response => response.json())
        .then(data => {
            updateNotificationBadge(data.count);
            displayNotifications(data.notifications);
        })
        .catch(error => console.error('Error loading notifications:', error));
}

function updateNotificationBadge(count) {
    const badge = document.querySelector('.notification-badge');
    if (badge) {
        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'block';
        } else {
            badge.style.display = 'none';
        }
    }
}

function displayNotifications(notifications) {
    const notificationContainer = document.querySelector('.notification-container');
    if (notificationContainer && notifications.length > 0) {
        notificationContainer.innerHTML = notifications.map(notif => `
            <div class="notification-item">
                <p>${notif.message}</p>
                <button class="btn btn-sm btn-outline-primary" onclick="markNotificationRead(${notif.notification_id})">
                    Mark as Read
                </button>
            </div>
        `).join('');
    }
}

function markNotificationRead(notificationId) {
    fetch(`/api/mark-notification-read/${notificationId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                loadNotifications();
            }
        })
        .catch(error => console.error('Error marking notification as read:', error));
}

// ==================== FORM VALIDATION ====================

function validateEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

function validatePassword(password) {
    return password.length >= 6;
}

function validateForm(formId) {
    const form = document.getElementById(formId);
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    }
}

// ==================== DATE & TIME UTILITIES ====================

function formatDate(dateString) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

function formatTime(timeString) {
    const [hours, minutes] = timeString.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
}

function setMinimumDate() {
    const dateInputs = document.querySelectorAll('input[type="date"]');
    const today = new Date().toISOString().split('T')[0];
    dateInputs.forEach(input => input.setAttribute('min', today));
}

// ==================== USER FEEDBACK ====================

function showSuccess(message) {
    showAlert(message, 'success');
}

function showError(message) {
    showAlert(message, 'danger');
}

function showWarning(message) {
    showAlert(message, 'warning');
}

function showAlert(message, type) {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            <i class="fas fa-${getAlertIcon(type)}"></i> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    const container = document.querySelector('.container');
    if (container) {
        const alertDiv = document.createElement('div');
        alertDiv.innerHTML = alertHtml;
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

function getAlertIcon(type) {
    const icons = {
        'success': 'check-circle',
        'danger': 'exclamation-circle',
        'warning': 'exclamation-triangle',
        'info': 'info-circle'
    };
    return icons[type] || 'info-circle';
}

// ==================== TABLE UTILITIES ====================

function makeTableSortable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const headers = table.querySelectorAll('th');
    headers.forEach((header, index) => {
        header.style.cursor = 'pointer';
        header.addEventListener('click', () => {
            sortTableByColumn(table, index);
        });
    });
}

function sortTableByColumn(table, columnIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    rows.sort((a, b) => {
        const aValue = a.children[columnIndex].textContent;
        const bValue = b.children[columnIndex].textContent;
        
        // Try to parse as numbers
        const aNum = parseFloat(aValue);
        const bNum = parseFloat(bValue);
        
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return aNum - bNum;
        }
        
        return aValue.localeCompare(bValue);
    });
    
    rows.forEach(row => tbody.appendChild(row));
}

// ==================== SEARCH & FILTER ====================

function filterTable(inputId, tableId, columnIndex = 0) {
    const input = document.getElementById(inputId);
    const table = document.getElementById(tableId);
    
    if (!input || !table) return;
    
    input.addEventListener('keyup', () => {
        const filter = input.value.toUpperCase();
        const rows = table.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const cell = row.children[columnIndex];
            if (cell) {
                const text = cell.textContent || cell.innerText;
                row.style.display = text.toUpperCase().includes(filter) ? '' : 'none';
            }
        });
    });
}

// ==================== MODAL UTILITIES ====================

function confirmAction(message) {
    return confirm(message);
}

function showModal(modalId) {
    const modal = new bootstrap.Modal(document.getElementById(modalId));
    modal.show();
}

function hideModal(modalId) {
    const modal = bootstrap.Modal.getInstance(document.getElementById(modalId));
    if (modal) modal.hide();
}

// ==================== LOCAL STORAGE ====================

function saveToLocalStorage(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function getFromLocalStorage(key) {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : null;
}

function removeFromLocalStorage(key) {
    localStorage.removeItem(key);
}

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', function() {
    // Set minimum dates on all date inputs
    setMinimumDate();
    
    // Load notifications if user is logged in
    if (document.querySelector('.navbar-brand')) {
        loadNotifications();
        // Refresh notifications every 30 seconds
        setInterval(loadNotifications, 30000);
    }
    
    // Initialize Bootstrap tooltips and popovers
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Motion on scroll (Framer-like)
    const motionItems = document.querySelectorAll('.motion');
    const io = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('motion-on');
                io.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15 });
    motionItems.forEach(el => io.observe(el));

    // Navbar solid on scroll for homepage
    const nav = document.getElementById('mainNav');
    const isHome = nav && nav.classList.contains('navbar-transparent');
    if (isHome) {
        const onScroll = () => {
            if (window.scrollY > 40) {
                nav.classList.remove('navbar-transparent');
                nav.classList.add('bg-hospital');
            } else {
                nav.classList.add('navbar-transparent');
                nav.classList.remove('bg-hospital');
            }
        };
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }
});

// ==================== UTILITY FUNCTIONS ====================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Export for use in other scripts
window.HospitalApp = {
    loadNotifications,
    markNotificationRead,
    showSuccess,
    showError,
    showWarning,
    showAlert,
    formatDate,
    formatTime,
    validateEmail,
    validatePassword,
    confirmAction,
    showModal,
    hideModal,
    saveToLocalStorage,
    getFromLocalStorage,
    removeFromLocalStorage
};
