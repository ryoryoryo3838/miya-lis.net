// SPDX-License-Identifier: CC0-1.0
// Narrow screens: after a link in the side view leads to a tree on this page,
// bring the page back into view beside it.
document.addEventListener("click", (event) => {
  if (!event.target.closest(".side-body .link[data-target]")) return;
  setTimeout(() => document.getElementById("main-wrapper")?.scrollTo({ left: 0, behavior: "smooth" }), 0);
});
