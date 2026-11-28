// SPDX-License-Identifier: CC0-1.0
// The site navigation stands above the page. Open the page scrolled past it,
// at once rather than gliding, so the tree comes first; and when scrolling up
// reaches the site-name line, stop there once, briefly, so the navigation
// shows on the next scroll up, or from [Navigation]. [Back to top] shows once
// the page is scrolled down. On narrow screens the
// page scrolls in its own column; on wide ones the window scrolls. After a
// contents link in the narrow-screen side view leads to a tree on this page,
// bring the page back into view.
const HOLD = 300; // ms the stop holds, so momentum alone does not carry past it
// armed: the stop applies (set again on returning below it).
let armed = true, heldUntil = 0, lastY = Infinity;

function scroller() {
  const page = document.getElementById("page-view");
  return page && getComputedStyle(page).overflowY === "auto" && page.scrollHeight > page.clientHeight ? page : null;
}
function y() { const s = scroller(); return s ? s.scrollTop : window.scrollY; }
function scrollToY(top, behavior) { (scroller() || window).scrollTo({ top, behavior }); }
// Where the site-name line starts, in the scroller's coordinates.
function stopY() {
  const nav = document.getElementById("nav-top"), s = scroller();
  if (!nav) return null;
  const header = nav.nextElementSibling.getBoundingClientRect().top;
  return s ? header - s.getBoundingClientRect().top + s.scrollTop : header + window.scrollY;
}

function skipNavigation() {
  const top = stopY();
  if (top === null || location.hash) return;
  scrollToY(top, "instant");
  lastY = y();
}

function onScroll() {
  const top = stopY();
  if (top === null) return;
  const now = y();
  // [Back to top] shows once the page is scrolled well past the site-name line.
  document.body.classList.toggle("is-scrolled", now > top + 200);
  if (now >= top + 1) armed = true; // back on the page: the stop applies again
  else if (lastY >= top - 1 && now < top - 1 && (armed || Date.now() < heldUntil)) {
    scrollToY(top, "instant"); // stop once at the site-name line
    if (armed) heldUntil = Date.now() + HOLD;
    armed = false;
    lastY = top;
    return;
  }
  lastY = now;
}

skipNavigation();
// Again once the fonts are in, which changes the navigation's height.
document.fonts?.ready.then(skipNavigation);
document.addEventListener("htmx:afterSettle", skipNavigation);
window.addEventListener("scroll", onScroll, { passive: true });
document.getElementById("page-view")?.addEventListener("scroll", onScroll, { passive: true });
document.addEventListener("click", (event) => {
  // [Navigation] goes all the way up: no stop on its way.
  if (event.target.closest(".side-tab--nav")) { armed = false; heldUntil = 0; return; }
  if (!event.target.closest(".side-body .link[data-target]")) return;
  setTimeout(() => document.getElementById("main-wrapper")?.scrollTo({ left: 0 }), 0);
});
