(function () {
  "use strict";

  const DB_NAME = "moneytrack_offline";
  const DB_VERSION = 2;
  const STORE_NAME = "snapshots";
  const QUEUE_STORE = "pending_changes";

  function openDB() {
    return new Promise(function (resolve, reject) {
      if (!("indexedDB" in window)) {
        reject(new Error("IndexedDB недоступен"));
        return;
      }

      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = function () {
        const db = request.result;

        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: "id" });
        }
        if (!db.objectStoreNames.contains(QUEUE_STORE)) {
          const queue = db.createObjectStore(QUEUE_STORE, {
            keyPath: "id",
            autoIncrement: true
          });
          queue.createIndex("userId", "userId", { unique: false });
        }
      };

      request.onsuccess = function () {
        resolve(request.result);
      };

      request.onerror = function () {
        reject(request.error || new Error("Не удалось открыть IndexedDB"));
      };
    });
  }

  async function saveSnapshot(userId, data) {
    const db = await openDB();

    return new Promise(function (resolve, reject) {
      const tx = db.transaction(STORE_NAME, "readwrite");

      tx.objectStore(STORE_NAME).put({
        id: "user:" + String(userId),
        userId: String(userId),
        savedAt: new Date().toISOString(),
        data: data
      });

      tx.oncomplete = function () {
        db.close();
        resolve(true);
      };

      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Не удалось сохранить данные"));
      };

      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Сохранение отменено"));
      };
    });
  }

  async function getSnapshot(userId) {
    const db = await openDB();

    return new Promise(function (resolve, reject) {
      const tx = db.transaction(STORE_NAME, "readonly");
      const request = tx.objectStore(STORE_NAME).get("user:" + String(userId));

      request.onsuccess = function () {
        db.close();
        resolve(request.result || null);
      };

      request.onerror = function () {
        db.close();
        reject(request.error || new Error("Не удалось прочитать данные"));
      };
    });
  }

  async function clearSnapshot(userId) {
    const db = await openDB();

    return new Promise(function (resolve, reject) {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete("user:" + String(userId));

      tx.oncomplete = function () {
        db.close();
        resolve(true);
      };

      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Не удалось удалить снимок"));
      };

      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Удаление отменено"));
      };
    });
  }

  async function enqueueChange(userId, change) {
    if (userId === undefined || userId === null) {
      throw new Error("Не указан пользователь");
    }
    if (!change || typeof change !== "object") {
      throw new Error("Некорректное изменение");
    }

    const db = await openDB();
    return new Promise(function (resolve, reject) {
      const tx = db.transaction(QUEUE_STORE, "readwrite");
      const request = tx.objectStore(QUEUE_STORE).add({
        userId: String(userId),
        change: change,
        createdAt: new Date().toISOString(),
        status: "pending"
      });
      let changeId;

      request.onsuccess = function () {
        changeId = request.result;
      };
      tx.oncomplete = function () {
        db.close();
        resolve(changeId);
      };
      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Не удалось добавить изменение"));
      };
      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Добавление отменено"));
      };
    });
  }

  async function getPendingChanges(userId) {
    if (userId === undefined || userId === null) {
      throw new Error("Не указан пользователь");
    }

    const db = await openDB();
    return new Promise(function (resolve, reject) {
      const tx = db.transaction(QUEUE_STORE, "readonly");
      const index = tx.objectStore(QUEUE_STORE).index("userId");
      const request = index.getAll(String(userId));
      let changes = [];

      request.onsuccess = function () {
        changes = (request.result || []).filter(function (item) {
          return item.status === "pending";
        });
      };
      request.onerror = function () {
        db.close();
        reject(request.error || new Error("Не удалось прочитать очередь"));
      };
      tx.oncomplete = function () {
        db.close();
        resolve(changes);
      };
      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Ошибка чтения очереди"));
      };
      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Чтение очереди отменено"));
      };
    });
  }

  async function removePendingChange(id) {
    const db = await openDB();
    return new Promise(function (resolve, reject) {
      const tx = db.transaction(QUEUE_STORE, "readwrite");
      tx.objectStore(QUEUE_STORE).delete(id);
      tx.oncomplete = function () {
        db.close();
        resolve(true);
      };
      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Не удалось удалить изменение"));
      };
      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Удаление отменено"));
      };
    });
  }

  window.MoneyTrackOfflineDB = {
    saveSnapshot: saveSnapshot,
    getSnapshot: getSnapshot,
    clearSnapshot: clearSnapshot,
    enqueueChange: enqueueChange,
    getPendingChanges: getPendingChanges,
    removePendingChange: removePendingChange
  };
})();
