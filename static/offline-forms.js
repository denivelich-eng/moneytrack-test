(function () {
    "use strict";

    function makeId() {
        if (window.crypto && typeof window.crypto.randomUUID === "function") {
            return "offline-" + window.crypto.randomUUID();
        }
        return "offline-" + Date.now() + "-" +
            Math.random().toString(36).slice(2);
    }

    function notify(message) {
        alert(message);
    }

    function applyTransactionBalance(snapshot, transaction, multiplier) {
        if (!snapshot || !transaction || !Array.isArray(snapshot.accounts)) return;

        const account = snapshot.accounts.find(
            item => Number(item.id) === Number(transaction.account_id)
        );
        if (!account) return;

        const amount = Number(transaction.amount);
        if (!Number.isFinite(amount) || amount <= 0) return;

        const sign = transaction.kind === "income" ? 1 : -1;
        account.balance = (Number(account.balance) || 0) + sign * amount * multiplier;
    }

    async function showQueuedOperations() {
        const db = window.MoneyTrackOfflineDB;
        const userId = localStorage.getItem("moneytrack-offline-user-id");
        if (!db || !userId || typeof db.getPendingChanges !== "function") return;

        const pending = await db.getPendingChanges(userId);
        const changes = pending
            .map(item => item.change)
            .filter(change => change && [
                "create_transaction",
                "edit_transaction",
                "delete_transaction"
            ].includes(change.action))
            .map(change => ({
                ...change,
                ...(change.transaction || {})
            }));

        let panel = document.getElementById("offline-pending-operations");
        if (!changes.length) {
            if (panel) panel.remove();
            return;
        }

        if (!panel) {
            panel = document.createElement("section");
            panel.id = "offline-pending-operations";
            panel.className = "card";
            panel.style.margin = "12px 0";
            const main = document.querySelector("main") || document.querySelector(".container") || document.body;
            main.prepend(panel);
        }

        panel.replaceChildren();
        const heading = document.createElement("h3");
        heading.textContent = "Операции, сохранённые на устройстве";
        panel.appendChild(heading);

        let incomeTotal = 0;
        let expenseTotal = 0;

        changes.forEach(change => {
            const row = document.createElement("p");

            if (change.action === "delete_transaction") {
                row.textContent =
                    "Ожидает удаления операции №" +
                    (change.transaction_id || "?");
                panel.appendChild(row);
                return;
            }

            if (change.action === "edit_transaction") {
                const transaction = change.transaction || change;
                row.textContent =
                    "Ожидает изменения операции №" +
                    (change.transaction_id || "?") + ": " +
                    (Number(transaction.amount) || 0).toLocaleString("ru-RU") +
                    " ₽ · " + (transaction.category || "");
                panel.appendChild(row);
                return;
            }

            const amount = Number(change.amount) || 0;

            if (change.kind === "income") {
                incomeTotal += amount;
            } else {
                expenseTotal += amount;
            }

            const kind = change.kind === "income" ? "Доход" : "Расход";
            row.textContent = kind + ": " +
                amount.toLocaleString("ru-RU") + " ₽ · " +
                (change.category || "") +
                (change.note ? " · " + change.note : "");

            panel.appendChild(row);
        });

        const summary = document.createElement("p");
        summary.textContent =
            "Доходы: +" + incomeTotal.toLocaleString("ru-RU") +
            " ₽ · Расходы: −" + expenseTotal.toLocaleString("ru-RU") + " ₽";
        panel.appendChild(summary);
    }


    async function renderOfflineHomeSnapshot() {
        if (navigator.onLine || window.location.pathname !== "/") return;

        const api = window.MoneyTrackOfflineSnapshot;
        if (!api || typeof api.get !== "function") return;

        const data = await api.get();
        if (!data) return;

        const money = value => (Number(value) || 0).toLocaleString("ru-RU", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });

        const accounts = Array.isArray(data.accounts) ? data.accounts : [];
        const transactions = Array.isArray(data.transactions) ? data.transactions : [];

        const balance = accounts.reduce(
            (sum, account) => sum + (Number(account.balance) || 0), 0
        );

        const balanceElement = document.querySelector(".balance-card .amount");
        if (balanceElement) balanceElement.textContent = money(balance) + " ₽";

        const params = new URLSearchParams(window.location.search);
        const month = params.get("month") || (
            new Date().getFullYear() + "-" +
            String(new Date().getMonth() + 1).padStart(2, "0")
        );

        function transactionMonth(value) {
            const str = String(value || "");
            let match = str.match(/^(\d{2})\.(\d{2})\.(\d{4})/);
            if (match) return match[3] + "-" + match[2];
            match = str.match(/^(\d{4})-(\d{2})/);
            return match ? match[1] + "-" + match[2] : "";
        }

        const monthRows = transactions.filter(
            item => transactionMonth(item.created) === month
        );

        const income = monthRows.reduce(
            (sum, item) => sum + (item.kind === "income" ? Number(item.amount) || 0 : 0), 0
        );
        const expense = monthRows.reduce(
            (sum, item) => sum + (item.kind === "expense" ? Number(item.amount) || 0 : 0), 0
        );

        const monthIncome = document.querySelector(".balance-details .income");
        const monthExpense = document.querySelector(".balance-details .expense");
        if (monthIncome) monthIncome.textContent = "+" + money(income) + " ₽";
        if (monthExpense) monthExpense.textContent = "−" + money(expense) + " ₽";

        const heading = Array.from(document.querySelectorAll("h3")).find(
            el => el.textContent.trim() === "Последние операции"
        );
        const card = heading && heading.closest(".card");

        if (card) {
            Array.from(card.children).forEach(child => {
                if (child !== heading) child.remove();
            });

            const latest = transactions.slice().sort((a, b) =>
                (Number(b.id) || 0) - (Number(a.id) || 0)
            ).slice(0, 10);

            if (!latest.length) {
                const empty = document.createElement("p");
                empty.className = "small";
                empty.textContent = "Нет сохранённых операций.";
                card.appendChild(empty);
            }

            latest.forEach(item => {
                const row = document.createElement("div");
                row.className = "transaction-row";
                row.style.cssText = "padding:12px 0;border-bottom:1px solid #e5e7eb;";

                const description = document.createElement("p");
                description.className = item.kind === "income" ? "income" : "expense";
                description.textContent =
                    (item.kind === "income" ? "+" : "−") +
                    money(item.amount) + " ₽ — " +
                    String(item.category || "") +
                    (item.note ? " " + String(item.note) : "");

                const date = document.createElement("div");
                date.className = "small";
                date.textContent = String(item.created || "");

                row.append(description, date);
                card.appendChild(row);
            });
        }
    }

    window.addEventListener("DOMContentLoaded", function () {
        renderOfflineHomeSnapshot().catch(error =>
            console.warn("MoneyTrack: не удалось показать локальный снимок", error)
        );
    });

    window.addEventListener("offline", function () {
        renderOfflineHomeSnapshot().catch(() => {});
    });

    window.MoneyTrackRefreshOfflineQueue = showQueuedOperations;

    window.addEventListener("online", () => {
        setTimeout(showQueuedOperations, 1200);
    });

    window.addEventListener("offline", showQueuedOperations);
    window.addEventListener("moneytrack-queue-updated", showQueuedOperations);

    window.addEventListener("DOMContentLoaded", showQueuedOperations);

    document.addEventListener("submit", async function (event) {
        const form = event.target;

        if (!(form instanceof HTMLFormElement)) return;

        const url = new URL(form.action || window.location.href);
        const method = form.method.toLowerCase();
        const editMatch = url.pathname.match(/^\/edit\/(\d+)$/);
        const deleteMatch = url.pathname.match(/^\/delete\/(\d+)$/);

        if (!navigator.onLine && method === "post" &&
            (editMatch || deleteMatch)) {
            event.preventDefault();

            const db = window.MoneyTrackOfflineDB;
            const userId = localStorage.getItem("moneytrack-offline-user-id");

            if (!db || typeof db.enqueueChange !== "function" || !userId) {
                notify("Офлайн-режим не подготовлен. Откройте MoneyTrack с интернетом.");
                return;
            }

            const transactionId = Number((editMatch || deleteMatch)[1]);

            try {
                let change;

                if (deleteMatch) {
                    change = {
                        action: "delete_transaction",
                        client_change_id: makeId(),
                        transaction_id: transactionId
                    };
                } else {
                    const snapshot = await window.MoneyTrackOfflineSnapshot?.get();
                    const transactions = Array.isArray(snapshot?.transactions)
                        ? snapshot.transactions : [];
                    const original = transactions.find(
                        item => Number(item.id) === transactionId
                    );

                    const kind = form.elements.kind?.value;
                    const amount = Number(form.elements.amount?.value);
                    const category = form.elements.category?.value;
                    const note = form.elements.note?.value || "";
                    const accountField = form.elements.account_id?.value;
                    const accountId = Number(
                        accountField || original?.account_id
                    );

                    if (!original ||
                        !["income", "expense"].includes(kind) ||
                        !Number.isFinite(amount) || amount <= 0 ||
                        !category ||
                        !Number.isFinite(accountId) || accountId <= 0) {
                        notify("Не удалось подготовить изменение. Проверьте операцию и счёт.");
                        return;
                    }

                    change = {
                        action: "edit_transaction",
                        client_change_id: makeId(),
                        transaction_id: transactionId,
                        transaction: {
                            kind: kind,
                            account_id: accountId,
                            amount: amount,
                            category: category,
                            note: note,
                            created: original.created || ""
                        }
                    };
                }

                await db.enqueueChange(userId, change);

                const snapshot = await window.MoneyTrackOfflineSnapshot?.get();
                if (snapshot) {
                    if (!Array.isArray(snapshot.transactions)) {
                        snapshot.transactions = [];
                    }

                    const index = snapshot.transactions.findIndex(
                        item => Number(item.id) === transactionId
                    );
                    const original = index >= 0 ? snapshot.transactions[index] : null;

                    if (!original) {
                        throw new Error("Original transaction not found in local snapshot");
                    }

                    // Отменяем влияние старой операции на её прежний счёт.
                    applyTransactionBalance(snapshot, original, -1);

                    if (change.action === "delete_transaction") {
                        snapshot.transactions = snapshot.transactions.filter(
                            item => Number(item.id) !== transactionId
                        );
                    } else {
                        // Применяем новую операцию к выбранному счёту.
                        applyTransactionBalance(snapshot, change.transaction, 1);
                        snapshot.transactions[index] = {
                            ...original,
                            ...change.transaction,
                            id: transactionId,
                            offline_pending: true,
                            pending_change_id: change.client_change_id
                        };
                    }

                    await db.saveSnapshot(userId, snapshot);
                }

                await renderOfflineHomeSnapshot();
                window.dispatchEvent(new Event("moneytrack-queue-updated"));

                notify(deleteMatch
                    ? "Удаление сохранено в очереди и будет отправлено при подключении."
                    : "Изменение сохранено в очереди и будет отправлено при подключении.");

                if (typeof window.MoneyTrackRefreshOfflineQueue === "function") {
                    await window.MoneyTrackRefreshOfflineQueue();
                }
            } catch (error) {
                console.error("Offline edit/delete failed:", error);
                notify("Не удалось сохранить изменение на устройстве.");
            }

            return;
        }

        if (url.pathname !== "/add" || method !== "post") {
            return;
        }

        const submitter = event.submitter;

        // Создание счёта оставляем штатному обработчику.
        if (
            (submitter && submitter.name === "action" &&
             submitter.value === "create_account") ||
            (form.elements.account_id &&
             form.elements.account_id.value === "__add__")
        ) {
            if (!navigator.onLine) {
                event.preventDefault();
                notify("Для создания нового счёта необходимо подключение к интернету.");
            }
            return;
        }

        // При наличии сети используем обычную форму без изменений.
        if (navigator.onLine) return;

        event.preventDefault();

        const db = window.MoneyTrackOfflineDB;
        if (!db || typeof db.enqueueChange !== "function") {
            notify("Офлайн-сохранение пока недоступно. Откройте приложение с интернетом и попробуйте снова.");
            return;
        }

        const userId = localStorage.getItem("moneytrack-offline-user-id");
        if (!userId) {
            notify("Сначала откройте MoneyTrack с интернетом, чтобы подготовить офлайн-режим.");
            return;
        }

        const kind = form.elements.kind?.value;
        const accountId = Number(form.elements.account_id?.value);
        const amount = Number(form.elements.amount?.value);
        const category = form.elements.category?.value;
        const note = form.elements.note?.value || "";

        if (
            !["income", "expense"].includes(kind) ||
            !Number.isFinite(accountId) ||
            accountId <= 0 ||
            !Number.isFinite(amount) ||
            amount <= 0 ||
            !category
        ) {
            notify("Проверьте сумму, счёт и категорию.");
            return;
        }

        const change = {
            action: "create_transaction",
            client_change_id: makeId(),
            transaction: {
                kind: kind,
                account_id: accountId,
                amount: amount,
                category: category,
                note: note,
                created: new Date().toLocaleString("ru-RU", {
                    day: "2-digit",
                    month: "2-digit",
                    year: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false
                })
            }
        };

        try {
            await db.enqueueChange(userId, change);

            const snapshot = await window.MoneyTrackOfflineSnapshot?.get();
            if (snapshot) {
                if (!Array.isArray(snapshot.transactions)) {
                    snapshot.transactions = [];
                }

                snapshot.transactions.unshift({
                    id: change.client_change_id,
                    client_change_id: change.client_change_id,
                    ...change.transaction,
                    offline_pending: true
                });

                // Сразу отражаем доход или расход в локальном балансе.
                applyTransactionBalance(snapshot, change.transaction, 1);
                await db.saveSnapshot(userId, snapshot);
            }

            await renderOfflineHomeSnapshot();

            const panel = document.getElementById("offline-pending-operations");
            if (panel) panel.remove();

            const message = document.createElement("p");
            message.className = "card";
            message.setAttribute("role", "status");
            message.textContent = "Операция сохранена на устройстве и будет отправлена при подключении к интернету.";
            form.insertAdjacentElement("afterend", message);

            form.reset();

            if (typeof window.MoneyTrackRefreshOfflineQueue === "function") {
                await window.MoneyTrackRefreshOfflineQueue();
            }
        } catch (error) {
            console.error("Offline save failed:", error);
            notify("Не удалось сохранить операцию на устройстве. Попробуйте ещё раз.");
        }
    }, true);
})();
