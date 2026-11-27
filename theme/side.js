// SPDX-License-Identifier: CC0-1.0
// Close the side panels once a link in one is followed, so the page or tree
// it leads to is not left behind a panel.
document.addEventListener("click", (event) => {
  if (!event.target.closest(".side-panel a, .side-panel .link")) return;
  for (const open of document.querySelectorAll(".side-switch")) open.checked = false;
});
