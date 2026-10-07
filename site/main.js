const sidebar = document.getElementById("sidebar");
const toggle = document.querySelector(".nav-toggle");

function setMenu(open) {
  sidebar.classList.toggle("open", open);
  sidebar.setAttribute("aria-hidden", String(!open));
  toggle.setAttribute("aria-expanded", String(open));
}

toggle.addEventListener("click", () => setMenu(true));
sidebar.querySelector(".sidebar-close").addEventListener("click", () => setMenu(false));
sidebar.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setMenu(false)));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setMenu(false);
});
