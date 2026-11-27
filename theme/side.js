// SPDX-License-Identifier: CC0-1.0
// The site navigation stands above the page. Open the page scrolled past it,
// at once rather than gliding, so the tree comes first; and when scrolling up
// reaches the site-name line, stop there, so the navigation shows only on a
// fresh scroll up after a pause, or from [Navigation]. On narrow screens the
// page scrolls in its own column; on wide ones the window scrolls. After a
// contents link in the narrow-screen side view leads to a tree on this page,
// bring the page back into view.
const PAUSE = 600; // ms without scrolling that ends a gesture, momentum included
// armed: the stop applies (set again on returning below it). passing: this
// gesture began while resting at the stop, after a pause, so it may go on up.
let armed = true, passing = false, lastY = Infinity, lastEvent = 0;

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

// Every wheel or scroll event: a gesture that starts after a pause while
// resting at the stop may pass it.
function note(top) {
  const t = Date.now();
  if (t - lastEvent > PAUSE && Math.abs(y() - top) < 2) passing = true;
  lastEvent = t;
}

function onScroll() {
  const top = stopY();
  if (top === null) return;
  note(top);
  const now = y();
  if (now >= top + 1) { armed = true; passing = false; } // back on the page
  else if (armed && !passing && lastY >= top - 1 && now < top - 1) {
    scrollToY(top, "instant"); // stop at the site-name line
    lastY = top;
    return;
  } else if (now < top - 1) armed = false;
  lastY = now;
}

// Wide screens scroll the window by wheel or trackpad: hold upward input at
// the stop until the gesture has paused, so momentum cannot carry past it.
function onWheel(event) {
  const top = stopY();
  if (top === null) return;
  note(top);
  if (event.deltaY < 0 && armed && !passing && Math.abs(y() - top) < 2) event.preventDefault();
}

skipNavigation();
// Again once the fonts are in, which changes the navigation's height.
document.fonts?.ready.then(skipNavigation);
document.addEventListener("htmx:afterSettle", skipNavigation);
window.addEventListener("scroll", onScroll, { passive: true });
document.getElementById("page-view")?.addEventListener("scroll", onScroll, { passive: true });
window.addEventListener("wheel", onWheel, { passive: false });
document.addEventListener("click", (event) => {
  // [Navigation] goes all the way up: no stop on its way.
  if (event.target.closest(".side-tab--nav")) { passing = true; return; }
  if (!event.target.closest(".side-body .link[data-target]")) return;
  setTimeout(() => document.getElementById("main-wrapper")?.scrollTo({ left: 0 }), 0);
});
