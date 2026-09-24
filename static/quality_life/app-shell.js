/* Shared navigation only; assessment data remains server-owned. */
(() => {
  'use strict';
  const body = document.body;
  const sidebar = document.getElementById('app-navigation');
  const toggle = document.querySelector('.ql-menu-toggle');
  const backdrop = document.querySelector('.ql-backdrop');
  const workspace = document.querySelector('.ql-workspace');
  const closeButton = document.querySelector('[data-drawer-close]');
  if (!sidebar || !toggle || !backdrop || !workspace) return;
  const mobile = window.matchMedia('(max-width: 900px)');
  let desktopCollapsed = false;
  let drawerOpen = false;
  const focusables = () => Array.from(sidebar.querySelectorAll('a[href], button, input:not([type="hidden"]), [tabindex="0"]')).filter(element => element.getClientRects().length && !element.disabled);
  function render() {
    const open = mobile.matches ? drawerOpen : !desktopCollapsed;
    body.classList.toggle('ql-sidebar-collapsed', !mobile.matches && desktopCollapsed);
    body.classList.toggle('ql-drawer-open', mobile.matches && drawerOpen);
    sidebar.inert = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    backdrop.hidden = !(mobile.matches && drawerOpen);
    workspace.inert = mobile.matches && drawerOpen;
    if (mobile.matches && drawerOpen) {
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
    } else {
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
    }
  }
  function closeDrawer(returnFocus = true) {
    drawerOpen = false;
    render();
    if (returnFocus) toggle.focus();
  }
  toggle.addEventListener('click', () => {
    if (mobile.matches) {
      drawerOpen = !drawerOpen;
      render();
      if (drawerOpen) (closeButton || focusables()[0]).focus();
      else toggle.focus();
    } else {
      desktopCollapsed = !desktopCollapsed;
      render();
    }
  });
  backdrop.addEventListener('click', () => closeDrawer());
  closeButton?.addEventListener('click', () => closeDrawer());
  document.addEventListener('keydown', event => {
    if (!mobile.matches || !drawerOpen) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeDrawer();
    }
    if (event.key === 'Tab') {
      const items = focusables();
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
  });
  mobile.addEventListener('change', () => {
    const focusInSidebar = sidebar.contains(document.activeElement);
    drawerOpen = false;
    render();
    if (focusInSidebar && sidebar.inert) toggle.focus();
  });
  render();
})();
