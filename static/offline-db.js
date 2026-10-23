(function () {
  "use strict";

  const DB_NAME = "moneytrack_offline";
  const DB_VERSION = 2;
  const SNAPSHOTS = "snapshots";
  const QUEUE = "pending_changes";

  function openDB() {
    return new Promise(function (resolve, reject) {
      if (!("indexedDB" in window)) {
        reject(new Error("IndexedDB недоступен"));
        return;
      }

      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = function () {
        const db = request.result;
        const tx = request.transaction;

        if (!db.objectStoreNames.contains(SNAPSHOTS)) {
          db.createObjectStore(SNAPSHOTS, { keyPath: "id" });
        }

        let queue;

        if (!db.objectStoreNames.contains(QUEUE)) {
          queue = db.createObjectStore(QUEUE, {
            keyPath: "id",
            autoIncrement: true
          });
        } else {
          queue = tx.objectStore(QUEUE);
        }

        if (!queue.indexNames.contains("userId")) {
          queue.createIndex("userId", "userId", {
            unique: false
          });
        }
      };

      request.onsuccess = function () {
        const db = request.result;
        db.onversionchange = function () {
          db.close();
        };
        resolve(db);
      };

      request.onerror = function () {
        reject(request.error || new Error("Не удалось открыть базу"));
      };

      request.onblocked = function () {
        console.warn("MoneyTrack: обновление базы ожидает закрытия другой вкладки");
      };
    });
  }

  function runTransaction(storeName, mode, action) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        let tx;
        let result;

        try {
          tx = db.transaction(storeName, mode);
          result = action(tx.objectStore(storeName), tx);
        } catch (error) {
          db.close();
          reject(error);
          return;
        }

        tx.oncomplete = function () {
          db.close();
          resolve(result);
        };

        tx.onerror = function () {
          db.close();
          reject(tx.error || new Error("Ошибка транзакции"));
        };

        tx.onabort = function () {
          db.close();
          reject(tx.error || new Error("Транзакция отменена"));
        };
      });
    });
  }

  function readOne(storeName, key) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(storeName, "readonly");
        const request = tx.objectStore(storeName).get(key);
        let result = null;

        request.onsuccess = function () {
          result = request.result || null;
        };

        tx.oncomplete = function () {
          db.close();
          resolve(result);
        };

        tx.onerror = function () {
          db.close();
          reject(tx.error || new Error("Не удалось прочитать данные"));
        };

        tx.onabort = function () {
          db.close();
          reject(tx.error || new Error("Чтение отменено"));
        };
      });
    });
  }

  async function saveSnapshot(userId, data) {
    if (userId === undefined || userId === null || !data) {
      throw new Error("Не указан пользователь или данные снимка");
    }

    const db = await openDB();

    return new Promise(function (resolve, reject) {
      const tx = db.transaction(SNAPSHOTS, "readwrite");

      tx.objectStore(SNAPSHOTS).put({
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
        reject(tx.error || new Error("Не удалось сохранить снимок"));
      };

      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Сохранение снимка отменено"));
      };
    });
  }

  function getSnapshot(userId) {
    if (userId === undefined || userId === null) {
      return Promise.reject(new Error("Не указан пользователь"));
    }

    return readOne(SNAPSHOTS, "user:" + String(userId));
  }

  async function clearSnapshot(userId) {
    if (userId === undefined || userId === null) {
      throw new Error("Не указан пользователь");
    }

    return runTransaction(SNAPSHOTS, "readwrite", function (store) {
      store.delete("user:" + String(userId));
      return true;
    });
  }

  async function enqueueChange(userId, change) {
    if (userId === undefined || userId === null) {
      throw new Error("Не указан пользователь");
    }

    if (!change || typeof change !== "object" || Array.isArray(change)) {
      throw new Error("Некорректная операция");
    }

    const db = await openDB();

    return new Promise(function (resolve, reject) {
      const tx = db.transaction(QUEUE, "readwrite");
      const request = tx.objectStore(QUEUE).add({
        userId: String(userId),
        change: change,
        createdAt: new Date().toISOString(),
        status: "pending"
      });

      let id = null;

      request.onsuccess = function () {
        id = request.result;
      };

      tx.oncomplete = function () {
        db.close();
        resolve(id);
      };

      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Не удалось сохранить операцию"));
      };

      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Добавление операции отменено"));
      };
    });
  }

  async function getPendingChanges(userId) {
    if (userId === undefined || userId === null) {
      throw new Error("Не указан пользователь");
    }

    const db = await openDB();

    return new Promise(function (resolve, reject) {
      const tx = db.transaction(QUEUE, "readonly");
      const request = tx.objectStore(QUEUE)
        .index("userId")
        .getAll(String(userId));

      let changes = [];

      request.onsuccess = function () {
        changes = (request.result || [])
          .filter(function (item) {
            return item.status === "pending";
          })
          .sort(function (a, b) {
            return a.id - b.id;
          });
      };

      tx.oncomplete = function () {
        db.close();
        resolve(changes);
      };

      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Не удалось прочитать очередь"));
      };

      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Чтение очереди отменено"));
      };
    });
  }

  async function getAllPendingChanges() {
    const db = await openDB();

    return new Promise(function (resolve, reject) {
      const tx = db.transaction(QUEUE, "readonly");
      const request = tx.objectStore(QUEUE).getAll();
      let changes = [];

      request.onsuccess = function () {
        changes = (request.result || [])
          .filter(function (item) {
            return item.status === "pending";
          })
          .sort(function (a, b) {
            return a.id - b.id;
          });
      };

      tx.oncomplete = function () {
        db.close();
        resolve(changes);
      };

      tx.onerror = function () {
        db.close();
        reject(tx.error || new Error("Не удалось прочитать очередь"));
      };

      tx.onabort = function () {
        db.close();
        reject(tx.error || new Error("Чтение очереди отменено"));
      };
    });
  }

  async function removePendingChange(id) {
    if (id === undefined || id === null) {
      throw new Error("Не указан идентификатор операции");
    }

    return runTransaction(QUEUE, "readwrite", function (store) {
      store.delete(id);
      return true;
    });
  }

  window.MoneyTrackOfflineDB = {
    saveSnapshot: saveSnapshot,
    getSnapshot: getSnapshot,
    clearSnapshot: clearSnapshot,
    enqueueChange: enqueueChange,
    getPendingChanges: getPendingChanges,
    getAllPendingChanges: getAllPendingChanges,
    removePendingChange: removePendingChange
  };
})();
