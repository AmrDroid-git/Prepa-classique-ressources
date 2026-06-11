const page = document.body.dataset.page;

const resourcesConfig = {
  folders: {
    path: "data/folders.json",
    badge: "Dossier Drive",
    icon: "🗂️",
    button: "Ouvrir le dossier",
    showOwner: true
  },
  files: {
    path: "data/files.json",
    badge: "Fichier Drive",
    icon: "📄",
    button: "Ouvrir le fichier",
    showOwner: false
  },
  websites: {
    path: "data/websites.json",
    badge: "Site web",
    icon: "🌐",
    button: "Visiter le site",
    showOwner: false
  }
};

const cleanText = (value) => String(value || "").trim();

const normalize = (value) => cleanText(value)
  .toLowerCase()
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "");

const ownerLabel = (owner) => {
  const value = cleanText(owner);
  const invalid = ["view sort options", "sort", "null", "undefined", ""];
  return invalid.includes(value.toLowerCase()) ? "Non indiqué" : value;
};

const setActiveNav = () => {
  document.querySelectorAll("[data-nav]").forEach((link) => {
    link.classList.toggle("active", link.dataset.nav === page);
  });
};

const setupMobileNav = () => {
  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  if (!toggle || !links) return;

  toggle.addEventListener("click", () => {
    const isOpen = links.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });
};

const setYear = () => {
  document.querySelectorAll("#year").forEach((element) => {
    element.textContent = new Date().getFullYear();
  });
};

const loadJson = async (path) => {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Impossible de charger ${path}`);
  return response.json();
};

const createCard = (item, config) => {
  const card = document.createElement("article");
  card.className = "resource-card";

  const top = document.createElement("div");
  top.className = "resource-top";

  const badge = document.createElement("span");
  badge.className = "resource-badge";
  badge.textContent = `${config.icon} ${config.badge}`;
  top.appendChild(badge);

  const title = document.createElement("h2");
  title.textContent = cleanText(item.predicted_name) || "Ressource sans nom";

  const description = document.createElement("p");
  description.className = "resource-description";
  description.textContent = cleanText(item.predicted_description) || "Aucune description disponible.";

  const link = document.createElement("a");
  link.className = "btn btn-primary resource-link";
  link.href = cleanText(item.drive_link) || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = config.button;

  card.append(top, title, description);

  if (config.showOwner) {
    const owner = document.createElement("p");
    owner.className = "owner-line";
    const strong = document.createElement("strong");
    strong.textContent = "Propriétaire : ";
    owner.append(strong, document.createTextNode(ownerLabel(item.owner)));
    card.appendChild(owner);
  }

  card.appendChild(link);
  return card;
};

const renderResources = (items, config, query = "") => {
  const grid = document.getElementById("resourcesGrid");
  const count = document.getElementById("resultCount");
  const empty = document.getElementById("emptyState");
  if (!grid || !count || !empty) return;

  const normalizedQuery = normalize(query);
  const filtered = items.filter((item) => {
    const searchable = [
      item.predicted_name,
      item.predicted_description,
      item.owner,
      item.drive_link
    ].map(normalize).join(" ");
    return searchable.includes(normalizedQuery);
  });

  grid.replaceChildren(...filtered.map((item) => createCard(item, config)));
  count.textContent = `${filtered.length} ressource${filtered.length > 1 ? "s" : ""} affichée${filtered.length > 1 ? "s" : ""}`;
  empty.classList.toggle("hidden", filtered.length !== 0);
};

const setupResourcesPage = async () => {
  const config = resourcesConfig[page];
  if (!config) return;

  const grid = document.getElementById("resourcesGrid");
  const count = document.getElementById("resultCount");
  const search = document.getElementById("resourceSearch");

  try {
    const items = await loadJson(config.path);
    renderResources(items, config);
    search?.addEventListener("input", (event) => renderResources(items, config, event.target.value));
  } catch (error) {
    if (grid) grid.innerHTML = "";
    if (count) count.textContent = "Erreur de chargement";
    const empty = document.getElementById("emptyState");
    if (empty) {
      empty.textContent = "Impossible de charger les ressources. Lance le site avec un serveur local, par exemple : python -m http.server 3000";
      empty.classList.remove("hidden");
    }
  }
};

const setupHomeStats = async () => {
  if (page !== "home") return;
  const stats = document.getElementById("homeStats");
  if (!stats) return;

  try {
    const [folders, files, websites] = await Promise.all([
      loadJson("data/folders.json"),
      loadJson("data/files.json"),
      loadJson("data/websites.json")
    ]);

    const data = [
      { label: "Dossiers", value: folders.length },
      { label: "Fichiers", value: files.length },
      { label: "Sites", value: websites.length }
    ];

    stats.replaceChildren(...data.map((item) => {
      const card = document.createElement("article");
      card.className = "stat-card";
      const value = document.createElement("span");
      value.textContent = item.value;
      const label = document.createElement("p");
      label.textContent = item.label;
      card.append(value, label);
      return card;
    }));
  } catch (error) {
    stats.innerHTML = "<p class='empty-state'>Impossible de charger les statistiques.</p>";
  }
};


const fetchAllData = async () => {
  const [folders, files, websites] = await Promise.all([
    loadJson("data/folders.json"),
    loadJson("data/files.json"),
    loadJson("data/websites.json")
  ]);

  return {
    generatedAt: new Date().toISOString(),
    source: "Prépa Classique Ressources",
    totals: {
      folders: folders.length,
      files: files.length,
      websites: websites.length,
      all: folders.length + files.length + websites.length
    },
    folders,
    files,
    websites
  };
};

const downloadBlob = (content, filename, type) => {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

const buildTxtExport = (data) => {
  const lines = [];

  lines.push("PREPA CLASSIQUE RESSOURCES");
  lines.push("Export généré le : " + new Date(data.generatedAt).toLocaleString("fr-FR"));
  lines.push("");
  lines.push(`Total : ${data.totals.all} ressources`);
  lines.push(`Dossiers : ${data.totals.folders}`);
  lines.push(`Fichiers : ${data.totals.files}`);
  lines.push(`Sites web : ${data.totals.websites}`);
  lines.push("\n==================================================\n");

  const addSection = (title, items, hasOwner = false) => {
    lines.push(title.toUpperCase());
    lines.push("-".repeat(title.length));
    lines.push("");

    items.forEach((item, index) => {
      lines.push(`${index + 1}. ${cleanText(item.predicted_name) || "Ressource sans nom"}`);
      if (hasOwner) lines.push(`Propriétaire : ${ownerLabel(item.owner)}`);
      lines.push(`Description : ${cleanText(item.predicted_description) || "Aucune description disponible."}`);
      lines.push(`Lien : ${cleanText(item.drive_link) || "Lien non disponible"}`);
      lines.push("");
    });

    lines.push("==================================================\n");
  };

  addSection("Dossiers Drive", data.folders, true);
  addSection("Fichiers Drive", data.files, false);
  addSection("Sites web", data.websites, false);

  return lines.join("\n");
};

const showDownloadMessage = (message, isError = false) => {
  const element = document.getElementById("downloadMessage");
  if (!element) return;
  element.textContent = message;
  element.classList.remove("hidden");
  element.style.borderStyle = isError ? "solid" : "dashed";
};

const setupDownloadAllPage = () => {
  if (page !== "downloadAll") return;

  const jsonButton = document.getElementById("downloadJsonBtn");
  const txtButton = document.getElementById("downloadTxtBtn");

  jsonButton?.addEventListener("click", async () => {
    try {
      const data = await fetchAllData();
      const json = JSON.stringify(data, null, 2);
      downloadBlob(json, "prepa-classique-ressources.json", "application/json;charset=utf-8");
      showDownloadMessage("Le fichier JSON complet a été généré avec succès.");
    } catch (error) {
      showDownloadMessage("Impossible de générer le fichier JSON. Lance le site avec un serveur local, par exemple : python -m http.server 3000", true);
    }
  });

  txtButton?.addEventListener("click", async () => {
    try {
      const data = await fetchAllData();
      const txt = buildTxtExport(data);
      downloadBlob(txt, "prepa-classique-ressources.txt", "text/plain;charset=utf-8");
      showDownloadMessage("Le fichier TXT complet a été généré avec succès.");
    } catch (error) {
      showDownloadMessage("Impossible de générer le fichier TXT. Lance le site avec un serveur local, par exemple : python -m http.server 3000", true);
    }
  });
};

setActiveNav();
setupMobileNav();
setYear();
setupResourcesPage();
setupHomeStats();
setupDownloadAllPage();
