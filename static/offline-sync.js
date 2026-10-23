(function () {
  "use strict";

  const STATUS_KEY = "moneytrack-offline-status";
  let syncRunning = false;

  function setStatus(state) {
    try {
      sessionStorage.setItem(STATUS_KEY, JSON.stringify({
        state: state,
        checkedAt: new Date().toISOString()
      }));
    } catch (_) {}
  }

  async function saveServerSnapshot() {
    if (!navigator.onLine || !window.MoneyTrackOfflineDB) {
      setStatus("offline-or-storage-unavailable");
      return;
    }

    const db = window.MoneyTrackOfflineDB;

    try {
      const response = await fetch("/api/offline/snapshot", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Accept": "application/json" }
      });

      if (!response.ok) {
        setStatus("server-response-" + response.status);
        return;
      }

      const result = await response.json();

      if (!result.ok || !result.data || !result.user_id) {
        setStatus("snapshot-unavailable");
        return;
      }

      const userId = String(result.user_id);
      localStorage.setItem("moneytrack-offline-user-id", userId);

      const pending = await db.getPendingChanges(userId);
      if (pending && pending.length) {
        setStatus("pending-local-changes");
        return;
      }

      await db.saveSnapshot(userId, result.data);
      setStatus("saved");
      console.info("MoneyTrack: снимок сервера сохранён локально");
    } catch (error) {
      setStatus("save-failed");
    }
  }

  async function syncPendingChanges() {
    if (syncRunning || !navigator.onLine || !window.MoneyTrackOfflineDB) return;

    const db = window.MoneyTrackOfflineDB;
    const userId = localStorage.getItem("moneytrack-offline-user-id");

    if (!userId) {
      setStatus("missing-local-user");
      return;
    }

    syncRunning = true;

    try {
      const pending = await db.getPendingChanges(userId);

      if (!pending || pending.length === 0) {
        await saveServerSnapshot();
        return;
      }

      setStatus("syncing");

      for (const row of pending) {
        if (!navigator.onLine) {
          setStatus("offline-pending");
          return;
        }

        const change = row.change;
        if (!change || !change.client_change_id) continue;

        let response;
        let result;

        try {
          response = await fetch("/api/offline/sync", {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
              "Accept": "application/json",
              "Content-Type": "application/json"
            },
            body: JSON.stringify({ changes: [change] })
          });

          result = await response.json();
        } catch (error) {
          setStatus("sync-network-error");
          return;
        }

        if (response.status === 401 || response.status === 403) {
          setStatus("sync-auth-required");
          return;
        }

        const itemResult = result && Array.isArray(result.results)
          ? result.results.find(item => item.client_change_id === change.client_change_id)
          : null;

        if (response.ok && itemResult && itemResult.ok === true) {
          await db.removePendingChange(row.id);
        } else {
          setStatus("sync-item-failed");
        }
      }

      const remaining = await db.getPendingChanges(userId);

      if (remaining && remaining.length) {
        setStatus("pending-local-changes");
        return;
      }

      await saveServerSnapshot();
      setStatus("synced");
      
    } catch (error) {
      setStatus("sync-failed");
    } finally {
      syncRunning = false;
    }
  }

  window.MoneyTrackOfflineStatus = {
    get: function () {
      try { return JSON.parse(sessionStorage.getItem(STATUS_KEY) || "null"); } catch (_) { return null; }
    },
    checkSavedSnapshot: async function (userId) {
      try {
        if (!userId) return { exists: false, error: "user-id-required" };
        const snapshot = await window.MoneyTrackOfflineDB.getSnapshot(userId);
        return snapshot ? { exists: true, savedAt: snapshot.savedAt } : { exists: false };
      } catch (_) {
        return { exists: false, error: "read-failed" };
      }
    },
    syncNow: syncPendingChanges
  };

  window.addEventListener("online", syncPendingChanges);
  
  window.addEventListener("load", function () {
    if (location.pathname === "/login" || location.pathname === "/register") return;
    const userId = localStorage.getItem("moneytrack-offline-user-id");
    if (userId) {
      syncPendingChanges();
    } else {
      saveServerSnapshot();
    }
  });
})();
