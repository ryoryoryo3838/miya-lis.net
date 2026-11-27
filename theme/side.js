// SPDX-License-Identifier: CC0-1.0
// Narrow screens. The site navigation stands above the page: open the page
// scrolled past it, so the tree comes first. After a contents link in the
// side view leads to a tree on this page, bring the page back into view.
// Run again once the fonts are in, which changes the navigation's height.
function skipNavigation() {
  const page = document.getElementById("page-view"), nav = document.getElementById("nav-top");
  if (!page || !nav || nav.offsetHeight === 0 || location.hash) return;
  page.scrollTop = nav.nextElementSibling.getBoundingClientRect().top - page.getBoundingClientRect().top + page.scrollTop;
}
skipNavigation();
document.fonts?.ready.then(skipNavigation);
document.addEventListener("htmx:afterSettle", skipNavigation);
document.addEventListener("click", (event) => {
  if (!event.target.closest(".side-body .link[data-target]")) return;
  setTimeout(() => document.getElementById("main-wrapper")?.scrollTo({ left: 0, behavior: "smooth" }), 0);
});
