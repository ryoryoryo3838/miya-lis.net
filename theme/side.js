// SPDX-License-Identifier: CC0-1.0
// Close the narrow-screen side panel once a link in it is followed, so the
// tree it scrolls to is not left behind the panel.
document.addEventListener("click", (event) => {
  if (!event.target.closest(".side-panel a, .side-panel .link")) return;
  const open = document.getElementById("side-open");
  if (open) open.checked = false;
});
