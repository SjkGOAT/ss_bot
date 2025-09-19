/* static/script.js
   Dashboard frontend:
   - loads roles/channels/saved settings
   - dynamic blacklist & ticket categories UI
   - loads bans/timeouts/tickets/warnings
   - creates ticket panels
   - saves settings
   - Enhanced with environment variable support
*/

document.addEventListener("DOMContentLoaded", () => {
  const serverId = window.currentServerId;
  const saved = window.initialSettings || {};

  // Elements
  const rolesSelect = document.getElementById("join_role");
  const welcomeChannelSelect = document.getElementById("welcome_channel");
  const welcomeMessageInput = document.getElementById("welcome_message");
  const blacklistContainer = document.getElementById("blacklist-container");
  const addBlacklistBtn = document.getElementById("add-blacklist-word");
  const saveBlacklistBtn = document.getElementById("save-blacklist");

  const ticketCategoriesContainer = document.getElementById("ticket-categories-container");
  const addTicketCategoryBtn = document.getElementById("add-ticket-category");
  const ticketMessageTextarea = document.getElementById("ticket_message");
  const ticketChannelSelect = document.getElementById("ticket_channel");
  const createPanelBtn = document.getElementById("create-panel");

  const bansList = document.getElementById("bans-list");
  const timeoutsList = document.getElementById("timeouts-list");
  const ticketsList = document.getElementById("tickets-list");

  const saveSettingsBtn = document.getElementById("save-settings");
  const saveStatus = document.getElementById("save-status");

  const warnedDropdown = document.getElementById("warned-users-dropdown");
  const userWarningsPanel = document.getElementById("user-warnings");
  const warningsList = document.getElementById("warnings-list");
  const selectedUserName = document.getElementById("selected-user-name");
  const clearWarningsBtn = document.getElementById("clear-warnings");

  const panelPreview = document.getElementById("panel-preview");
  const panelPreviewBody = document.getElementById("panel-preview-body");
  const previewPanelBtn = document.getElementById("preview-panel");

  // API configuration
  const API_CONFIG = {
    BASE_URL: window.location.origin,
    TIMEOUT: 10000, // 10 seconds timeout for API requests
  };

  // Helper
  async function getJSON(path) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);
      
      const fullUrl = path.startsWith('/') ? `${API_CONFIG.BASE_URL}${path}` : path;
      const res = await fetch(fullUrl, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (!res.ok) {
        throw new Error(`API Error: ${res.status} ${res.statusText}`);
      }
      
      return await res.json();
    } catch (error) {
      console.error(`Request failed: ${path}`, error);
      throw error;
    }
  }
  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Fetch and display bot status
  async function loadBotStatus() {
    try {
      const statusData = await getJSON(`/api/bot/status`);
      
      const botOnlineStatus = document.getElementById("bot-online-status");
      const botUptime = document.getElementById("bot-uptime");
      const botCommands = document.getElementById("bot-commands");
      
      if (botOnlineStatus) {
        botOnlineStatus.textContent = statusData.status === "online" ? "🟢 Online" : "🔴 Offline";
        botOnlineStatus.style.color = statusData.status === "online" ? 'var(--success)' : 'var(--danger)';
        botOnlineStatus.className = statusData.status === "online" ? "font-medium" : "font-medium";
      }
      
      if (botUptime) {
        botUptime.textContent = statusData.uptime || "N/A";
      }
      
      if (botCommands) {
        // In a real implementation, you might want to calculate this differently
        // For now we'll just show the number of loaded cogs
        botCommands.textContent = `${statusData.cogs_loaded?.length || 0} modules loaded`;
      }
    } catch (e) {
      console.error("Failed to load bot status:", e);
      const botOnlineStatus = document.getElementById("bot-online-status");
      if (botOnlineStatus) {
        botOnlineStatus.textContent = "❓ Unknown";
        botOnlineStatus.style.color = 'var(--warning)';
      }
    }
  }

  async function init() {
    try {
      const data = await getJSON(`/api/server/${serverId}/data`);
      populateSelect(rolesSelect, data.roles, "No role");
      populateSelect(welcomeChannelSelect, data.channels, "No channel");
      populateSelect(ticketChannelSelect, data.channels, "Select channel for panel");

      const s = data.saved || {};
      if (s.join_role) rolesSelect.value = s.join_role;
      if (s.welcome_channel) welcomeChannelSelect.value = s.welcome_channel;
      welcomeMessageInput.value = s.welcome_message || "Welcome {ping} to {server_name}! We now have {members} members.";
      ticketMessageTextarea.value = s.ticket_message || "Click a button below to create a ticket!";

      renderBlacklistInputs(s.blacklisted_words || []);
      renderTicketCategoryInputs(s.ticket_categories || ["Support", "Bug Report", "Feature Request", "Other"]);

      await loadBans();
      await loadTimeouts();
      await loadTickets();
      await loadWarnedUsers();
      await loadBotStatus();

      addBlacklistBtn?.addEventListener("click", () => appendBlacklistInput(""));
      saveBlacklistBtn?.addEventListener("click", saveBlacklistHandler);
      addTicketCategoryBtn?.addEventListener("click", () => appendTicketCategoryInput(""));
      createPanelBtn?.addEventListener("click", createTicketPanelHandler);
      saveSettingsBtn?.addEventListener("click", saveAllSettings);
      previewPanelBtn?.addEventListener("click", previewPanel);
      warnedDropdown?.addEventListener("change", onWarnedUserChange);
      clearWarningsBtn?.addEventListener("click", clearWarningsHandler);
    } catch (e) {
      console.error("Init error:", e);
      alert("Failed to load server data. Check console for details.");
    }
  }

  function populateSelect(sel, items, placeholderText) {
    if (!sel) return;
    sel.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = placeholderText || "Select...";
    sel.appendChild(placeholder);
    items.forEach(it => {
      const opt = document.createElement("option");
      opt.value = String(it.id);
      opt.textContent = it.name;
      sel.appendChild(opt);
    });
    sel.classList.add("dropdown-scrollable");
  }

  // Blacklist
  function renderBlacklistInputs(words) {
    blacklistContainer.innerHTML = "";
    if (!words.length) appendBlacklistInput("");
    else words.forEach(w => appendBlacklistInput(w));
  }
  function appendBlacklistInput(value) {
    const div = document.createElement("div");
    div.className = "flex gap-2";
    const input = document.createElement("input");
    input.className = "flex-1 p-3 rounded-lg bg-gray-700 text-white border border-gray-600 focus:border-red-400 transition-all";
    input.value = value || "";
    input.placeholder = "Enter word to blacklist...";
    const rem = document.createElement("button");
    rem.className = "px-3 py-1 bg-red-600 hover:bg-red-700 rounded-lg transition-all";
    rem.textContent = "Remove";
    rem.addEventListener("click", () => div.remove());
    div.appendChild(input);
    div.appendChild(rem);
    blacklistContainer.appendChild(div);
  }
  async function saveBlacklistHandler() {
    const words = Array.from(blacklistContainer.querySelectorAll("input"))
      .map(i => i.value.trim()).filter(Boolean);
    try {
      const res = await fetch(`/api/server/${serverId}/blacklist`, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({blacklisted_words: words})
      });
      const j = await res.json();
      if (res.ok && j.success) {
        const btn = saveBlacklistBtn;
        const original = btn.textContent;
        btn.textContent = "✅ Saved!";
        setTimeout(() => btn.textContent = original, 2000);
      } else alert("Failed to save blacklist");
    } catch (e) {
      console.error(e);
      alert("Network error while saving blacklist");
    }
  }

  // Ticket categories
  function renderTicketCategoryInputs(categories) {
    ticketCategoriesContainer.innerHTML = "";
    if (!categories.length) appendTicketCategoryInput("");
    else categories.forEach(c => appendTicketCategoryInput(c));
  }
  function appendTicketCategoryInput(value) {
    const div = document.createElement("div");
    div.className = "flex gap-2";
    const input = document.createElement("input");
    input.className = "flex-1 p-3 rounded-lg bg-gray-700 text-white border border-gray-600 focus:border-purple-400 transition-all";
    input.value = value || "";
    input.placeholder = "Category name...";
    const rem = document.createElement("button");
    rem.className = "px-3 py-1 bg-red-600 hover:bg-red-700 rounded-lg transition-all";
    rem.textContent = "Remove";
    rem.addEventListener("click", () => div.remove());
    div.appendChild(input);
    div.appendChild(rem);
    ticketCategoriesContainer.appendChild(div);
  }

  // Bans
  async function loadBans() {
    bansList.innerHTML = '<div class="text-gray-400">Loading bans...</div>';
    try {
      const j = await getJSON(`/api/server/${serverId}/bans`);
      if (j.success) {
        if (!j.bans.length) {
          bansList.innerHTML = '<div class="text-gray-400 p-3 bg-gray-700 rounded-lg">No banned users</div>';
        } else {
          bansList.innerHTML = "";
          j.bans.forEach(b => {
            const node = document.createElement("div");
            node.className = "p-3 bg-gray-700 rounded-lg";
            node.innerHTML = `<div class="font-semibold text-red-400">${escapeHtml(b.user)}</div>
              <div class="text-sm text-gray-400">Reason: ${escapeHtml(b.reason || "No reason")}</div>`;
            bansList.appendChild(node);
          });
        }
      }
    } catch (e) {
      console.error("loadBans", e);
    }
  }

  // Timeouts
  async function loadTimeouts() {
    timeoutsList.innerHTML = '<div class="text-gray-400">Loading timeouts...</div>';
    try {
      const j = await getJSON(`/api/server/${serverId}/timeouts`);
      if (j.success) {
        if (!j.timeouts.length) {
          timeoutsList.innerHTML = '<div class="text-gray-400 p-3 bg-gray-700 rounded-lg">No timeouts</div>';
        } else {
          timeoutsList.innerHTML = "";
          j.timeouts.forEach(t => {
            const node = document.createElement("div");
            node.className = "p-3 bg-gray-700 rounded-lg";
            node.innerHTML = `<div class="font-semibold text-yellow-400">${escapeHtml(t.user)}</div>
              <div class="text-sm text-gray-400">Until: ${new Date(t.until).toLocaleString()}</div>`;
            timeoutsList.appendChild(node);
          });
        }
      }
    } catch (e) {
      console.error("loadTimeouts", e);
    }
  }

  // Tickets
  async function loadTickets() {
    ticketsList.innerHTML = '<div class="text-gray-400">Loading tickets...</div>';
    try {
      const j = await getJSON(`/api/server/${serverId}/tickets`);
      if (j.success) {
        if (!j.tickets.length) {
          ticketsList.innerHTML = '<div class="text-gray-400 p-3 bg-gray-700 rounded-lg">No open tickets</div>';
        } else {
          ticketsList.innerHTML = "";
          j.tickets.forEach(t => {
            const node = document.createElement("div");
            node.className = "p-3 bg-gray-700 rounded-lg";
            node.innerHTML = `<div class="font-semibold text-green-400">#${escapeHtml(t.id)} — ${escapeHtml(t.user)}</div>
              <div class="text-sm text-gray-400">${escapeHtml(t.category || "Uncategorized")}</div>`;
            ticketsList.appendChild(node);
          });
        }
      }
    } catch (e) {
      console.error("loadTickets", e);
    }
  }

  // Ticket panel
  async function createTicketPanelHandler() {
    const channel = ticketChannelSelect.value;
    const message = ticketMessageTextarea.value.trim();
    const categories = Array.from(ticketCategoriesContainer.querySelectorAll("input"))
      .map(i => i.value.trim()).filter(Boolean);
    if (!channel || !message || !categories.length) return alert("Fill all fields");
    try {
      const res = await fetch(`/api/server/${serverId}/ticket_panel`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({channel, message, categories})
      });
      const j = await res.json();
      if (j.success) alert("Ticket panel created!");
      else alert("Failed to create ticket panel");
    } catch (e) {
      console.error("createTicketPanelHandler", e);
    }
  }

  // Preview
  function previewPanel() {
    const message = ticketMessageTextarea.value.trim();
    const categories = Array.from(ticketCategoriesContainer.querySelectorAll("input"))
      .map(i => i.value.trim()).filter(Boolean);
    panelPreviewBody.innerHTML = `<p class="mb-3">${escapeHtml(message)}</p>`;
    const btns = document.createElement("div");
    btns.className = "flex flex-wrap gap-2";
    categories.forEach(c => {
      const b = document.createElement("button");
      b.className = "px-3 py-1 bg-purple-600 text-white rounded-lg";
      b.textContent = c;
      btns.appendChild(b);
    });
    panelPreviewBody.appendChild(btns);
    panelPreview.classList.remove("hidden");
  }

  // Warnings
  async function loadWarnedUsers() {
    warnedDropdown.innerHTML = '<option value="">Loading users...</option>';
    try {
      const j = await getJSON(`${API_CONFIG.BASE_URL}/api/server/${serverId}/warnings`);
      if (j.success) {
        warnedDropdown.innerHTML = '<option value="">Select user...</option>';
        if (j.users && j.users.length > 0) {
          j.users.forEach(u => {
            const opt = document.createElement("option");
            opt.value = u.id;
            opt.textContent = `${u.name} (${u.count} warnings)`;
            warnedDropdown.appendChild(opt);
          });
        } else {
          warnedDropdown.innerHTML = '<option value="">No warned users</option>';
        }
      } else {
        warnedDropdown.innerHTML = '<option value="">Error loading users</option>';
        console.error("API Error:", j.error || "Unknown error");
      }
    } catch (e) {
      console.error("loadWarnedUsers", e);
      warnedDropdown.innerHTML = '<option value="">Failed to load users</option>';
    }
  }
  async function onWarnedUserChange() {
    const uid = warnedDropdown.value;
    if (!uid) {
      userWarningsPanel.classList.add("hidden");
      return;
    }
    try {
      const j = await getJSON(`/api/server/${serverId}/warnings/${uid}`);
      if (j.success) {
        userWarningsPanel.classList.remove("hidden");
        selectedUserName.textContent = j.user;
        warningsList.innerHTML = "";
        if (!j.warnings.length) {
          warningsList.innerHTML = '<div class="text-gray-400">No warnings</div>';
        } else {
          j.warnings.forEach(w => {
            const div = document.createElement("div");
            div.className = "p-2 bg-gray-700 rounded mb-2";
            div.innerHTML = `<div class="text-red-400">${escapeHtml(w.reason)}</div>
              <div class="text-xs text-gray-400">By ${escapeHtml(w.moderator)} — ${new Date(w.date).toLocaleString()}</div>`;
            warningsList.appendChild(div);
          });
        }
      }
    } catch (e) {
      console.error("onWarnedUserChange", e);
    }
  }
  async function clearWarningsHandler() {
    const uid = warnedDropdown.value;
    if (!uid) return alert("Select a user first");
    if (!confirm("Clear all warnings?")) return;
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);
      
      const res = await fetch(`${API_CONFIG.BASE_URL}/api/server/${serverId}/warnings/${uid}/clear`, {
        method: "POST",
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!res.ok) {
        throw new Error(`Server responded with ${res.status}: ${res.statusText}`);
      }
      
      const j = await res.json();
      if (j.success) {
        alert("Warnings cleared!");
        loadWarnedUsers();
        userWarningsPanel.classList.add("hidden");
      } else {
        throw new Error(j.error || "Unknown error occurred");
      }
    } catch (e) {
      console.error("clearWarningsHandler", e);
      alert(`Failed to clear warnings: ${e.message}`);
    }
  }

  // Save settings
  async function saveAllSettings() {
    saveStatus.textContent = "⏳ Saving...";
    const settings = {
      join_role: rolesSelect.value,
      welcome_channel: welcomeChannelSelect.value,
      welcome_message: welcomeMessageInput.value,
      ticket_message: ticketMessageTextarea.value,
      ticket_categories: Array.from(ticketCategoriesContainer.querySelectorAll("input"))
        .map(i => i.value.trim()).filter(Boolean)
    };
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);
      
      const res = await fetch(`${API_CONFIG.BASE_URL}/api/server/${serverId}/settings`, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(settings),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!res.ok) {
        throw new Error(`Server responded with ${res.status}: ${res.statusText}`);
      }
      
      const j = await res.json();
      if (j.success) {
        saveStatus.textContent = "✅ Saved!";
        saveStatus.style.color = "var(--success)";
        setTimeout(() => {
          saveStatus.textContent = "";
          saveStatus.style.color = "";
        }, 2000);
      } else {
        throw new Error(j.error || "Unknown error occurred");
      }
    } catch (e) {
      console.error("saveAllSettings", e);
      saveStatus.textContent = "❌ Error saving settings";
      saveStatus.style.color = "var(--danger)";
      setTimeout(() => {
        saveStatus.textContent = "";
        saveStatus.style.color = "";
      }, 3000);
      alert(`Failed to save settings: ${e.message}`);
    }
  }

  init();
});
