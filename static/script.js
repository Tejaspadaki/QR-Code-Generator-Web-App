function toggleTheme() {
    const html = document.documentElement;
    const theme = html.getAttribute("data-theme") === "light" ? "dark" : "light";
    html.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }
  
  function updateQRFields() {
    const type = document.getElementById("qr_type").value;
    const container = document.getElementById("qr_fields");
  
    container.innerHTML = "";
  
    if (type === "url") {
      container.innerHTML = `<input type="text" name="url" placeholder="Enter URL" required />`;
    } else if (type === "whatsapp") {
      container.innerHTML = `
        <input type="text" name="phone" placeholder="Phone (with country code)" required />
        <input type="text" name="message" placeholder="Message" required />
      `;
    } else if (type === "location") {
      container.innerHTML = `
        <input type="text" name="lat" placeholder="Latitude" required />
        <input type="text" name="lon" placeholder="Longitude" required />
      `;
    } else if (type === "vcard") {
      container.innerHTML = `
        <input type="text" name="name" placeholder="Full Name" required />
        <input type="text" name="phone" placeholder="Phone" required />
        <input type="email" name="email" placeholder="Email" required />
      `;
    }
  }
  
  window.addEventListener("DOMContentLoaded", () => {
    const saved = localStorage.getItem("theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
  });
  