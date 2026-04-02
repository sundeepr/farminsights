/**
 * nav.js — Sidebar hamburger toggle + backdrop for mobile
 */

document.addEventListener('DOMContentLoaded', () => {
    const hamburger = document.getElementById('hamburgerBtn');
    const sidebar = document.getElementById('sidebarNav');
    const backdrop = document.getElementById('sidebarBackdrop');

    function openSidebar() {
        sidebar.classList.add('open');
        backdrop.classList.add('visible');
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        backdrop.classList.remove('visible');
    }

    if (hamburger && sidebar) {
        hamburger.addEventListener('click', () => {
            sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
        });
    }

    if (backdrop) {
        backdrop.addEventListener('click', closeSidebar);
    }

    // Close on nav link click (so page navigates smoothly on mobile)
    if (sidebar) {
        sidebar.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', closeSidebar);
        });
    }
});
